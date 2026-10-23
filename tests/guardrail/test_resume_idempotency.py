"""A LangGraph-style resume (matched by thread_id/tool_call_id) is CHECKED against
the approval row it would reuse, never trusted to match just because the keys do.
"""

from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import CheckId, Decision
from tests.conftest import make_request


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


def test_a_resume_with_an_unchanged_request_gets_its_original_approval(
    conn: Connection, config: EngineConfig
) -> None:
    first = _resume(conn, config, params={"amount": "10"})
    second = _resume(conn, config, params={"amount": "10"})

    assert first.decision.decision == Decision.PROPOSED
    assert second.decision.decision == Decision.PROPOSED
    assert first.approval_id == second.approval_id

    rows = conn.execute("SELECT COUNT(*) AS n FROM approvals").fetchone()
    assert rows["n"] == 1, "a resume with an unchanged request must not create a second approval"


def test_a_resume_with_a_changed_request_is_refused_with_both_digests_recorded(
    conn: Connection, config: EngineConfig
) -> None:
    first = _resume(conn, config, params={"amount": "10"})
    second = _resume(conn, config, params={"amount": "99"})

    assert first.decision.decision == Decision.PROPOSED
    assert second.decision.decision == Decision.DENIED
    assert second.decision.reason_code == CheckId.RESUME_REQUEST_MISMATCH

    rows = conn.execute("SELECT COUNT(*) AS n FROM approvals").fetchone()
    assert rows["n"] == 1, (
        "a changed resume must neither reuse the old approval nor silently create a new one"
    )

    audit_row = conn.execute(
        "SELECT resume_digest_expected, resume_digest_actual FROM actions_audit WHERE id=?",
        (second.audit_id,),
    ).fetchone()
    assert audit_row["resume_digest_expected"] is not None
    assert audit_row["resume_digest_actual"] is not None
    assert audit_row["resume_digest_expected"] != audit_row["resume_digest_actual"]
    assert audit_row["resume_digest_expected"] == approvals.resume_digest(
        "demo.confirm", {"amount": "10"}
    )
    assert audit_row["resume_digest_actual"] == approvals.resume_digest(
        "demo.confirm", {"amount": "99"}
    )


def test_no_resume_key_behaves_exactly_as_before(conn: Connection, config: EngineConfig) -> None:
    """Absent thread_id/tool_call_id, two proposals of the same action are two
    separate approvals -- the ordinary, pre-existing behaviour, untouched."""
    req1 = make_request("demo.confirm", {"amount": "10"})
    req2 = make_request("demo.confirm", {"amount": "10"})
    first = decide_and_reserve(req1, conn=conn, config=config, now=req1.created_at)
    second = decide_and_reserve(req2, conn=conn, config=config, now=req2.created_at)

    assert first.approval_id != second.approval_id
    rows = conn.execute("SELECT COUNT(*) AS n FROM approvals").fetchone()
    assert rows["n"] == 2
