"""Numeric/enum bounds validation of action params. Pure — no I/O."""

from __future__ import annotations

from dataclasses import dataclass

from onedoor.guardrail.models import Bounds, JsonValue


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
        value = params[key]
        if not isinstance(value, int | float) or isinstance(value, bool):
            return BoundsResult(False, f"param '{key}' must be numeric")
        if bound.min is not None and value < bound.min:
            return BoundsResult(False, f"param '{key}'={value} below min {bound.min}")
        if bound.max is not None and value > bound.max:
            return BoundsResult(False, f"param '{key}'={value} above max {bound.max}")

    for key, allowed_values in bounds.enum.items():
        if key not in params:
            continue
        value = params[key]
        if value not in allowed_values:
            return BoundsResult(False, f"param '{key}'={value!r} not in whitelist")

    return BoundsResult(True)
