"""Decimal survives ingress → bounds → cost → settlement, end to end (W3).

Written **before** the fix, on core's instruction (R017 §1), so the implementation is
fitted to the requirement rather than the requirement to the implementation.

The hazard it exists for: `parse_float=Decimal` at ingress and the `isinstance` check
in `bounds.py` are *one* change, not two. Landing the ingress half alone makes every
numeric parameter arrive as `Decimal`, which the bounds gate then rejects outright as
"must be numeric" — every governed numeric action denied. Landing the bounds half
alone leaves S2 open. **A fix that half-lands is worse than the defect**, so the
end-to-end path is asserted as a single property and cannot be satisfied by half of it.

S2, for the record: on `≤0.3.6` a wire amount of `500.1000000000000000001` against a
policy maximum of `500.10` was ALLOWED, because `json.loads` rounded it onto the bound
before any check saw it. `test_a_value_over_the_bound_by_less_than_a_double_can_hold`
is that exact case, and it is the one that proves the defect closed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.bounds import validate
from onedoor.guardrail.caps import resolve_cost
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    NumericBound,
    Outcome,
    Policy,
    Source,
    Tier,
)
from onedoor.store.db import Database

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
CONFIG = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC"))


@pytest.fixture
def spend_db(tmp_path: Path) -> Database:
    """A tier-2 action with a euro cap whose amount comes from a parameter."""
    database = Database(str(tmp_path / "decimal.db"))
    database.init()
    conn = database.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.spend",
            cost_param="amount_eur",
            caps=Caps(eur_day=Decimal("1000.00")),
            bounds=Bounds(
                numeric={"amount_eur": NumericBound(max=Decimal("500.10"))},
                required=["amount_eur"],
                strict_params=True,
            ),
        ),
    )
    conn.close()
    return database


def _request(amount: object) -> ActionRequest:
    return ActionRequest(
        request_id=uuid4(),
        action_type="demo.spend",
        params={"amount_eur": amount},  # type: ignore[dict-item]
        source=Source.LLM,
        rationale="w3 guard",
        created_at=NOW,
    )


def test_bounds_accepts_a_decimal_parameter() -> None:
    """The half-landed-fix guard. Fails with 'must be numeric' before W3."""
    bounds = Bounds(
        numeric={"amount_eur": NumericBound(max=Decimal("500.10"))}, strict_params=False
    )
    result = validate(bounds, {"amount_eur": Decimal("499.99")})
    assert result.ok, (
        f"a Decimal parameter must be accepted as numeric: {result.detail}. "
        f"parse_float=Decimal at ingress and the bounds isinstance check are ONE "
        f"change -- landing ingress alone denies every numeric action."
    )


def test_bounds_still_rejects_a_decimal_over_the_maximum() -> None:
    """Both directions: accepting Decimal must not mean accepting everything."""
    bounds = Bounds(
        numeric={"amount_eur": NumericBound(max=Decimal("500.10"))}, strict_params=False
    )
    assert not validate(bounds, {"amount_eur": Decimal("500.11")}).ok


def test_a_value_over_the_bound_by_less_than_a_double_can_hold() -> None:
    """S2 itself. On <=0.3.6 this was ALLOWED; it must deny.

    The amount exceeds the policy maximum, but by less than an IEEE double can
    represent at that magnitude -- so a float-based gate rounds it onto the bound and
    admits it. Parsed with parse_float=Decimal, the excess survives and the gate sees
    what was actually sent.
    """
    wire = '{"amount_eur": 500.1000000000000000001}'
    params = json.loads(wire, parse_float=Decimal)
    assert params["amount_eur"] > Decimal("500.10"), "the probe must really exceed the cap"

    bounds = Bounds(
        numeric={"amount_eur": NumericBound(max=Decimal("500.10"))}, strict_params=False
    )
    assert not validate(bounds, params).ok, (
        "a value above the policy maximum was admitted -- S2. The gate must see the "
        "amount as sent, not as rounded onto the bound by float parsing."
    )


def test_cost_resolves_from_a_decimal_parameter_without_losing_precision() -> None:
    policy = Policy(
        action_type="demo.spend",
        tier=Tier.AUTO_CAPPED,
        cost_param="amount_eur",
        compensating_command="demo.spend",
        caps=Caps(eur_day=Decimal("1000.00")),
        bounds=Bounds(required=["amount_eur"], strict_params=False),
    )
    amount = Decimal("500.1000000000000000001")
    assert resolve_cost(policy, _request(amount)) == amount


def test_a_decimal_parameter_survives_decide_reserve_and_settle(spend_db: Database) -> None:
    """The end-to-end property: ingress -> bounds -> cost -> reservation -> settle.

    Asserted as one path, so no half of the change can satisfy it.
    """
    conn = spend_db.connect()
    try:
        outcome = decide_and_reserve(_request(Decimal("400.50")), conn=conn, config=CONFIG, now=NOW)
        assert isinstance(outcome, PermittedIntent), (
            f"a Decimal amount within bounds and cap must be permitted, got "
            f"{getattr(outcome, 'decision', outcome)}"
        )
        report_result(
            outcome, conn=conn, outcome=Outcome.SUCCESS, payload=None, error=None, now=NOW
        )

        stored = conn.execute(
            "SELECT eur_total FROM cap_counters WHERE window_kind='eur_day'"
        ).fetchone()
        assert stored is not None, "the reservation must have reached the counter"
        assert Decimal(stored["eur_total"]) == Decimal("400.50")

        # and the cap still binds: 600.00 more would exceed the 1000.00 daily cap
        second = decide_and_reserve(_request(Decimal("600.00")), conn=conn, config=CONFIG, now=NOW)
        assert not isinstance(second, PermittedIntent), "the euro cap must still bind"
    finally:
        conn.close()
