from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection
from uuid import uuid4

import pytest

from onedoor.export import export_rows
from onedoor.guardrail import approvals, killswitch
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import (
    EngineConfig,
    deny_approval,
    evaluate_and_execute,
    resume_approval,
)
from onedoor.guardrail.models import ApprovalState, Decision
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import make_request


def _propose(conn, registry, config, now):  # type: ignore[no-untyped-def]
    req = make_request("demo.confirm", now=now)
    result = evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=now)
    assert result.approval_id is not None
    return result.approval_id


def test_create_sets_expiry(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.confirm").created_at
    aid = _propose(conn, registry, config, now)
    approval = approvals.get(conn, aid)
    assert approval is not None
    assert approval.state == ApprovalState.PENDING
    assert approval.expires_at == now + timedelta(seconds=config.approval_ttl_seconds)


def test_approve_before_ttl_executes(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.confirm").created_at
    aid = _propose(conn, registry, config, now)
    result = resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=now)
    assert result.executed is True
    approval = approvals.get(conn, aid)
    assert approval is not None
    assert approval.state == ApprovalState.CONSUMED
    assert approval.resulting_audit_id is not None


def test_approve_after_ttl_rejected(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.confirm").created_at
    aid = _propose(conn, registry, config, now)
    late = now + timedelta(seconds=config.approval_ttl_seconds + 1)
    with pytest.raises(ApprovalError):
        resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=late)


def test_deny(conn: Connection, registry: ConnectorRegistry, config: EngineConfig) -> None:
    now = make_request("demo.confirm").created_at
    aid = _propose(conn, registry, config, now)
    deny_approval(aid, "sess-1", conn=conn, now=now)
    approval = approvals.get(conn, aid)
    assert approval is not None
    assert approval.state == ApprovalState.DENIED


def test_sweep_then_approve_is_rejected(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.confirm").created_at
    aid = _propose(conn, registry, config, now)
    late = now + timedelta(seconds=config.approval_ttl_seconds + 1)
    with tx(conn):
        assert approvals.sweep(conn, late) == 1
    with pytest.raises(ApprovalError):
        resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=late)


def test_a_second_resumption_of_the_same_approval_does_not_execute_again(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """An approved action executes once. Resuming the same approval id again --
    under whatever fresh request_id `resume_approval` itself mints -- must find it
    no longer pending and refuse, never execute a second time."""
    now = make_request("demo.confirm").created_at
    aid = _propose(conn, registry, config, now)
    first = resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=now)
    assert first.executed is True

    with pytest.raises(ApprovalError):
        resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=now)


def test_resume_rechecks_kill_switch(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.confirm").created_at
    aid = _propose(conn, registry, config, now)
    with tx(conn):
        killswitch.set_engaged(conn, True)
    result = resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=now)
    # Kill switch engaged after proposal -> approved action is blocked, not executed.
    assert result.decision.decision == Decision.DENIED
    assert result.executed is False


# --- resumes_audit_id: the link a resumption's own row previously lacked ---------


def test_resumption_names_the_proposals_audit_id(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """Measured against real fixtures: a resumption's audit row carried no field
    linking it to the proposal it resumes, though it had been assumed to. This
    is that link, checked directly against the row it names."""
    now = make_request("demo.confirm").created_at
    req = make_request("demo.confirm", now=now)
    proposed = evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=now)
    assert proposed.approval_id is not None
    proposal_audit_id = proposed.audit_id

    result = resume_approval(
        proposed.approval_id, "sess-1", conn=conn, registry=registry, config=config, now=now
    )
    assert result.executed is True
    row = conn.execute(
        "SELECT resumes_audit_id FROM actions_audit WHERE id=?", (result.audit_id,)
    ).fetchone()
    assert row["resumes_audit_id"] == proposal_audit_id


def test_a_replayed_resumption_does_not_add_a_second_link(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """The idempotency guard returns the recorded result for a repeated
    request_id (test_decision_split.py's own `test_replay_guard_runs_before_decide`,
    applied here): a replayed resumption must not write a second linked row."""
    now = make_request("demo.confirm").created_at
    req = make_request("demo.confirm", now=now)
    proposed = evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=now)
    approval_id = proposed.approval_id
    assert approval_id is not None
    proposal_audit_id = proposed.audit_id

    with tx(conn):
        original = approvals.cas_approve(conn, approval_id, "sess-1", now)
    resumed = original.model_copy(update={"request_id": uuid4(), "created_at": now})

    first = evaluate_and_execute(
        resumed,
        conn=conn,
        registry=registry,
        config=config,
        now=now,
        approved_override=True,
        resumes_audit_id=proposal_audit_id,
    )
    assert first.executed is True

    replay = evaluate_and_execute(
        resumed,
        conn=conn,
        registry=registry,
        config=config,
        now=now,
        approved_override=True,
        resumes_audit_id=proposal_audit_id,
    )
    assert replay.audit_id == first.audit_id, (
        "a replay must return the recorded result, not write again"
    )

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM actions_audit WHERE resumes_audit_id=?", (proposal_audit_id,)
    ).fetchone()["n"]
    assert count == 1, "a replay of the same resumed request must not add a second link"


def test_export_carries_the_resumption_link(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.confirm").created_at
    req = make_request("demo.confirm", now=now)
    proposed = evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=now)
    assert proposed.approval_id is not None
    proposal_audit_id = proposed.audit_id

    result = resume_approval(
        proposed.approval_id, "sess-1", conn=conn, registry=registry, config=config, now=now
    )
    exported = export_rows(conn)
    resumption_record = next(r for r in exported if r["id"] == result.audit_id)
    assert resumption_record["resumes_audit_id"] == proposal_audit_id


def test_sabotage_omitting_resumes_audit_id_leaves_no_link(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """The three tests above are not vacuous: reconstructed here without passing
    `resumes_audit_id` at all -- the pre-0.8.1 call shape -- to prove the link
    genuinely depends on threading it through, not on some other mechanism that
    would populate it regardless."""
    now = make_request("demo.confirm").created_at
    req = make_request("demo.confirm", now=now)
    proposed = evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=now)
    approval_id = proposed.approval_id
    assert approval_id is not None

    with tx(conn):
        original = approvals.cas_approve(conn, approval_id, "sess-1", now)
    resumed = original.model_copy(update={"request_id": uuid4(), "created_at": now})
    result = evaluate_and_execute(
        resumed, conn=conn, registry=registry, config=config, now=now, approved_override=True
    )
    assert result.executed is True
    row = conn.execute(
        "SELECT resumes_audit_id FROM actions_audit WHERE id=?", (result.audit_id,)
    ).fetchone()
    assert row["resumes_audit_id"] is None, "omitting the parameter must leave no link"
