from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import CheckId, Decision, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from tests.conftest import make_request

TOGGLE = {"target": "demo.lamp", "state": "on"}


def _rows(conn: Connection, request_id: object) -> list:
    return list(
        conn.execute(
            "SELECT * FROM actions_audit WHERE request_id=? ORDER BY id", (str(request_id),)
        )
    )


def test_tier1_executes_with_undo(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("demo.toggle", TOGGLE)
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )

    assert result.decision.decision == Decision.EXECUTED
    assert result.executed is True
    assert result.connector_ok is True
    assert result.undo_available_until is not None
    rows = _rows(conn, req.request_id)
    assert [r["kind"] for r in rows] == ["exec_intent", "exec_result"]


def test_tier0_observe_is_noop(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("demo.read")
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )

    assert result.decision.decision == Decision.EXECUTED
    assert result.decision.reason_code == CheckId.OBSERVE
    assert result.decision.effective_tier == Tier.OBSERVE
    assert result.undo_available_until is None
    assert len(_rows(conn, req.request_id)) == 1


def test_tier2_capped_executes(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # The demo.tier2 fixture carries euro caps, so a request against it must
    # declare an amount. It previously did not, and executed anyway -- because
    # an unset cost was read as zero and every euro cap passed. That was F7.
    # This test is about tier resolution, so it now supplies a real amount
    # rather than relying on the behaviour that turned out to be the defect.
    req = make_request("demo.tier2", cost_eur=Decimal("1.00"))
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )

    assert result.executed is True
    assert result.decision.nominal_tier == Tier.AUTO_CAPPED


def test_tier3_proposes(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("demo.unlisted")
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )

    assert result.decision.decision == Decision.PROPOSED
    assert result.approval_id is not None
    assert result.executed is False


def test_nominal_and_effective_tier_recorded(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("demo.toggle", TOGGLE)
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )
    assert result.decision.nominal_tier == Tier.AUTO
    assert result.decision.effective_tier == Tier.AUTO
