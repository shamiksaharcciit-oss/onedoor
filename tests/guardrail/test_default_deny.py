from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import CheckId, Decision
from onedoor.guardrail.registry import ConnectorRegistry
from tests.conftest import make_request


def test_unlisted_action_defaults_to_tier3(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("totally.unknown.action")
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )

    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.DEFAULT_DENY


def test_unlisted_action_never_touches_connector(conn: Connection, config: EngineConfig) -> None:
    called: list[str] = []
    registry = ConnectorRegistry()
    registry.register("spy.action", lambda params: called.append("x") or {"ok": True})

    req = make_request("spy.action")
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )

    # spy.action has a connector but no policy -> default-deny -> proposed, not executed.
    assert result.decision.decision == Decision.PROPOSED
    assert called == []


def test_empty_policy_table_defaults_everything_to_tier3(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    conn.execute("DELETE FROM policies")
    req = make_request("demo.toggle", {"target": "demo.lamp", "state": "on"})
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )
    assert result.decision.decision == Decision.PROPOSED
