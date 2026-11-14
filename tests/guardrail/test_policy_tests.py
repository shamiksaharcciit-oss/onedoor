"""`onedoor.guardrail.policy_tests`: which decisions a candidate policy moves."""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

from onedoor.guardrail import policy_tests, shadow
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Decision, NumericBound, Policy, Tier
from tests.conftest import make_request


def test_compare_finds_a_request_a_tighter_bound_now_denies(
    conn: Connection, config: EngineConfig
) -> None:
    old = Policy(
        action_type="policytest.auto",
        tier=Tier.AUTO,
        bounds=Bounds(
            numeric={"amount": NumericBound(min=Decimal(0), max=Decimal(100))},
            strict_params=False,
        ),
    )
    tighter = Policy(
        action_type="policytest.auto",
        tier=Tier.AUTO,
        bounds=Bounds(
            numeric={"amount": NumericBound(min=Decimal(0), max=Decimal(10))},
            strict_params=False,
        ),
    )
    requests = [
        make_request("policytest.auto", {"amount": Decimal(5)}),
        make_request("policytest.auto", {"amount": Decimal(50)}),
    ]
    report = policy_tests.compare(
        conn,
        old,
        tighter,
        requests,
        now=requests[0].created_at,
        tz=config.tz,
        kill_switch_engaged=False,
    )
    assert report.coverage == shadow.COVERAGE_ID
    assert len(report.moved) == 1
    assert report.moved[0].request is requests[1]
    assert report.moved[0].old.decision == Decision.EXECUTED
    assert report.moved[0].candidate.decision == Decision.DENIED


def test_compare_omits_a_request_both_policies_decide_the_same_way(
    conn: Connection, config: EngineConfig
) -> None:
    old = Policy(action_type="policytest.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    candidate = Policy(
        action_type="policytest.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False)
    )
    req = make_request("policytest.auto")
    report = policy_tests.compare(
        conn, old, candidate, [req], now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert report.moved == []


def test_compare_omits_a_request_both_policies_deny_for_the_same_reason(
    conn: Connection, config: EngineConfig
) -> None:
    """Both deny -- but for the SAME reason and tier, so the candidate has
    not moved anything about this request; a looser or differently-reasoned
    denial would still count as moved."""
    old = Policy(action_type="policytest.unknown", tier=Tier.AUTO, is_default_deny=True)
    candidate = Policy(action_type="policytest.unknown", tier=Tier.AUTO, is_default_deny=True)
    req = make_request("policytest.unknown")
    report = policy_tests.compare(
        conn, old, candidate, [req], now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert report.moved == []


def test_compare_finds_a_tier_change(conn: Connection, config: EngineConfig) -> None:
    old = Policy(action_type="policytest.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    candidate = Policy(
        action_type="policytest.auto", tier=Tier.CONFIRM, bounds=Bounds(strict_params=False)
    )
    req = make_request("policytest.auto")
    report = policy_tests.compare(
        conn, old, candidate, [req], now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert len(report.moved) == 1
    assert report.moved[0].old.decision == Decision.EXECUTED
    assert report.moved[0].candidate.decision == Decision.PROPOSED


def test_compare_preserves_request_order(conn: Connection, config: EngineConfig) -> None:
    old = Policy(
        action_type="policytest.auto",
        tier=Tier.AUTO,
        bounds=Bounds(
            numeric={"amount": NumericBound(min=Decimal(0), max=Decimal(100))},
            strict_params=False,
        ),
    )
    tighter = Policy(
        action_type="policytest.auto",
        tier=Tier.AUTO,
        bounds=Bounds(
            numeric={"amount": NumericBound(min=Decimal(0), max=Decimal(10))},
            strict_params=False,
        ),
    )
    requests = [
        make_request("policytest.auto", {"amount": Decimal(50)}),
        make_request("policytest.auto", {"amount": Decimal(5)}),
        make_request("policytest.auto", {"amount": Decimal(60)}),
    ]
    report = policy_tests.compare(
        conn,
        old,
        tighter,
        requests,
        now=requests[0].created_at,
        tz=config.tz,
        kill_switch_engaged=False,
    )
    assert [case.request for case in report.moved] == [requests[0], requests[2]]


def test_compare_does_not_let_one_policys_read_affect_the_others(
    conn: Connection, config: EngineConfig
) -> None:
    """Both sides must see the SAME, unconsumed counters -- if evaluating the
    old policy first reserved anything, the candidate's own evaluation right
    after would see a corrupted picture of what is actually available."""
    old = Policy(
        action_type="demo.capped",
        tier=Tier.AUTO,
        caps=Caps(daily_rate=2),
        bounds=Bounds(strict_params=False),
    )
    candidate = Policy(
        action_type="demo.capped",
        tier=Tier.AUTO,
        caps=Caps(daily_rate=5),
        bounds=Bounds(strict_params=False),
    )
    requests = [make_request("demo.capped") for _ in range(4)]
    report = policy_tests.compare(
        conn,
        old,
        candidate,
        requests,
        now=requests[0].created_at,
        tz=config.tz,
        kill_switch_engaged=False,
    )
    # Every one of the 4 calls sees the same (empty) counters under both
    # policies -- none of them would be denied by either cap on its own, so
    # nothing here moves.
    assert report.moved == []
    row = conn.execute(
        "SELECT count FROM cap_counters WHERE action_type='demo.capped' AND window_kind='rate'"
    ).fetchone()
    assert row is None  # confirms neither evaluation reserved anything
