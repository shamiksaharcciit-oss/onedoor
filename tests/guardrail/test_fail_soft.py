from __future__ import annotations

from sqlite3 import Connection

from niyam.guardrail.executor import EngineConfig, evaluate_and_execute
from niyam.guardrail.models import Decision
from niyam.guardrail.registry import ConnectorRegistry
from tests.conftest import make_request


def test_connector_raise_is_fail_soft(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("demo.flaky")
    # Must not raise — fail-soft.
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )
    assert result.decision.decision == Decision.FAILED
    assert result.connector_ok is False
    assert result.error is not None
    rows = list(
        conn.execute(
            "SELECT kind FROM actions_audit WHERE request_id=? ORDER BY id", (str(req.request_id),)
        )
    )
    assert [r["kind"] for r in rows] == ["exec_intent", "exec_result"]


def test_connector_timeout_is_fail_soft(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("demo.slow")
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )
    assert result.decision.decision == Decision.FAILED
    assert "timeout" in (result.error or "")


def test_cap_retained_on_failure(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # demo.flaky has no cap; give a capped failing action to confirm the reservation
    # is NOT refunded on failure (conservative).
    from niyam.guardrail import policy_loader
    from niyam.guardrail.models import Bounds, Caps, Policy, Tier

    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.flakycap",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(daily_rate=3),
            bounds=Bounds(strict_params=False),
        ),
    )
    registry.register("demo.flakycap", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    req = make_request("demo.flakycap")
    evaluate_and_execute(req, conn=conn, registry=registry, config=config, now=req.created_at)
    row = conn.execute(
        "SELECT count FROM cap_counters WHERE action_type='demo.flakycap' AND window_kind='rate'"
    ).fetchone()
    assert row["count"] == 1  # reserved, not refunded
