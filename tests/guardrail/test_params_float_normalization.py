"""0.12.1: `ActionRequest` normalises a float anywhere in
`params`, at any depth, to `Decimal(repr(value))` when the request is built,
and refuses NaN/infinity outright, naming the key -- before any decision
runs. Closes E10's own open question (models.py's `JsonValue` comment): a
raw float used to reach `approvals.resume_digest`/`approval_ref.canonical_params`
unconverted and raise `TypeError: floats are forbidden in canonical
structures` the moment either was asked to canonicalise it.

Ints, strings, Decimals, bools and None pass through exactly as given.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from onedoor.guardrail import approval_ref
from onedoor.guardrail.approvals import resume_digest
from onedoor.guardrail.models import ActionRequest, Source
from tests.conftest import FROZEN_NOW


def _request(params: dict) -> ActionRequest:
    return ActionRequest(
        request_id=uuid4(),
        action_type="demo.confirm",
        params=params,
        source=Source.UI,
        rationale="test",
        created_at=FROZEN_NOW,
    )


def test_a_top_level_float_becomes_a_decimal_with_the_same_text() -> None:
    req = _request({"amount_eur": 2400.0})
    assert req.params["amount_eur"] == Decimal("2400.0")
    assert isinstance(req.params["amount_eur"], Decimal)


def test_a_float_nested_in_a_dict_becomes_a_decimal() -> None:
    req = _request({"transfer": {"amount_eur": 2400.5}})
    value = req.params["transfer"]["amount_eur"]  # type: ignore[index]
    assert value == Decimal("2400.5")
    assert isinstance(value, Decimal)


def test_a_float_nested_in_a_list_becomes_a_decimal() -> None:
    req = _request({"installments": [100.0, 50.25]})
    values = req.params["installments"]
    assert values == [Decimal("100.0"), Decimal("50.25")]
    assert all(isinstance(v, Decimal) for v in values)  # type: ignore[union-attr]


def test_a_float_nested_several_levels_deep_still_normalises() -> None:
    req = _request({"a": {"b": [{"c": 1.5}, {"c": 2.5}]}})
    values = [item["c"] for item in req.params["a"]["b"]]  # type: ignore[index]
    assert values == [Decimal("1.5"), Decimal("2.5")]
    assert all(isinstance(v, Decimal) for v in values)


@pytest.mark.parametrize(
    "value",
    [1, "x", Decimal("3.14"), True, False, None],
    ids=["int", "str", "decimal", "true", "false", "none"],
)
def test_every_other_json_type_passes_through_unchanged(value: object) -> None:
    req = _request({"k": value})
    assert req.params["k"] == value
    assert type(req.params["k"]) is type(value)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_infinity_are_refused_naming_the_key(bad: float) -> None:
    with pytest.raises(ValueError, match=r"params\.amount"):
        _request({"amount": bad})


def test_nan_nested_in_a_list_is_refused_naming_the_full_path() -> None:
    with pytest.raises(ValueError, match=r"params\.installments\[1\]"):
        _request({"installments": [10.0, float("nan")]})


def test_a_float_valued_digest_is_stable_across_two_runs() -> None:
    req1 = _request({"amount_eur": 2400.0})
    req2 = _request({"amount_eur": 2400.0})
    assert resume_digest(req1.action_type, req1.params) == resume_digest(
        req2.action_type, req2.params
    )


def test_a_decimal_valued_digest_is_stable_across_two_runs() -> None:
    """Stands in for the HTTP body's own future "50.00" (0.13, parse_float=Decimal):
    a caller that already hands a Decimal must be exactly as stable as one that
    hands a float -- this fix must not depend on which boundary produced the value."""
    req1 = _request({"amount_eur": Decimal("50.00")})
    req2 = _request({"amount_eur": Decimal("50.00")})
    assert resume_digest(req1.action_type, req1.params) == resume_digest(
        req2.action_type, req2.params
    )


def test_canonical_params_no_longer_sees_a_raw_float() -> None:
    """approval_ref._canon refuses a raw float outright (E10); a request built
    through ActionRequest must never hand it one, whatever the caller passed in."""
    req = _request({"amount_eur": 2400.0, "legs": [{"amount_eur": 1.5}]})
    approval_ref.canonical_params(req.params)  # must not raise
