from __future__ import annotations

from sqlite3 import Connection

from niyam.guardrail import policy_loader
from niyam.guardrail.executor import EngineConfig, evaluate_and_execute
from niyam.guardrail.models import Bounds, Decision, NumericBound, Policy, Tier
from niyam.guardrail.registry import ConnectorRegistry
from tests.conftest import make_request


def _climate_policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.climate",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(
                numeric={"setpoint": NumericBound(min=17, max=23)}, required=["setpoint"]
            ),
        ),
    )


def _run(conn, registry, config, action, params):  # type: ignore[no-untyped-def]
    req = make_request(action, params)
    return evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )


def test_setpoint_in_bounds_ok(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    _climate_policy(conn)
    registry.register("demo.climate", lambda p: {"ok": True})
    for value in (17, 20, 23):
        assert _run(conn, registry, config, "demo.climate", {"setpoint": value}).executed is True


def test_setpoint_out_of_bounds_denied(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    _climate_policy(conn)
    registry.register("demo.climate", lambda p: {"ok": True})
    for value in (16, 24, 25):
        result = _run(conn, registry, config, "demo.climate", {"setpoint": value})
        assert result.decision.decision == Decision.DENIED
        assert result.decision.reason_code.value == "bounds"


def test_missing_required_param_denied(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    _climate_policy(conn)
    result = _run(conn, registry, config, "demo.climate", {})
    assert result.decision.decision == Decision.DENIED


def test_unknown_param_rejected_when_strict(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    result = _run(
        conn, registry, config, "demo.toggle", {"target": "demo.lamp", "state": "on", "evil": "x"}
    )
    assert result.decision.decision == Decision.DENIED
    assert "unknown param" in result.decision.detail


def test_enum_whitelist_enforced(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    result = _run(
        conn, registry, config, "demo.toggle", {"target": "demo.notallowed", "state": "on"}
    )
    assert result.decision.decision == Decision.DENIED


def test_bounds_enforced_on_tier3_proposal(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # A listed Tier-3 action with bounds: out-of-bounds must be DENIED, never proposed.
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.t3bounded",
            tier=Tier.CONFIRM,
            bounds=Bounds(numeric={"amount": NumericBound(max=100)}, required=["amount"]),
        ),
    )
    result = _run(conn, registry, config, "demo.t3bounded", {"amount": 500})
    assert result.decision.decision == Decision.DENIED
    assert result.approval_id is None
