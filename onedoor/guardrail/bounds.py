"""Numeric/enum bounds validation of action params. Pure — no I/O."""

from __future__ import annotations

from dataclasses import dataclass

from onedoor.guardrail.models import Bounds, JsonValue
from onedoor.guardrail.numeric import numeric_refusal, numeric_value


@dataclass(frozen=True)
class BoundsResult:
    ok: bool
    detail: str = ""


def validate(bounds: Bounds, params: dict[str, JsonValue]) -> BoundsResult:
    """Validate ``params`` against ``bounds``. Returns the first failure found.

    Order: required-present -> unknown-param (if strict) -> numeric -> enum.
    """
    for key in bounds.required:
        if key not in params:
            return BoundsResult(False, f"missing required param '{key}'")

    if bounds.strict_params:
        allowed = set(bounds.numeric) | set(bounds.enum) | set(bounds.required)
        for key in params:
            if key not in allowed:
                return BoundsResult(False, f"unknown param '{key}' rejected (strict_params)")

    for key, bound in bounds.numeric.items():
        if key not in params:
            continue
        raw = params[key]
        # ND-054: one numeric_value(), shared with caps.resolve_cost, so declaring a
        # bound can never change which wire types an action accepts. Accepts int,
        # finite Decimal/float, and the decimal-string form ("40.00", AADP §5) --
        # never through float for strings, so the comparison below is exact.
        value = numeric_value(raw)
        if value is None:
            return BoundsResult(False, numeric_refusal(key, raw))
        if bound.min is not None and not value >= bound.min:
            return BoundsResult(False, f"param '{key}'={value} below min {bound.min}")
        if bound.max is not None and not value <= bound.max:
            return BoundsResult(False, f"param '{key}'={value} above max {bound.max}")

    for key, allowed_values in bounds.enum.items():
        # Absence is a value, not a skip: a param constrained to an allowlist that
        # is simply missing must not reach the allowed path because the policy
        # author forgot to repeat the key under `required`.
        if key not in params:
            return BoundsResult(False, f"param '{key}' is constrained but absent")
        enum_value = params[key]
        if enum_value not in allowed_values:
            return BoundsResult(False, f"param '{key}'={enum_value!r} not in whitelist")

    return BoundsResult(True)
