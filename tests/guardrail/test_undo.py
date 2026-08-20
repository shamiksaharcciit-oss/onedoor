from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

import pytest

from onedoor.guardrail import undo
from onedoor.guardrail.errors import UndoError
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.registry import ConnectorRegistry
from tests.conftest import make_request

TOGGLE = {"target": "demo.lamp", "state": "on"}


def _execute_toggle(conn, registry, config, now):  # type: ignore[no-untyped-def]
    req = make_request("demo.toggle", TOGGLE, now=now)
    result = evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=now)
    assert result.executed is True
    assert result.audit_id is not None
    return result.audit_id


def test_undo_within_window_runs_compensating_action(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.toggle").created_at
    audit_id = _execute_toggle(conn, registry, config, now)
    result = undo.undo(audit_id, conn=conn, registry=registry, config=config, now=now)
    assert result.executed is True
    assert result.decision.effective_tier  # demo.restore ran
    # The undo action is linked back to the original.
    row = conn.execute("SELECT undo_of FROM actions_audit WHERE undo_of=?", (audit_id,)).fetchone()
    assert row is not None


def test_undo_after_window_expired(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.toggle").created_at
    audit_id = _execute_toggle(conn, registry, config, now)
    late = now + timedelta(seconds=1000)  # > 900s window
    with pytest.raises(UndoError):
        undo.undo(audit_id, conn=conn, registry=registry, config=config, now=late)


def test_double_undo_rejected(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    now = make_request("demo.toggle").created_at
    audit_id = _execute_toggle(conn, registry, config, now)
    undo.undo(audit_id, conn=conn, registry=registry, config=config, now=now)
    with pytest.raises(UndoError):
        undo.undo(audit_id, conn=conn, registry=registry, config=config, now=now)


def test_failed_original_has_no_undo(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # demo.flaky raises -> FAILED. There is an exec_intent but no successful result.
    req = make_request("demo.flaky", now=make_request("demo.flaky").created_at)
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )
    assert result.executed is False
    with pytest.raises(UndoError):
        undo.undo(
            result.audit_id or -1, conn=conn, registry=registry, config=config, now=req.created_at
        )
