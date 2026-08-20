"""Regressions for defects found by ScopeGate's adversarial bypass suite.

Source of the vectors: `tests/test_bypass.py` in scopegate-runtime
(David Mellafe Zuvic, Apache-2.0), the artifact of arXiv:2606.28679. Running that
suite against onedoor surfaced four issues; these tests pin the fixes.

F1  NaN passed the numeric bounds check, because the negative comparison form
    (`value < min` / `value > max`) is False for NaN. Same defect the ScopeGate
    author found and fixed in his own prototype.
F2  A param constrained by an enum allowlist but absent from `params` was skipped,
    so safe behaviour depended on the author repeating the key under `required`.
F3  `bytes` params were coerced to `str` before validation, so the PDP validated
    and audited a different object from the one the PEP holds.
F4  `decide_and_reserve` raised on a malformed request instead of denying, moving
    the fail-closed guarantee out of the decision point and into each caller.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from sqlite3 import Connection
from uuid import UUID, uuid4

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.bounds import validate
from onedoor.guardrail.decision import NIL_REQUEST_ID, PermittedIntent, decide_raw
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    CheckId,
    NumericBound,
    Policy,
    Source,
    Tier,
)
from tests.conftest import FROZEN_NOW

MONEY = Bounds(numeric={"amount": NumericBound(min=0, max=100_000)}, strict_params=False)


# --- F1: NaN and infinities are not finite amounts -------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_f1_non_finite_amount_denied(bad: float) -> None:
    assert not validate(MONEY, {"amount": bad}).ok


def test_f1_one_sided_bound_still_rejects_infinity() -> None:
    """With only a min set, the old form left the max direction unguarded."""
    one_sided = Bounds(numeric={"amount": NumericBound(min=0)}, strict_params=False)
    assert not validate(one_sided, {"amount": float("inf")}).ok


def test_f1_finite_values_still_pass() -> None:
    assert validate(MONEY, {"amount": 10}).ok
    assert validate(MONEY, {"amount": 0}).ok
    assert validate(MONEY, {"amount": 100_000}).ok


# --- F2: absence is a value, not a skip ------------------------------------


def test_f2_absent_enum_param_denied_without_required() -> None:
    bounds = Bounds(enum={"account": ["acct_MERCHANT_001"]}, required=[], strict_params=False)
    assert not validate(bounds, {}).ok


def test_f2_present_allowed_enum_value_passes() -> None:
    bounds = Bounds(enum={"account": ["acct_MERCHANT_001"]}, required=[], strict_params=False)
    assert validate(bounds, {"account": "acct_MERCHANT_001"}).ok


# --- F3: no silent coercion of non-JSON param types ------------------------


@pytest.mark.parametrize("bad", [b"acct_MERCHANT_001", bytearray(b"x"), {"acct"}, ("a",)])
def test_f3_non_json_param_rejected(bad: object) -> None:
    with pytest.raises(ValueError):
        ActionRequest(
            request_id=uuid4(),
            action_type="demo.read",
            params={"account": bad},  # type: ignore[dict-item]
            source=Source.LLM,
            rationale="regression",
            created_at=FROZEN_NOW,
        )


def test_f3_nested_non_json_param_rejected() -> None:
    with pytest.raises(ValueError):
        ActionRequest(
            request_id=uuid4(),
            action_type="demo.read",
            params={"outer": {"inner": [b"x"]}},  # type: ignore[dict-item]
            source=Source.LLM,
            rationale="regression",
            created_at=FROZEN_NOW,
        )


# --- F4: a malformed request is denied, not raised -------------------------


def _seed(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="regress.payout",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="regress.restore",
            bounds=Bounds(
                enum={"account": ["acct_MERCHANT_001"]},
                required=["account"],
                strict_params=True,
            ),
        ),
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"request_id": "not-a-uuid", "action_type": "regress.payout"},
        {"action_type": "regress.payout"},  # missing required envelope fields
        "not-a-mapping-at-all",
        {"request_id": str(uuid4()), "action_type": None},
    ],
)
def test_f4_malformed_request_denies(conn: Connection, config: object, raw: object) -> None:
    _seed(conn)
    result = decide_raw(raw, conn=conn, config=config, now=FROZEN_NOW)  # type: ignore[arg-type]
    assert not isinstance(result, PermittedIntent)
    assert result.decision.reason_code is CheckId.MALFORMED
    assert result.decision.effective_tier is Tier.CONFIRM


def test_f4_malformed_echoes_request_id_when_parseable(conn: Connection, config: object) -> None:
    _seed(conn)
    rid = uuid4()
    result = decide_raw(
        {"request_id": str(rid), "action_type": 12345},
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(result, PermittedIntent)
    assert result.request_id == rid


def test_f4_unparseable_request_id_becomes_nil(conn: Connection, config: object) -> None:
    _seed(conn)
    result = decide_raw({"request_id": "???"}, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.request_id == NIL_REQUEST_ID
    assert result.request_id == UUID(int=0)


def test_f4_well_formed_request_still_permitted(conn: Connection, config: object) -> None:
    _seed(conn)
    result = decide_raw(
        {
            "request_id": str(uuid4()),
            "action_type": "regress.payout",
            "params": {"account": "acct_MERCHANT_001"},
            "source": "llm",
            "rationale": "regression positive control",
            "cost_eur": Decimal(0),
            "created_at": FROZEN_NOW,
        },
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent), "positive control must still permit"


def test_f4_internal_errors_are_not_swallowed(conn: Connection, config: object) -> None:
    """Deliberate divergence from ScopeGate's catch-all: a bug must not look like a denial."""
    _seed(conn)
    raw = {
        "request_id": str(uuid4()),
        "action_type": "regress.payout",
        "params": {"account": "acct_MERCHANT_001"},
        "source": "llm",
        "rationale": "internal failure probe",
        "created_at": FROZEN_NOW,
    }

    class Exploding:
        def get(self, *_: object, **__: object) -> None:
            raise RuntimeError("policy store is down")

    with pytest.raises(RuntimeError):
        decide_raw(
            raw,
            conn=conn,
            config=config,
            now=datetime.fromisoformat(FROZEN_NOW.isoformat()),
            policy_store=Exploding(),  # type: ignore[arg-type]
        )


# --- F5: reversibility precondition covers every auto-executing tier -------
# Found by the Stage 2 multi-call experiment, not by the bypass suite: an
# irreversible action escaped human approval merely because it also carried a
# budget, since the check was scoped to Tier.AUTO alone.


def _seed_irreversible(conn: Connection, tier: Tier) -> str:
    action = f"regress.irrev_{int(tier)}"
    policy_loader.upsert(
        conn,
        Policy(
            action_type=action,
            tier=tier,
            dry_run=False,
            compensating_command=None,  # no registered means of reversal
            bounds=Bounds(strict_params=False),
        ),
    )
    return action


@pytest.mark.parametrize("tier", [Tier.AUTO, Tier.AUTO_CAPPED])
def test_f5_irreversible_policy_rejected_at_load(conn: Connection, tier: Tier) -> None:
    """Fail early: an auto-executing policy with no reversal must not load at all."""
    with pytest.raises(ValueError, match="no reversal"):
        _seed_irreversible(conn, tier)


def test_f5_irreversible_never_auto_executes(conn: Connection, config: object) -> None:
    """Defence in depth: even if such a policy reaches the table, decide escalates.

    Written directly to the policy table, bypassing the loader, because the loader
    now refuses it — the runtime check must not rely on the loader having run.
    """
    tier = Tier.AUTO_CAPPED
    action = "regress.irrev_direct"
    conn.execute(
        "INSERT INTO policies (action_type, tier, bounds_json, caps_json, dry_run, "
        "dry_run_until, compensating_command, undo_window_seconds, requires_step_up, "
        "updated_at, effects_json, param_effects_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (action, int(tier), "{}", "{}", 0, None, None, 900, 0, FROZEN_NOW.isoformat(), "[]", "[]"),
    )
    conn.commit()
    result = decide_raw(
        {
            "request_id": str(uuid4()),
            "action_type": action,
            "params": {},
            "source": "llm",
            "rationale": "irreversible probe",
            "created_at": FROZEN_NOW,
        },
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(result, PermittedIntent), (
        f"tier {tier!r} auto-executed an action with no means of reversal"
    )
    assert result.decision.reason_code is CheckId.NO_COMPENSATION
    assert result.decision.effective_tier is Tier.CONFIRM


@pytest.mark.parametrize("tier", [Tier.AUTO, Tier.AUTO_CAPPED])
def test_f5_reversible_action_still_permitted(conn: Connection, config: object, tier: Tier) -> None:
    action = f"regress.rev_{int(tier)}"
    policy_loader.upsert(
        conn,
        Policy(
            action_type=action,
            tier=tier,
            dry_run=False,
            compensating_command=f"{action}.undo",
            bounds=Bounds(strict_params=False),
        ),
    )
    result = decide_raw(
        {
            "request_id": str(uuid4()),
            "action_type": action,
            "params": {},
            "source": "llm",
            "rationale": "positive control",
            "created_at": FROZEN_NOW,
        },
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent), "reversible action must still permit"
