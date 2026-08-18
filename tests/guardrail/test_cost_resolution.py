"""F7: a euro cap is only a budget if the engine can learn the amount.

Euro caps were evaluated against `request.cost_eur`. Nothing derived that from
the action's parameters, and the LangGraph tool wrapper shipped in `examples/`
-- the one `docs/integration-langgraph.md` tells people to use -- never set it.
Every request therefore declared a cost of zero, every euro cap compared
0 + 0 > limit, and every payment passed. No error, no warning, and an audit
trail that looked correct.

The fix has two halves and both are load-bearing:
  * policy declares `cost_param`, so the amount comes from the trusted input
  * an amount that cannot be resolved is a denial, never an assumed zero
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    CheckId,
    Decision,
    NumericBound,
    Policy,
    Source,
    Tier,
)
from onedoor.store.clock import now_utc
from onedoor.store.db import Connection

PAY = "test.pay"


def _policy(*, cost_param: str | None, eur_day: str | None = "500.00") -> Policy:
    return Policy(
        action_type=PAY,
        tier=Tier.AUTO_CAPPED,
        dry_run=False,
        compensating_command="test.refund",
        cost_param=cost_param,
        caps=Caps(eur_day=Decimal(eur_day) if eur_day else None),
        bounds=Bounds(
            numeric={"amount_eur": NumericBound(min=0.01, max=100)},
            required=["amount_eur"],
            strict_params=True,
        ),
    )


def _refund_policy() -> Policy:
    return Policy(
        action_type="test.refund",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="test.refund",
        bounds=Bounds(strict_params=False),
    )


def _request(amount: float | str | None, *, cost_eur: Decimal = Decimal(0)) -> ActionRequest:
    params: dict = {} if amount is None else {"amount_eur": amount}
    return ActionRequest(
        request_id=uuid4(), action_type=PAY, params=params, source=Source.LLM,
        rationale="test", cost_eur=cost_eur, created_at=now_utc(),
    )


def _cfg() -> EngineConfig:
    from zoneinfo import ZoneInfo

    return EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=1.0, tz=ZoneInfo("UTC")
    )


def _load(conn: Connection, policy: Policy) -> None:
    policy_loader.upsert(conn, _refund_policy())
    policy_loader.upsert(conn, policy)


def _decide(conn: Connection, request: ActionRequest):
    return decide_and_reserve(request, conn=conn, config=_cfg(), now=now_utc())


def test_declared_cost_param_enforces_a_cumulative_budget(conn: Connection) -> None:
    """The defect itself: six compliant payments against a 500 cap."""
    _load(conn, _policy(cost_param="amount_eur"))
    permitted = 0
    for _ in range(6):
        outcome = _decide(conn, _request(99.00))
        if not hasattr(outcome, "decision") or outcome.decision.decision != Decision.DENIED:
            permitted += 1
    assert permitted == 5, "5 x 99.00 = 495 fits; the sixth must not"


def test_unresolvable_amount_denies_rather_than_assuming_zero(conn: Connection) -> None:
    """No cost_param and no cost_eur: the exact configuration that was silent."""
    _load(conn, _policy(cost_param=None))
    outcome = _decide(conn, _request(99.00))  # amount is in params, undeclared
    assert outcome.decision.decision == Decision.DENIED
    assert outcome.decision.reason_code == CheckId.COST_UNKNOWN


def test_absent_declared_param_denies(conn: Connection) -> None:
    _load(conn, _policy(cost_param="amount_eur"))
    outcome = _decide(conn, _request(None))
    assert outcome.decision.decision == Decision.DENIED


def test_non_numeric_amount_denies(conn: Connection) -> None:
    _load(conn, _policy(cost_param="amount_eur"))
    outcome = _decide(conn, _request("not-a-number"))
    assert outcome.decision.decision == Decision.DENIED


def test_explicit_cost_eur_still_works_without_cost_param(conn: Connection) -> None:
    """Back-compat: callers that compute the cost themselves are unaffected."""
    _load(conn, _policy(cost_param=None))
    outcome = _decide(conn, _request(99.00, cost_eur=Decimal("99.00")))
    assert not hasattr(outcome, "decision") or \
        outcome.decision.decision != Decision.DENIED


def test_no_euro_cap_means_no_cost_needed(conn: Connection) -> None:
    """An action without a euro cap must not start failing for want of an amount."""
    _load(conn, _policy(cost_param=None, eur_day=None))
    outcome = _decide(conn, _request(99.00))
    assert not hasattr(outcome, "decision") or \
        outcome.decision.decision != Decision.DENIED


def test_cost_param_must_be_required(conn: Connection) -> None:
    """A parameter that may be absent is not a source of truth for money."""
    bad = Policy(
        action_type=PAY, tier=Tier.AUTO_CAPPED, dry_run=False,
        compensating_command="test.refund", cost_param="amount_eur",
        caps=Caps(eur_day=Decimal("500.00")),
        bounds=Bounds(numeric={"amount_eur": NumericBound(min=0.01, max=100)}),
    )
    with pytest.raises(ValueError, match="bounds.required"):
        policy_loader.validate_policy(bad)
