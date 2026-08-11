"""When a request would fail multiple checks, the correct precedence holds:
kill-switch clamps to propose-only before caps are ever consulted; bounds are
validated before caps (and even for proposals — an out-of-bounds action is
denied, never proposed)."""

from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail import killswitch, policy_loader
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import Bounds, Caps, CheckId, Decision, NumericBound, Policy, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import make_request


def _bounded_capped(conn: Connection, action: str) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=action,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(numeric={"x": NumericBound(max=10)}, required=["x"]),
            caps=Caps(daily_rate=0),
        ),
    )


def _run(conn, registry, config, action, params):  # type: ignore[no-untyped-def]
    req = make_request(action, params)
    return evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )


def test_kill_switch_clamps_before_caps(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # In-bounds but cap=0 AND kill engaged -> clamped to propose-only before caps
    # are consulted, so it proposes rather than being denied by the cap.
    _bounded_capped(conn, "demo.ord")
    with tx(conn):
        killswitch.set_engaged(conn, True)
    result = _run(conn, registry, config, "demo.ord", {"x": 5})
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.KILL_SWITCH


def test_bounds_beats_caps(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # Out-of-bounds AND cap zero -> bounds wins (checked before caps).
    _bounded_capped(conn, "demo.ord2")
    result = _run(conn, registry, config, "demo.ord2", {"x": 999})
    assert result.decision.reason_code == CheckId.BOUNDS


def test_bounds_denies_even_when_killed(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # An out-of-bounds action is never proposed to a human, even under the kill
    # switch — it is denied.
    _bounded_capped(conn, "demo.ord3")
    with tx(conn):
        killswitch.set_engaged(conn, True)
    result = _run(conn, registry, config, "demo.ord3", {"x": 999})
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.BOUNDS
