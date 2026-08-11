from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

from niyam.guardrail import killswitch, policy_loader
from niyam.guardrail.executor import EngineConfig, evaluate_and_execute
from niyam.guardrail.models import Bounds, Decision, Policy, Tier
from niyam.guardrail.registry import ConnectorRegistry
from niyam.store.db import tx
from tests.conftest import make_request

TOGGLE = {"target": "demo.lamp", "state": "on"}


def _run(conn, registry, config, action, params=None, now=None):  # type: ignore[no-untyped-def]
    req = make_request(action, params, now=now or make_request(action).created_at)
    return evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )


def test_dry_run_does_not_call_connector(conn: Connection, config: EngineConfig) -> None:
    called: list[str] = []
    registry = ConnectorRegistry()
    registry.register("demo.dry", lambda p: called.append("x") or {"ok": True})
    result = _run(conn, registry, config, "demo.dry", TOGGLE)
    assert result.decision.decision == Decision.DRY_RUN
    assert result.executed is False
    assert called == []


def test_new_action_type_defaults_to_dry_run(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # A freshly-loaded policy with no explicit dry_run defaults to true (invariant 7).
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.fresh",
            tier=Tier.AUTO,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    assert _run(conn, registry, config, "demo.fresh").decision.decision == Decision.DRY_RUN


def test_dry_run_until_graduation(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    base = make_request("demo.grad").created_at
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.grad",
            tier=Tier.AUTO,
            dry_run=False,
            dry_run_until=base + timedelta(days=1),
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    registry.register("demo.grad", lambda p: {"ok": True})
    # Before graduation -> dry-run.
    assert _run(conn, registry, config, "demo.grad", now=base).decision.decision == Decision.DRY_RUN
    # After the clock passes -> live.
    later = base + timedelta(days=2)
    assert _run(conn, registry, config, "demo.grad", now=later).executed is True


def test_kill_switch_takes_precedence_over_dry_run(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    with tx(conn):
        killswitch.set_engaged(conn, True)
    result = _run(conn, registry, config, "demo.dry", TOGGLE)
    assert result.decision.decision == Decision.PROPOSED
