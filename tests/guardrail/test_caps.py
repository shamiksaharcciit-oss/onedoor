from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from sqlite3 import Connection

from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import Bounds, Caps, Decision, Policy, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from tests.conftest import make_request


def _run(conn, registry, config, action, params=None, cost=Decimal(0), now=None):  # type: ignore[no-untyped-def]
    req = make_request(action, params, cost_eur=cost, now=now or make_request(action).created_at)
    return evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )


def test_daily_rate_cap(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    assert _run(conn, registry, config, "demo.capped").executed is True
    assert _run(conn, registry, config, "demo.capped").executed is True
    third = _run(conn, registry, config, "demo.capped")
    assert third.decision.decision == Decision.DENIED
    assert third.decision.reason_code.value == "cap_rate"  # aadp/0.2: unit-neutral


def test_denied_by_cap_does_not_consume_counter(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    _run(conn, registry, config, "demo.capped")
    _run(conn, registry, config, "demo.capped")
    _run(conn, registry, config, "demo.capped")  # denied
    row = conn.execute(
        "SELECT count FROM cap_counters WHERE action_type='demo.capped' AND window_kind='rate'"
    ).fetchone()
    assert row["count"] == 2  # the denial did not push it to 3


def test_dry_run_does_not_consume_cap(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.drycap",
            tier=Tier.AUTO,
            dry_run=True,
            compensating_command="demo.restore",
            caps=Caps(daily_rate=1),
            bounds=Bounds(strict_params=False),
        ),
    )
    result = _run(conn, registry, config, "demo.drycap")
    assert result.decision.decision == Decision.DRY_RUN
    row = conn.execute(
        "SELECT count FROM cap_counters WHERE action_type='demo.drycap' AND window_kind='rate'"
    ).fetchone()
    assert row is None  # nothing reserved


def test_eur_day_cap(conn: Connection, registry: ConnectorRegistry, config: EngineConfig) -> None:
    assert _run(conn, registry, config, "demo.tier2", cost=Decimal("6")).executed is True
    over = _run(conn, registry, config, "demo.tier2", cost=Decimal("5"))  # 6+5 > 10
    assert over.decision.decision == Decision.DENIED
    # aadp/0.2 collapses cap_eur_day and cap_eur_month into cap_value; the WINDOW
    # moves into ND-003's budget object. Until W5 lands it survives only as prose
    # in `detail`, which is exactly the granularity budget_json exists to restore.
    assert over.decision.reason_code.value == "cap_value"
    assert "day" in over.decision.detail


def test_eur_month_cap(conn: Connection, registry: ConnectorRegistry, config: EngineConfig) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.month",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            # The reversibility precondition applies to every auto-executing tier;
            # this test is about the month cap, not about reversibility.
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("1000"), eur_month=Decimal("5")),
            bounds=Bounds(strict_params=False),
        ),
    )
    registry.register("demo.month", lambda p: {"ok": True})
    assert _run(conn, registry, config, "demo.month", cost=Decimal("3")).executed is True
    over = _run(
        conn, registry, config, "demo.month", cost=Decimal("3")
    )  # month 6 > 5, day 6 < 1000
    assert over.decision.decision == Decision.DENIED
    assert over.decision.reason_code.value == "cap_value"
    assert "month" in over.decision.detail  # window still only in prose until W5


def test_daily_rate_rolls_over_at_local_midnight(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    day1 = make_request("demo.capped").created_at
    _run(conn, registry, config, "demo.capped", now=day1)
    _run(conn, registry, config, "demo.capped", now=day1)
    assert (
        _run(conn, registry, config, "demo.capped", now=day1).decision.decision == Decision.DENIED
    )
    # Next calendar day (Europe/Amsterdam) resets the window.
    day2 = day1 + timedelta(days=1)
    assert _run(conn, registry, config, "demo.capped", now=day2).executed is True
