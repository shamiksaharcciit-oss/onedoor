"""`ND-056` / T1 — what this rule will DO at decision time, kept apart from what the loader refuses.

Two lists, never merged (R066 §3). `staging.staged` answers *"will the loader refuse this
at boot?"*. This answers a different question — *"once loaded, how will this rule
behave?"* — and the two must never be rendered as one list, because a reader who cannot
tell them apart learns a false schema: they come to believe the Studio refuses things the
engine accepts, and then they stop believing the Studio.

## Why the separation is a correctness rule and not a layout preference

Forward 006 asked for five things in one inline list. Three of them are loader refusals.
**Two are not, and checking found it:**

- **A euro cap with no `cost_param` loads perfectly well.** Nothing in
  `policy_loader.validate_policy` mentions it. The engine denies at DECISION time, in
  `caps._check_one`, with `CheckId.COST_UNKNOWN` and the reason *"no cost_param declared
  and the request carries no cost_eur"*. Showing it as a boot refusal would state a
  falsehood about the engine.
- **`strict_params` is not an authoring-time property at all.** It is a runtime bounds
  check: `bounds.check` rejects an unknown param **in a request**. A policy cannot
  violate it; a request can.

R058 §4 is the law that caught both: *check every phrase against the code that decides,
not the names that suggest.* A Studio that invented a boot refusal would be the second
validator wearing a warning's clothes.

## Every forecast names the code that will speak

R066 §3's requirement, and it is what keeps this list from being the Studio's opinion.
A forecast cites `CheckId` — the same vocabulary the audit row will carry — so an
operator who sees `cost_unknown` in the ledger next week can find the sentence that
predicted it. A forecast in the Studio's own paraphrase would be unfalsifiable; a
forecast naming a reason code is checkable against what the engine actually emits.

## The one that names a code by its silence

`EFFECT_FLOOR` is forecast for a **declared but inert** effect — a label the rule names
with no effect policy behind it. Here the code is what will *not* speak: the floor never
applies, the rule permits more than its author believes, and nothing in the ledger says
so. `coverage.DECLARED_INERT` is the existing detector and this is the same finding at
authoring time. The wording describes **today**; `ND-053` will turn this into a boot
refusal, and until it ships, saying so here would be describing tomorrow's engine —
`test_forecast_describes_today.py` holds the forbidden words.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from onedoor.guardrail import caps as caps_module
from onedoor.guardrail.models import CheckId, EffectPolicy, Policy

FORECAST_NOTICE = (
    "These are not refusals: the loader accepts every rule below. They describe how "
    "each rule will behave once it is in force, and each one names the reason code the "
    "engine will record."
)
"""Rendered wherever the forecast list is shown, including when it is empty.

The sibling of `validate.INCOMPLETE_NOTICE`, and it carries the heavier load: the risk
on this list is not incompleteness but misreading, because a warning that sits near a
refusal list gets read as a refusal.
"""

FORECASTS_ARE_NOT_COMPLETE = (
    "Only the behaviours this check knows how to predict are listed. A rule with no row "
    "here has not been shown to be free of surprises."
)

INERT_UNKNOWN = (
    "Effect coverage was not checked: the set of declared effect policies was not "
    "supplied to this check."
)
"""The third outcome for the inert-effect forecast.

Absent, unverifiable and failed stay apart. Without the declared-effect set this check
cannot tell an inert label from a covered one, and guessing would produce a warning
about a rule that is fine — which is how a reader learns to ignore the list.
"""


@dataclass(frozen=True)
class Forecast:
    """One thing a rule will do at decision time, and the reason code it will record."""

    action_type: str
    reason_code: str
    """A `CheckId` value. The audit vocabulary, not the Studio's."""

    message: str

    def to_object(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "reason_code": self.reason_code,
            "message": self.message,
        }


def _reached_effects(policy: Policy) -> set[str]:
    """Every effect this rule can reach — declared, plus any a param rule adds."""
    reached = set(policy.effects)
    for rule in policy.param_effects:
        reached |= set(rule.add_effects)
    return reached


def _declared_params(policy: Policy) -> list[str]:
    bounds = policy.bounds
    named = set(bounds.numeric) | set(bounds.enum) | set(bounds.required)
    if policy.cost_param:
        named.add(policy.cost_param)
    return sorted(named)


def build(
    policies: list[Policy] | tuple[Policy, ...],
    effects: list[EffectPolicy] | tuple[EffectPolicy, ...] = (),
    *,
    known_effects: set[str] | None = None,
) -> tuple[Forecast, ...]:
    """Forecast decision-time behaviour for a candidate.

    `known_effects` is the set of effect names that have an effect policy — the
    candidate's own plus whatever is already in force. When it is `None` the inert-effect
    forecast is **omitted entirely** rather than guessed: see `INERT_UNKNOWN`.
    """
    caps_by_effect = {e.effect: e.caps for e in effects}
    covered = set(known_effects) if known_effects is not None else None
    if covered is not None:
        covered |= set(caps_by_effect)

    out: list[Forecast] = []
    for policy in sorted(policies, key=lambda p: p.action_type):
        reached = _reached_effects(policy)

        # 1. A euro cap the engine cannot measure against. `_has_euro_cap` is the
        # engine's own predicate -- read the code that decides, not the column's name.
        euro_here = caps_module._has_euro_cap(policy.caps)
        euro_effects = sorted(
            name
            for name in reached
            if name in caps_by_effect and caps_module._has_euro_cap(caps_by_effect[name])
        )
        if (euro_here or euro_effects) and policy.cost_param is None:
            source = "this rule" if euro_here else f"effect '{euro_effects[0]}'"
            out.append(
                Forecast(
                    action_type=policy.action_type,
                    reason_code=CheckId.COST_UNKNOWN.value,
                    message=(
                        f"A euro cap applies (from {source}) and no cost_param is "
                        "declared, so the engine cannot resolve the amount from the "
                        "request's params. Every request that does not itself carry a "
                        "positive cost_eur is DENIED — an unknown amount is never "
                        "treated as zero."
                    ),
                )
            )

        # 2. strict_params: a runtime bounds rejection, stated as one.
        if policy.bounds.strict_params:
            named = _declared_params(policy)
            accepted = ", ".join(named) if named else "no parameters at all"
            out.append(
                Forecast(
                    action_type=policy.action_type,
                    reason_code=CheckId.BOUNDS.value,
                    message=(
                        f"strict_params is on, so a request carrying any parameter "
                        f"other than {accepted} is refused at decision time. This is a "
                        "property of requests, not of this rule — the loader accepts "
                        "the rule either way."
                    ),
                )
            )

        # 3. Declared but inert -- the code that will NOT speak.
        if covered is not None:
            for name in sorted(reached - covered):
                out.append(
                    Forecast(
                        action_type=policy.action_type,
                        reason_code=CheckId.EFFECT_FLOOR.value,
                        message=(
                            f"This rule names effect '{name}', and no effect policy "
                            "declares it. The effect floor does not apply: the label is "
                            "dropped and the rule permits more than its presence "
                            "suggests. Nothing in the ledger records that it was "
                            "dropped."
                        ),
                    )
                )
    return tuple(out)
