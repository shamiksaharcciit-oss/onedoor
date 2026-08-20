from __future__ import annotations

import sqlite3
from sqlite3 import Connection

import pytest

from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.registry import ConnectorRegistry
from tests.conftest import make_request

TOGGLE = {"target": "demo.lamp", "state": "on"}


def _one_row(conn: Connection) -> int:
    req = make_request("demo.read")
    evaluate_and_execute(
        req, conn=conn, registry=ConnectorRegistry(), config=_cfg(), now=req.created_at
    )
    return int(conn.execute("SELECT id FROM actions_audit LIMIT 1").fetchone()["id"])


def _cfg() -> EngineConfig:
    from zoneinfo import ZoneInfo

    return EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=1.0, tz=ZoneInfo("UTC")
    )


def test_update_is_blocked(conn: Connection) -> None:
    row_id = _one_row(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE actions_audit SET detail='tamper' WHERE id=?", (row_id,))


def test_delete_is_blocked(conn: Connection) -> None:
    row_id = _one_row(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM actions_audit WHERE id=?", (row_id,))


def test_replay_returns_prior_result_and_adds_no_rows(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("demo.toggle", TOGGLE)
    first = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )
    count1 = conn.execute("SELECT COUNT(*) c FROM actions_audit").fetchone()["c"]

    second = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )
    count2 = conn.execute("SELECT COUNT(*) c FROM actions_audit").fetchone()["c"]

    assert count1 == count2  # replay added nothing
    assert second.audit_id == first.audit_id


def test_executed_writes_two_linked_rows(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("demo.toggle", TOGGLE)
    evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=req.created_at)
    rows = list(
        conn.execute(
            "SELECT * FROM actions_audit WHERE request_id=? ORDER BY id", (str(req.request_id),)
        )
    )
    assert [r["kind"] for r in rows] == ["exec_intent", "exec_result"]
    assert rows[1]["parent_id"] == rows[0]["id"]
