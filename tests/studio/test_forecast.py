"""`ND-056` / T1 — the forecast list, and the fence that keeps it out of the refusal list.

The load-bearing test in this file is `test_the_two_lists_never_merge`. Forward 006 named
five checks as one inline list; two of them are not loader refusals, and a Studio that
presented them as refusals would tell an operator the engine refuses something it
accepts. That is not a cosmetic error: it teaches a false schema, and the operator who
learns it stops trusting the list that was right.
"""

from __future__ import annotations

from decimal import Decimal

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Caps, CheckId, EffectPolicy, Policy, Tier
from onedoor.studio import forecast, staging


def _priced_cap_no_cost_param() -> Policy:
    """A euro cap with no `cost_param`. The loader accepts it; the engine denies on it."""
    return Policy(
        action_type="payments.transfer",
        tier=Tier.CONFIRM,
        caps=Caps(eur_day=Decimal("100")),
        bounds=Bounds(strict_params=False),
    )


# --- the fence: two lists, never merged ---------------------------------------------


def test_the_two_lists_never_merge() -> None:
    """A euro cap with no cost_param forecasts, and is NOT refused.

    Sabotage on the premise (R058 §3): the candidate is first proven to load cleanly
    through the engine's own `validate_policy`, so this cannot pass by accident on a
    candidate that was refused for some other reason. Without that assertion the test
    would still be green if the policy were invalid — and would then be proving nothing.
    """
    policy = _priced_cap_no_cost_param()

    # Premise: the engine itself accepts this rule. If this ever raises, the rest of the
    # test is meaningless and must be re-derived rather than adjusted.
    policy_loader.validate_policy(policy)

    text = (
        "policies:\n"
        "  - action_type: payments.transfer\n"
        "    tier: 3\n"
        "    bounds:\n"
        "      strict_params: false\n"
        "    caps:\n"
        "      eur_day: 100\n"
    )
    result = staging.staged(text)
    assert result.loads is True, "the loader accepts this candidate"
    assert result.refusals == (), "so it must appear in NO refusal list"

    forecasts = forecast.build(result.policies, result.effects)
    codes = {f.reason_code for f in forecasts}
    assert CheckId.COST_UNKNOWN.value in codes, "and it must appear in the forecast list"


def test_strict_params_is_forecast_and_never_refused() -> None:
    text = "policies:\n  - action_type: a.b\n    tier: 3\n"
    result = staging.staged(text)
    assert result.loads is True
    assert result.refusals == ()

    forecasts = forecast.build(result.policies, result.effects)
    bounds = [f for f in forecasts if f.reason_code == CheckId.BOUNDS.value]
    assert len(bounds) == 1
    assert "strict_params" in bounds[0].message
    # It is a property of requests, and the sentence says so rather than implying the
    # rule is defective.
    assert "property of requests" in bounds[0].message


# --- every forecast names the code that will speak (R066 §3) -------------------------


def test_every_forecast_names_a_real_reason_code() -> None:
    policy = _priced_cap_no_cost_param()
    forecasts = forecast.build([policy], [])
    assert forecasts, "this candidate has behaviour worth forecasting"
    known = {c.value for c in CheckId}
    for item in forecasts:
        assert item.reason_code in known, (
            f"{item.reason_code!r} is not a CheckId. A forecast in the Studio's own "
            "vocabulary is unfalsifiable; one naming a reason code is checkable against "
            "what the engine emits."
        )


def test_the_cost_unknown_forecast_says_an_unknown_amount_is_not_a_zero() -> None:
    forecasts = forecast.build([_priced_cap_no_cost_param()], [])
    item = next(f for f in forecasts if f.reason_code == CheckId.COST_UNKNOWN.value)
    assert "never" in item.message and "zero" in item.message


def test_a_priced_cap_with_a_cost_param_forecasts_nothing_about_cost() -> None:
    policy = Policy(
        action_type="payments.transfer",
        tier=Tier.CONFIRM,
        caps=Caps(eur_day=Decimal("100")),
        cost_param="amount_eur",
        bounds=Bounds(required=["amount_eur"], strict_params=False),
    )
    policy_loader.validate_policy(policy)
    codes = {f.reason_code for f in forecast.build([policy], [])}
    assert CheckId.COST_UNKNOWN.value not in codes


def test_a_euro_cap_arriving_from_an_effect_is_forecast_too() -> None:
    """The cap need not be on the rule: an effect the rule reaches can impose one."""
    policy = Policy(
        action_type="payments.transfer",
        tier=Tier.CONFIRM,
        effects=["money.egress"],
        bounds=Bounds(strict_params=False),
    )
    effects = [EffectPolicy(effect="money.egress", caps=Caps(eur_month=Decimal("500")))]
    codes = {f.reason_code for f in forecast.build([policy], effects)}
    assert CheckId.COST_UNKNOWN.value in codes
    item = next(
        f for f in forecast.build([policy], effects) if f.reason_code == CheckId.COST_UNKNOWN.value
    )
    assert "money.egress" in item.message


# --- the inert-effect forecast, and its third outcome -------------------------------


def test_an_inert_effect_is_forecast_when_the_declared_set_is_known() -> None:
    policy = Policy(
        action_type="a.b",
        tier=Tier.CONFIRM,
        effects=["money.egress"],
        bounds=Bounds(strict_params=False),
    )
    forecasts = forecast.build([policy], [], known_effects=set())
    inert = [f for f in forecasts if f.reason_code == CheckId.EFFECT_FLOOR.value]
    assert len(inert) == 1
    assert "money.egress" in inert[0].message
    assert "dropped" in inert[0].message


def test_a_covered_effect_is_not_forecast_as_inert() -> None:
    policy = Policy(
        action_type="a.b",
        tier=Tier.CONFIRM,
        effects=["money.egress"],
        bounds=Bounds(strict_params=False),
    )
    forecasts = forecast.build([policy], [], known_effects={"money.egress"})
    assert not [f for f in forecasts if f.reason_code == CheckId.EFFECT_FLOOR.value]


def test_the_candidates_own_effects_count_as_covering() -> None:
    policy = Policy(
        action_type="a.b",
        tier=Tier.CONFIRM,
        effects=["money.egress"],
        bounds=Bounds(strict_params=False),
    )
    effects = [EffectPolicy(effect="money.egress", min_tier=Tier.CONFIRM)]
    forecasts = forecast.build([policy], effects, known_effects=set())
    assert not [f for f in forecasts if f.reason_code == CheckId.EFFECT_FLOOR.value]


def test_without_the_declared_set_the_inert_check_is_absent_not_guessed() -> None:
    """Three outcomes: absent, unverifiable, failed — and this one is absent.

    Guessing here would warn about a rule that is fine, which is how a reader learns to
    ignore the list.
    """
    policy = Policy(
        action_type="a.b",
        tier=Tier.CONFIRM,
        effects=["money.egress"],
        bounds=Bounds(strict_params=False),
    )
    forecasts = forecast.build([policy], [], known_effects=None)
    assert not [f for f in forecasts if f.reason_code == CheckId.EFFECT_FLOOR.value]
    assert forecast.INERT_UNKNOWN, "and the page has words for why it is absent"


def test_an_effect_added_by_a_param_rule_is_reached_and_checked() -> None:
    text = (
        "policies:\n"
        "  - action_type: a.b\n"
        "    tier: 3\n"
        "    param_effects:\n"
        "      - pattern: '.*'\n"
        "        param: target\n"
        "        add_effects: [net.egress]\n"
    )
    result = staging.staged(text)
    assert result.loads is True
    forecasts = forecast.build(result.policies, result.effects, known_effects=set())
    inert = [f for f in forecasts if f.reason_code == CheckId.EFFECT_FLOOR.value]
    assert [f.message for f in inert if "net.egress" in f.message]


# --- the note describes today (R063 §3 pattern) --------------------------------------


def test_the_inert_forecast_describes_today_and_never_nd_053() -> None:
    """ND-053 will turn this into a boot refusal. Until it ships, saying so is aspiration.

    The forbidden-word list is the fence; it holds the wording to the engine that exists.
    """
    policy = Policy(
        action_type="a.b",
        tier=Tier.CONFIRM,
        effects=["money.egress"],
        bounds=Bounds(strict_params=False),
    )
    forecasts = forecast.build([policy], [], known_effects=set())
    text = " ".join(f.message for f in forecasts).lower()
    for forbidden in ("will be", "until", "planned", "nd-053", "soon", "future", "fixed"):
        assert forbidden not in text, (
            f"{forbidden!r} appears in a forecast. A note that describes tomorrow's "
            "behaviour is aspiration dressed as capability."
        )


def test_the_forecast_notice_says_these_are_not_refusals() -> None:
    assert "not refusals" in forecast.FORECAST_NOTICE
    assert "reason code" in forecast.FORECAST_NOTICE


def test_the_forecast_list_does_not_claim_completeness() -> None:
    assert "has not been shown" in forecast.FORECASTS_ARE_NOT_COMPLETE


def test_forecasts_are_ordered_so_the_same_candidate_renders_the_same_twice() -> None:
    policies = [
        Policy(action_type="z.z", tier=Tier.CONFIRM),
        Policy(action_type="a.a", tier=Tier.CONFIRM),
    ]
    once = forecast.build(policies, [])
    twice = forecast.build(list(reversed(policies)), [])
    assert [f.action_type for f in once] == [f.action_type for f in twice] == ["a.a", "z.z"]


def test_a_forecast_serialises_with_its_reason_code() -> None:
    item = forecast.build([_priced_cap_no_cost_param()], [])[0]
    assert set(item.to_object()) == {"action_type", "reason_code", "message"}
