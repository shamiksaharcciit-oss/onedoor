"""README.md's own empirical claims about numeric bounds, checked against the code."""

from __future__ import annotations

from pathlib import Path

from onedoor.guardrail.bounds import validate
from onedoor.guardrail.models import Bounds, NumericBound
from onedoor.guardrail.numeric import parse_numeric

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"


def _known_limitations_section() -> str:
    text = README.read_text(encoding="utf-8")
    return text.split("## Known limitations", 1)[1].split("\n## ", 1)[0]


def test_readme_names_the_three_values_its_decimal_string_claim_rests_on() -> None:
    section = _known_limitations_section()
    for literal in ('"40.00"', '"abc"', '"1e3"'):
        assert literal in section, (
            f"README's Known limitations no longer names {literal} -- "
            "the claim this test checks has moved or been reworded"
        )


def test_a_decimal_string_under_a_numeric_bound_is_accepted_exactly_as_the_readme_says() -> None:
    """README.md, Known limitations: '`{"amount_eur": "40.00"}` is permitted,
    exactly like `{"amount_eur": 40.00}`'."""
    parsed = parse_numeric("40.00")
    assert parsed.value is not None
    assert parsed.value == parse_numeric(40.00).value


def test_garbage_and_exponent_notation_are_both_refused_with_bounds_as_the_readme_says() -> None:
    """README.md, Known limitations: both are refused with
    `"decision":"denied","reason":"bounds"`, detail "param 'amount_eur' must
    be numeric: ...". A caller never sees the parser's own internal reason
    (`not_numeric`) -- `bounds.validate`'s own `detail` is exactly what
    `decision.py`'s step 6 copies into the reply (`reason_code=CheckId.BOUNDS,
    detail=bounds_result.detail`), so this holds the reply itself, not the
    parser underneath it."""
    bounds = Bounds(numeric={"amount_eur": NumericBound(min=0.01, max=2000.00)})
    for value in ("abc", "1e3"):
        result = validate(bounds, {"amount_eur": value})
        assert result.ok is False
        assert result.detail is not None
        assert "must be numeric" in result.detail
        assert repr(value) in result.detail
