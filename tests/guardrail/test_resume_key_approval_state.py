"""`find_by_resume_key` selects by (thread_id, tool_call_id) and the approval's own
state: `pending` or `approved` reuse the row, `consumed`/`expired`/`denied` do not.

The ordinary resume needs both reusable states: a LangGraph resume re-executes the
interrupted node from the top, so `wrap_tool_call` decides once with no reference
(must find the row whether a human has acted yet or not -- `pending` or `approved`)
and, separately, once with the reference (consumes it). Finding only `pending` rows
(an earlier state in this same release) made the first of those two decisions miss
an already-`approved` row and propose a second, never-granted one on every ordinary
resume -- the bug this file's row-counting tests close.
"""

from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Decision
from tests.conftest import FROZEN_NOW, make_request


def _resume(
    conn: Connection,
    config: EngineConfig,
    *,
    params: dict[str, object],
    approval_ref: int | None = None,
):  # type: ignore[no-untyped-def]
    req = make_request("demo.confirm", params)
    if approval_ref is not None:
        req = req.model_copy(update={"approval_ref": approval_ref})
    return decide_and_reserve(
        req,
        conn=conn,
        config=config,
        now=req.created_at,
        thread_id="thread-1",
        tool_call_id="call-1",
    )


def _table(conn: Connection) -> list[tuple[int, str]]:
    rows = conn.execute("SELECT id, state FROM approvals ORDER BY id").fetchall()
    return [(r["id"], r["state"]) for r in rows]


def test_a_resume_while_pending_reuses_the_row(conn: Connection, config: EngineConfig) -> None:
    first = _resume(conn, config, params={"amount": "10"})
    assert first.decision.decision == Decision.PROPOSED
    approval_id = first.approval_id

    second = _resume(conn, config, params={"amount": "10"})
    assert second.decision.decision == Decision.PROPOSED
    assert second.approval_id == approval_id
    assert _table(conn) == [(approval_id, "pending")]


def test_a_resume_while_approved_with_no_reference_reuses_the_row_and_creates_none(
    conn: Connection, config: EngineConfig
) -> None:
    """The ordinary resume's first decision: the interrupted node re-executes
    from the top, so `_decide()` runs once more with no reference -- it must
    find the now-approved row, not miss it and propose a second one."""
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    approvals.cas_approve(conn, approval_id, session_id="approver", now=FROZEN_NOW)

    second = _resume(conn, config, params={"amount": "10"})
    assert second.decision.decision == Decision.PROPOSED
    assert second.approval_id == approval_id, (
        "a resume while the row is already approved must reuse it, not propose a new one"
    )
    assert _table(conn) == [(approval_id, "approved")], (
        "the ordinary resume's first (reference-less) decision must create no second row"
    )


def test_a_resume_while_approved_with_the_reference_is_permitted_and_consumes_it(
    conn: Connection, config: EngineConfig
) -> None:
    """The ordinary resume's second decision: the reference is presented, and
    this is the normal approval_ref path, untouched by the resume-key fix."""
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    approvals.cas_approve(conn, approval_id, session_id="approver", now=FROZEN_NOW)

    second = _resume(conn, config, params={"amount": "10"}, approval_ref=approval_id)
    assert isinstance(second, PermittedIntent)
    assert _table(conn) == [(approval_id, "consumed")]


def test_a_resume_after_its_approval_was_consumed_does_not_reuse_it(
    conn: Connection, config: EngineConfig
) -> None:
    first = _resume(conn, config, params={"amount": "10"})
    assert first.decision.decision == Decision.PROPOSED
    approval_id = first.approval_id
    assert approval_id is not None

    approvals.cas_approve(conn, approval_id, session_id="approver", now=FROZEN_NOW)
    approvals.consume(conn, approval_id)
    row = approvals.get(conn, approval_id)
    assert row is not None and row.state.value == "consumed"

    second = _resume(conn, config, params={"amount": "10"})
    assert second.approval_id != approval_id, (
        "a resume after its approval was consumed reused the dead approval row -- "
        "a caller told 'proposed' with that id can never have it approved again"
    )


def test_a_resume_after_its_approval_expired_does_not_reuse_it(
    conn: Connection, config: EngineConfig
) -> None:
    first = _resume(conn, config, params={"amount": "10"})
    assert first.decision.decision == Decision.PROPOSED
    approval_id = first.approval_id
    assert approval_id is not None

    row = approvals.get(conn, approval_id)
    assert row is not None
    later = row.expires_at + timedelta(seconds=1)
    swept = approvals.sweep(conn, later)
    assert swept == 1
    row = approvals.get(conn, approval_id)
    assert row is not None and row.state.value == "expired"

    second_req = make_request("demo.confirm", {"amount": "10"})
    second = decide_and_reserve(
        second_req,
        conn=conn,
        config=config,
        now=later,
        thread_id="thread-1",
        tool_call_id="call-1",
    )
    assert second.approval_id != approval_id, (
        "a resume after its approval expired reused the dead approval row -- "
        "a caller told 'proposed' with that id can never have it approved again"
    )


def test_a_resume_after_its_approval_was_denied_gets_a_fresh_row(
    conn: Connection, config: EngineConfig
) -> None:
    """Not named a requirement anywhere -- stated here either way: a denied
    approval is exactly as dead as a consumed or expired one, and `deny`
    never reaches `find_by_resume_key`'s kept states."""
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    approvals.deny(conn, approval_id, session_id="approver", now=FROZEN_NOW)
    row = approvals.get(conn, approval_id)
    assert row is not None and row.state.value == "denied"

    second = _resume(conn, config, params={"amount": "10"})
    assert second.approval_id != approval_id, (
        "a resume after its approval was denied reused the dead approval row"
    )
    assert _table(conn) == [(approval_id, "denied"), (second.approval_id, "pending")]


def test_the_ordinary_resume_leaves_exactly_one_row_at_engine_level(
    conn: Connection, config: EngineConfig
) -> None:
    """Row-counting: propose with a resume key, approve, then resume -- the
    ordinary LangGraph shape, where the interrupted node's re-execution
    decides once with no reference and once with the reference."""
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    assert _table(conn) == [(approval_id, "pending")]

    approvals.cas_approve(conn, approval_id, session_id="approver", now=FROZEN_NOW)
    assert _table(conn) == [(approval_id, "approved")]

    no_ref = _resume(conn, config, params={"amount": "10"})
    assert no_ref.decision.decision == Decision.PROPOSED
    assert no_ref.approval_id == approval_id
    assert _table(conn) == [(approval_id, "approved")], (
        "the resume's first (reference-less) pass must not propose a second approval"
    )

    with_ref = _resume(conn, config, params={"amount": "10"}, approval_ref=approval_id)
    assert isinstance(with_ref, PermittedIntent)
    assert _table(conn) == [(approval_id, "consumed")], (
        "the ordinary resume must end with exactly the one original row, consumed"
    )
