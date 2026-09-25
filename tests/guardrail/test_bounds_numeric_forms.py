"""`numeric` bounds accept the decimal-string form (ND-054 / F-B).

Written **before** the fix, so the implementation is fitted to the requirement rather
than the requirement to the implementation.

The defect this closes is a conformance one, not a design preference. AADP §5 says
monetary values are decimal strings and the rule "applies wherever a monetary value
appears, **including inside `params`**"; §5.1's own worked request carries
`"amount_eur": "40.00"`. onedoor refused exactly that form whenever a `numeric` bound
was declared over the parameter, while `caps.resolve_cost` accepted it — so **adding a
bound changed which wire types the action accepted**. Two implementations of one
question ("is this a number?"), which is the root the fix closes rather than papers
over.

The direction matters too: the refusal pushed integrators toward binary floating
point, the representation the draft's Security Considerations names as an attack
surface on budget arithmetic. A check that looks stricter can be the one steering you
toward the hazard.

Both directions are asserted here. Accepting a decimal string must not become
"accept anything that is a string": `"abc"`, exponent notation, the non-finite
spellings and `bool` are each refused, and each refusal says why.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.bounds import validate
from onedoor.guardrail.caps import resolve_cost
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    Decision,
    NumericBound,
    Policy,
    Source,
    Tier,
)
from onedoor.store.db import Database

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
CONFIG = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC"))

PARAM = "amount_eur"


def _bounds(maximum: str) -> Bounds:
    return Bounds(numeric={PARAM: NumericBound(max=Decimal(maximum))}, strict_params=False)


def _request(amount: object) -> ActionRequest:
    return ActionRequest(
        request_id=uuid4(),
        action_type="demo.spend",
        params={PARAM: amount},  # type: ignore[dict-item]
        source=Source.LLM,
        rationale="nd-054 numeric forms",
        created_at=NOW,
    )


@pytest.fixture
def spend_db(tmp_path: Path) -> Database:
    """A tier-2 action whose amount is a bounded parameter under a euro cap."""
    database = Database(str(tmp_path / "numeric_forms.db"))
    database.init()
    conn = database.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.spend",
            cost_param=PARAM,
            caps=Caps(eur_day=Decimal("1000.00")),
            bounds=Bounds(
                numeric={PARAM: NumericBound(max=Decimal("120.00"))},
                required=[PARAM],
                strict_params=True,
            ),
        ),
    )
    conn.close()
    return database


# --- the widening, at the verdict ---------------------------------------------


def test_a_decimal_string_inside_the_bound_is_permitted() -> None:
    """§5.1's own example form. Fails with 'must be numeric' before ND-054."""
    result = validate(_bounds("120.00"), {PARAM: "120.00"})
    assert result.ok, (
        f"a decimal string inside the bound must be accepted: {result.detail}. "
        f"AADP §5 applies the decimal-string rule inside `params`, and §5.1 carries "
        f'"amount_eur": "40.00" as the worked example.'
    )


def test_a_decimal_string_is_permitted_end_to_end(spend_db: Database) -> None:
    """The verdict, not just the helper: ingress → bounds → caps → permit."""
    conn = spend_db.connect()
    try:
        outcome = decide_and_reserve(_request("120.00"), conn=conn, config=CONFIG, now=NOW)
        assert isinstance(outcome, PermittedIntent), (
            "a decimal-string amount within bounds and cap must be permitted, got "
            f"{getattr(outcome, 'decision', outcome)}"
        )
    finally:
        conn.close()


def test_a_decimal_string_over_the_bound_is_denied(spend_db: Database) -> None:
    """The other direction: accepting the form must not accept the amount."""
    conn = spend_db.connect()
    try:
        outcome = decide_and_reserve(_request("120.01"), conn=conn, config=CONFIG, now=NOW)
        assert not isinstance(outcome, PermittedIntent)
        assert outcome.decision.decision == Decision.DENIED
        assert outcome.decision.reason_code.value == "bounds"
    finally:
        conn.close()


# --- evaluation is exact -------------------------------------------------------


def test_the_bound_admits_its_own_value_and_refuses_a_cent_more() -> None:
    """`"40.00"` against a bound of `40.00` — the equality a float would blur."""
    bounds = _bounds("40.00")
    assert validate(bounds, {PARAM: "40.00"}).ok
    assert not validate(bounds, {PARAM: "40.01"}).ok


def test_decimal_arithmetic_decides_the_boundary_not_binary_rounding() -> None:
    """A value exact in decimal and not in binary: `0.1 + 0.2`.

    The correct answer, stated rather than asserted from whatever the code happens to
    do: `0.1 + 0.2 == 0.3` is TRUE as decimal arithmetic and FALSE as IEEE binary.
    AADP §5 requires monetary values to be *evaluated exactly*, so a bound of `0.3`
    must admit `"0.1"` and `"0.2"` and must refuse the string the binary sum would
    print, `"0.30000000000000004"`. Refusing the decimal forms instead would be the
    defect this ticket exists to close.
    """
    bounds = _bounds("0.3")
    assert validate(bounds, {PARAM: "0.1"}).ok
    assert validate(bounds, {PARAM: "0.2"}).ok
    assert not validate(bounds, {PARAM: "0.30000000000000004"}).ok, (
        "the binary artifact of 0.1 + 0.2 exceeds a bound of 0.3 as decimal arithmetic"
    )


# --- the refusals, each with its reason ---------------------------------------


def test_a_garbage_string_is_refused_and_the_message_names_the_parameter() -> None:
    result = validate(_bounds("120.00"), {PARAM: "abc"})
    assert not result.ok
    assert PARAM in result.detail, f"the refusal must name the parameter: {result.detail!r}"
    assert "numeric" in result.detail, f"and must say it is not a number: {result.detail!r}"


def test_exponent_notation_is_refused() -> None:
    """A decimal *string* is the fixed-point form the draft writes, not `1e400`.

    `Decimal("1e400")` is finite and would compare fine, so this refusal is a decision
    about the accepted spelling rather than about magnitude — the same reason the
    canonical renderer refuses exponent notation. It is a must-refuse case in the work
    order, so it is asserted as one.
    """
    result = validate(_bounds("120.00"), {PARAM: "1e400"})
    assert not result.ok
    assert "numeric" in result.detail


@pytest.mark.parametrize("spelling", ["NaN", "nan", "Infinity", "-inf", "+infinity"])
def test_a_non_finite_spelling_is_refused_as_non_finite(spelling: str) -> None:
    """E10 keeps these distinct from "not a number": they are malformed, not garbled."""
    result = validate(_bounds("120.00"), {PARAM: spelling})
    assert not result.ok
    assert "finite" in result.detail, (
        f"{spelling!r} is a non-finite value, not an unparseable one: {result.detail!r}"
    )


@pytest.mark.parametrize("flag", [True, False])
def test_bool_is_refused(flag: bool) -> None:
    """`bool` is an `int` subclass; both paths exclude it, and must keep excluding it."""
    result = validate(_bounds("120.00"), {PARAM: flag})
    assert not result.ok
    assert PARAM in result.detail


# --- int and Decimal are unchanged --------------------------------------------


@pytest.mark.parametrize("value", [120, Decimal("120.00"), Decimal("119.999")])
def test_int_and_decimal_still_pass(value: object) -> None:
    assert validate(_bounds("120.00"), {PARAM: value}).ok


def test_an_out_of_range_int_is_still_denied() -> None:
    assert not validate(_bounds("120.00"), {PARAM: 121}).ok


# --- one question, one answer --------------------------------------------------


def test_bounds_and_resolve_cost_cannot_disagree() -> None:
    """The fix's own clause: one `numeric_value`, called by both.

    Every probe below is asked of both paths, and they must give the same answer about
    *the numeric form*. The one deliberate asymmetry is sign: a euro cost must be
    non-negative, so `resolve_cost` refuses `"-5"` as a cost while `bounds` has no
    opinion unless the policy sets a `min`. That is a money rule, not a disagreement
    about what a number is, and it is asserted separately below.
    """
    bounds = Bounds(numeric={PARAM: NumericBound()}, strict_params=False)
    policy = Policy(
        action_type="demo.spend",
        tier=Tier.AUTO_CAPPED,
        dry_run=False,
        compensating_command="demo.spend",
        cost_param=PARAM,
        caps=Caps(eur_day=Decimal("1000.00")),
        bounds=bounds,
    )
    probes: list[object] = [
        120,
        Decimal("120.00"),
        120.5,
        "120.00",
        "0.1",
        "abc",
        "1e400",
        "NaN",
        True,
        False,
        None,
        "",
        "  ",
    ]
    for probe in probes:
        accepted_by_bounds = validate(bounds, {PARAM: probe}).ok
        resolved = resolve_cost(policy, _request(probe)) is not None
        assert accepted_by_bounds == resolved, (
            f"bounds and resolve_cost disagree about {probe!r}: "
            f"bounds accepts={accepted_by_bounds}, resolve_cost resolves={resolved}"
        )


def test_a_negative_cost_is_refused_by_cost_resolution_only() -> None:
    """The stated asymmetry, so it cannot be mistaken for a numeric-form disagreement."""
    bounds = Bounds(numeric={PARAM: NumericBound()}, strict_params=False)
    policy = Policy(
        action_type="demo.spend",
        tier=Tier.AUTO_CAPPED,
        dry_run=False,
        compensating_command="demo.spend",
        cost_param=PARAM,
        caps=Caps(eur_day=Decimal("1000.00")),
        bounds=bounds,
    )
    assert validate(bounds, {PARAM: "-5"}).ok, "a negative number is still a number"
    assert resolve_cost(policy, _request("-5")) is None, "a negative *cost* is not a cost"
