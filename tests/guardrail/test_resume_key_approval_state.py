"""`find_by_resume_key` selects by (thread_id, tool_call_id) alone, with no filter
on the approval's own state (approvals.py's own docstring names this explicitly).
This checks whether a resume can reuse an approval that is no longer reusable --
one already consumed, or one that has expired.
"""

from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Decision
from tests.conftest import FROZEN_NOW, make_request


def _resume(conn: Connection, config: EngineConfig, *, params: dict[str, object]):  # type: ignore[no-untyped-def]
    req = make_request("demo.confirm", params)
    return decide_and_reserve(
        req,
        conn=conn,
        config=config,
        now=req.created_at,
        thread_id="thread-1",
        tool_call_id="call-1",
    )


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
