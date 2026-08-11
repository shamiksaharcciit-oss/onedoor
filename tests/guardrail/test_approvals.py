from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

import pytest
from niyam.guardrail import approvals, killswitch
from niyam.guardrail.errors import ApprovalError
from niyam.guardrail.executor import (
    EngineConfig,
    deny_approval,
    evaluate_and_execute,
    resume_approval,
)
from niyam.guardrail.models import ApprovalState, Decision
from niyam.guardrail.registry import ConnectorRegistry
from niyam.store.db import tx
from tests.conftest import make_request


def _propose(conn, registry, config, now):  # type: ignore[no-untyped-def]
    req = make_request("demo.unlisted", now=now)
    result = evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=now)
    assert result.approval_id is not None
    return result.approval_id


def test_create_sets_expiry(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.unlisted").created_at
    aid = _propose(conn, registry, config, now)
    approval = approvals.get(conn, aid)
    assert approval is not None
    assert approval.state == ApprovalState.PENDING
    assert approval.expires_at == now + timedelta(seconds=config.approval_ttl_seconds)


def test_approve_before_ttl_executes(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.unlisted").created_at
    aid = _propose(conn, registry, config, now)
    result = resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=now)
    assert result.executed is True
    approval = approvals.get(conn, aid)
    assert approval is not None
    assert approval.state == ApprovalState.EXECUTED
    assert approval.resulting_audit_id is not None


def test_approve_after_ttl_rejected(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.unlisted").created_at
    aid = _propose(conn, registry, config, now)
    late = now + timedelta(seconds=config.approval_ttl_seconds + 1)
    with pytest.raises(ApprovalError):
        resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=late)


def test_deny(conn: Connection, registry: ConnectorRegistry, config: EngineConfig) -> None:
    now = make_request("demo.unlisted").created_at
    aid = _propose(conn, registry, config, now)
    deny_approval(aid, "sess-1", conn=conn, now=now)
    approval = approvals.get(conn, aid)
    assert approval is not None
    assert approval.state == ApprovalState.DENIED


def test_sweep_then_approve_is_rejected(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.unlisted").created_at
    aid = _propose(conn, registry, config, now)
    late = now + timedelta(seconds=config.approval_ttl_seconds + 1)
    with tx(conn):
        assert approvals.sweep(conn, late) == 1
    with pytest.raises(ApprovalError):
        resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=late)


def test_resume_rechecks_kill_switch(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.unlisted").created_at
    aid = _propose(conn, registry, config, now)
    with tx(conn):
        killswitch.set_engaged(conn, True)
    result = resume_approval(aid, "sess-1", conn=conn, registry=registry, config=config, now=now)
    # Kill switch engaged after proposal -> approved action is blocked, not executed.
    assert result.decision.decision == Decision.DENIED
    assert result.executed is False
