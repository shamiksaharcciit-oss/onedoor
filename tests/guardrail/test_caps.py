from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from sqlite3 import Connection

from onedoor.guardrail import caps as caps_mod
from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import Bounds, Caps, Decision, Policy, Tier
from onedoor.guardrail.policy import PolicyStore
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
    assert third.decision.reason_code.value == "rate_exhausted"  # aadp/0.2: unit-neutral


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
    assert over.decision.reason_code.value == "budget_exhausted"
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
    assert over.decision.reason_code.value == "budget_exhausted"
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


# ---------------------------------------------------------------------------
# check_only: check_and_reserve's own read-and-check half, with no reservation.
# ---------------------------------------------------------------------------


def test_check_only_denies_the_same_way_check_and_reserve_does(
    conn: Connection, config: EngineConfig
) -> None:
    policy = PolicyStore().get(conn, "demo.capped")
    req = make_request("demo.capped")
    # Exhaust the real cap first, through the real path.
    caps_mod.check_and_reserve(conn, policy, req, req.created_at, config.tz)
    caps_mod.check_and_reserve(conn, policy, req, req.created_at, config.tz)
    result = caps_mod.check_only(conn, policy, req, req.created_at, config.tz)
    assert result.exceeded is True
    assert result.reason is not None
    assert result.reason.value == "rate_exhausted"


def test_check_only_reserves_nothing(conn: Connection, config: EngineConfig) -> None:
    policy = PolicyStore().get(conn, "demo.capped")
    req = make_request("demo.capped")
    result = caps_mod.check_only(conn, policy, req, req.created_at, config.tz)
    assert result.exceeded is False
    assert result.deltas == ()
    row = conn.execute(
        "SELECT count FROM cap_counters WHERE action_type='demo.capped' AND window_kind='rate'"
    ).fetchone()
    assert row is None  # nothing written at all, not even a zero row


def test_check_only_does_not_block_a_later_real_reservation(
    conn: Connection, config: EngineConfig
) -> None:
    """A read-only check must never consume the budget it is only looking at --
    two check_only calls followed by the real cap's own two-per-day limit must
    still allow exactly two real reservations."""
    policy = PolicyStore().get(conn, "demo.capped")
    req = make_request("demo.capped")
    caps_mod.check_only(conn, policy, req, req.created_at, config.tz)
    caps_mod.check_only(conn, policy, req, req.created_at, config.tz)
    caps_mod.check_only(conn, policy, req, req.created_at, config.tz)
    first = caps_mod.check_and_reserve(conn, policy, req, req.created_at, config.tz)
    second = caps_mod.check_and_reserve(conn, policy, req, req.created_at, config.tz)
    assert first.exceeded is False
    assert second.exceeded is False


def test_reservation_reclaim(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """A real decision reclaims an expired reservation before it ever checks
    a cap (`reclaim_expired_reservations`, called at the top of a decide).
    `check_only` has no write access to do that same reclaim, so it must
    count an expired-but-still-held reservation as reclaimed anyway --
    without writing anything -- or it denies on a budget a real decision,
    right now, would see as free."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.reclaim",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(daily_rate=1),
            bounds=Bounds(strict_params=False),
        ),
    )
    policy = PolicyStore().get(conn, "demo.reclaim")
    req0 = make_request("demo.reclaim")
    # decide_and_reserve, not evaluate_and_execute: the permit is never
    # reported, so the reservation stays `held` -- exactly the state a
    # report-less caller (or an outright-abandoned permit) leaves behind.
    first = decide_and_reserve(req0, conn=conn, config=config, now=req0.created_at)
    assert isinstance(first, PermittedIntent)

    reservation = conn.execute(
        "SELECT status, deadline_utc FROM cap_reservations WHERE request_id=?",
        (str(req0.request_id),),
    ).fetchone()
    assert reservation["status"] == "held"

    past_deadline = req0.created_at + timedelta(seconds=config.reservation_ttl_seconds + 1)
    req = make_request("demo.reclaim", now=past_deadline)

    # Without the fix this denies: the reservation is still `held` in
    # cap_counters, which a live decide would have already reclaimed.
    result = caps_mod.check_only(conn, policy, req, past_deadline, config.tz)
    assert result.exceeded is False
    assert result.deltas == ()

    # And it still wrote nothing -- the reservation itself is untouched.
    unchanged = conn.execute(
        "SELECT status FROM cap_reservations WHERE request_id=?", (str(req0.request_id),)
    ).fetchone()
    assert unchanged["status"] == "held"
    row = conn.execute(
        "SELECT count FROM cap_counters WHERE action_type='demo.reclaim' AND window_kind='rate'"
    ).fetchone()
    assert row["count"] == 1  # the real counter is untouched too


def test_check_only_still_reserves_nothing_across_many_calls(
    conn: Connection, config: EngineConfig
) -> None:
    """A stress case: many `check_only` calls around real, still-`held`
    reservations (so a `cap_reservations` row exists for the new
    expired-reservation accounting to read, not just `cap_counters`)
    must still never themselves write."""
    policy = PolicyStore().get(conn, "demo.capped")
    req1 = make_request("demo.capped", {}, cost_eur=Decimal(0))
    req2 = make_request("demo.capped", {}, cost_eur=Decimal(0))
    assert isinstance(
        decide_and_reserve(req1, conn=conn, config=config, now=req1.created_at), PermittedIntent
    )
    assert isinstance(
        decide_and_reserve(req2, conn=conn, config=config, now=req2.created_at), PermittedIntent
    )
    req = make_request("demo.capped")
    for _ in range(1000):
        result = caps_mod.check_only(conn, policy, req, req.created_at, config.tz)
        assert result.exceeded is True
        assert result.deltas == ()
    row = conn.execute(
        "SELECT count, eur_total FROM cap_counters WHERE action_type='demo.capped' "
        "AND window_kind='rate'"
    ).fetchone()
    assert row["count"] == 2  # untouched by any of the 1000 calls
    reservation_count = conn.execute("SELECT COUNT(*) c FROM cap_reservations").fetchone()["c"]
    assert reservation_count == 2  # one per real reservation, none added by check_only
    still_held = conn.execute(
        "SELECT COUNT(*) c FROM cap_reservations WHERE status='held'"
    ).fetchone()["c"]
    assert still_held == 2  # none marked expired by a call that must not write
    still_held = conn.execute(
        "SELECT COUNT(*) c FROM cap_reservations WHERE status='held'"
    ).fetchone()["c"]
    assert still_held == 2  # none marked expired by a call that must not write
