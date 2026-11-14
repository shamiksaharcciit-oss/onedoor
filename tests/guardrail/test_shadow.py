"""`onedoor.guardrail.shadow`: what a candidate policy would decide for a
request, read-only, never fed back into the live engine."""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

import pytest

from onedoor.guardrail import caps as caps_mod
from onedoor.guardrail import shadow
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    Bounds,
    CheckId,
    Decision,
    NumericBound,
    Policy,
    PolicyDecision,
    Tier,
)
from onedoor.guardrail.policy import PolicyStore
from tests.conftest import make_request


def _live(
    reason_code: CheckId,
    *,
    decision: Decision = Decision.DENIED,
    approvers: list[str] | None = None,
) -> PolicyDecision:
    """A minimal live `PolicyDecision` naming only the reason code (and,
    for a resumption, the approvers) these tests care about -- the
    comparison in `shadow.record` reads nothing else off it."""
    return PolicyDecision(
        decision=decision,
        effective_tier=Tier.CONFIRM,
        nominal_tier=Tier.CONFIRM,
        reason_code=reason_code,
        approvers=approvers,
    )


def test_evaluate_allows_a_tier1_action_within_bounds(
    conn: Connection, config: EngineConfig
) -> None:
    policy = Policy(action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    req = make_request("shadow.auto")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.EXECUTED
    assert result.effective_tier == Tier.AUTO
    assert result.reason_code is None


def test_evaluate_denies_default_deny(conn: Connection, config: EngineConfig) -> None:
    policy = Policy(action_type="shadow.unknown", tier=Tier.AUTO, is_default_deny=True)
    req = make_request("shadow.unknown")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.DENIED
    assert result.reason_code is not None
    assert result.reason_code.value == "default_deny"


def test_evaluate_denies_out_of_bounds(conn: Connection, config: EngineConfig) -> None:
    policy = Policy(
        action_type="shadow.bounded",
        tier=Tier.AUTO,
        bounds=Bounds(
            numeric={"amount": NumericBound(min=Decimal(0), max=Decimal(10))},
            strict_params=False,
        ),
    )
    req = make_request("shadow.bounded", {"amount": Decimal(50)})
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.DENIED
    assert result.reason_code is not None
    assert result.reason_code.value == "bounds"


def test_evaluate_denies_over_cap_and_reserves_nothing(
    conn: Connection, config: EngineConfig
) -> None:
    policy = PolicyStore().get(conn, "demo.capped")  # daily_rate=2
    req = make_request("demo.capped")
    caps_mod.check_and_reserve(conn, policy, req, req.created_at, config.tz)
    caps_mod.check_and_reserve(conn, policy, req, req.created_at, config.tz)
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.DENIED
    assert result.reason_code is not None
    assert result.reason_code.value == "rate_exhausted"
    row = conn.execute(
        "SELECT count FROM cap_counters WHERE action_type='demo.capped' AND window_kind='rate'"
    ).fetchone()
    assert row["count"] == 2  # unaffected by the shadow evaluation


def test_evaluate_proposes_a_confirm_tier_action(conn: Connection, config: EngineConfig) -> None:
    policy = PolicyStore().get(conn, "demo.confirm")
    req = make_request("demo.confirm")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.PROPOSED
    assert result.effective_tier == Tier.CONFIRM


def test_evaluate_denies_outright_when_the_kill_switch_is_engaged(
    conn: Connection, config: EngineConfig
) -> None:
    """Matches the live engine: an engaged switch denies a non-observe
    action outright, after bounds and before caps -- it does not propose,
    which would still fill the approval queue during an incident."""
    policy = Policy(action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    req = make_request("shadow.auto")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=True
    )
    assert result.decision == Decision.DENIED
    assert result.effective_tier == Tier.CONFIRM
    assert result.reason_code == CheckId.KILL_SWITCH


def test_evaluate_denies_outright_for_a_tier3_policy_too(
    conn: Connection, config: EngineConfig
) -> None:
    """The switch is why, even when the policy's own tier is already
    CONFIRM -- live sets `reason_confirm = KILL_SWITCH` in this case too,
    not `TIER_CONFIRM`, so this still denies rather than proposing."""
    policy = Policy(
        action_type="shadow.tier3", tier=Tier.CONFIRM, bounds=Bounds(strict_params=False)
    )
    req = make_request("shadow.tier3")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=True
    )
    assert result.decision == Decision.DENIED
    assert result.reason_code == CheckId.KILL_SWITCH


def test_evaluate_exempts_observe_tier_from_the_kill_switch(
    conn: Connection, config: EngineConfig
) -> None:
    policy = PolicyStore().get(conn, "demo.read")  # Tier.OBSERVE
    req = make_request("demo.read")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=True
    )
    assert result.decision == Decision.EXECUTED
    assert result.effective_tier == Tier.OBSERVE


def test_evaluate_returns_an_observe_read_before_bounds_would_deny_it(
    conn: Connection, config: EngineConfig
) -> None:
    """Live returns an OBSERVE read at step 5, before bounds (step 6) --
    matching `tests/mcp/test_sequence_gateway.py`'s own real gateway case,
    where a marked, undeclared parameter on a tier-0 read is let through by
    the live engine (reads never reach `strict_params`), but was wrongly
    denied here when bounds ran first."""
    policy = Policy(
        action_type="shadow.read",
        tier=Tier.OBSERVE,
        bounds=Bounds(required=["known"], strict_params=True),
    )
    req = make_request("shadow.read", {"unknown_param": "x"})
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.EXECUTED
    assert result.effective_tier == Tier.OBSERVE
    assert result.reason_code == CheckId.OBSERVE


def test_evaluate_touches_the_real_kill_switch_table_not_at_all(
    conn: Connection, config: EngineConfig
) -> None:
    """`kill_switch_engaged` is a caller-supplied fact, never read from the
    database here -- so passing `True` on a system whose real switch is off
    must not engage it, and must not even query the table."""
    policy = Policy(action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    req = make_request("shadow.auto")
    shadow.evaluate(conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=True)
    from onedoor.guardrail import killswitch

    assert killswitch.is_engaged(conn) is False


def test_record_persists_a_shadow_decision(conn: Connection, config: EngineConfig) -> None:
    policy = Policy(action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    req = make_request("shadow.auto")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    row_id = shadow.record(conn, req, result, policy_label="candidate-v2", now=req.created_at)
    row = conn.execute("SELECT * FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["request_id"] == str(req.request_id)
    assert row["action_type"] == "shadow.auto"
    assert row["policy_label"] == "candidate-v2"
    assert row["decision"] == "executed"
    assert row["effective_tier"] == int(Tier.AUTO)
    assert row["reason_code"] is None
    assert row["live_audit_id"] is None
    assert row["coverage"] == shadow.COVERAGE_ID
    assert row["live_reason_code"] is None
    assert row["comparison"] is None


def test_record_carries_the_denial_reason_and_detail(
    conn: Connection, config: EngineConfig
) -> None:
    policy = Policy(action_type="shadow.unknown", tier=Tier.AUTO, is_default_deny=True)
    req = make_request("shadow.unknown")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    row_id = shadow.record(conn, req, result, policy_label="candidate-v2", now=req.created_at)
    row = conn.execute("SELECT * FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["decision"] == "denied"
    assert row["reason_code"] == "default_deny"
    assert row["detail"] == "policy.is_default_deny == true"


def test_record_links_to_a_real_audit_row_when_given_one(
    conn: Connection, config: EngineConfig
) -> None:
    from onedoor.guardrail import audit
    from onedoor.guardrail.models import CheckId, PolicyDecision

    req = make_request("demo.read")
    decision = PolicyDecision(
        decision=Decision.EXECUTED,
        effective_tier=Tier.OBSERVE,
        nominal_tier=Tier.OBSERVE,
        reason_code=CheckId.KILL_SWITCH,
    )
    audit_id = audit.append(conn, req, decision, kind="decision", now=req.created_at)

    policy = Policy(action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    row_id = shadow.record(
        conn, req, result, policy_label="candidate-v2", now=req.created_at, live_audit_id=audit_id
    )
    row = conn.execute(
        "SELECT live_audit_id FROM shadow_decisions WHERE id=?", (row_id,)
    ).fetchone()
    assert row["live_audit_id"] == audit_id


# ---------------------------------------------------------------------------
# record() given a live decision beside the shadow verdict: comparison, never
# a bare agree/disagree for a path limits-v1 does not model.
# ---------------------------------------------------------------------------

_UNMODELED_REASON_CODES = [
    CheckId.EFFECT_FLOOR,
    CheckId.SEQUENCE_RULE,
    CheckId.SEQUENCE_NO_SESSION,
    CheckId.RESUME_REQUEST_MISMATCH,
    CheckId.EXPIRED,
    CheckId.EXTERNAL_AUTHORIZATION,
    CheckId.PRESENT_BOUND,
    CheckId.DRY_RUN,
    CheckId.NO_COMPENSATION,
    CheckId.SENDER_MISMATCH,
    CheckId.UNTRUSTED_INPUT,
    CheckId.MALFORMED,
    CheckId.PLAN_REF,
]


@pytest.mark.parametrize(
    "reason", _UNMODELED_REASON_CODES, ids=[r.value for r in _UNMODELED_REASON_CODES]
)
def test_record_marks_a_live_decision_from_an_unmodeled_path(
    conn: Connection, config: EngineConfig, reason: CheckId
) -> None:
    """A live decision whose own reason names a path limits-v1 does not
    check is marked as outside coverage -- never folded into agreement or
    disagreement with a check it was never put through."""
    policy = Policy(action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    req = make_request("shadow.auto")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    row_id = shadow.record(
        conn,
        req,
        result,
        policy_label="candidate-v2",
        now=req.created_at,
        live_decision=_live(reason),
    )
    row = conn.execute("SELECT * FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["live_reason_code"] == reason.value
    assert row["comparison"] == f"live decided by {reason.value}; not modeled"
    # the row still holds the SHADOW verdict, not the live one
    assert row["decision"] == result.decision.value


def test_record_marks_agreement_on_a_modeled_check(conn: Connection, config: EngineConfig) -> None:
    """The live engine executed a plain tier-1 action (reason `passed`) and
    the shadow policy, evaluated for the same request, also executes --
    that is agreement, on a check limits-v1 does model."""
    policy = Policy(action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    req = make_request("shadow.auto")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.EXECUTED
    row_id = shadow.record(
        conn,
        req,
        result,
        policy_label="candidate-v2",
        now=req.created_at,
        live_decision=_live(CheckId.PASSED, decision=Decision.EXECUTED),
    )
    row = conn.execute("SELECT * FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["comparison"] == "agree"


def test_record_marks_disagreement_on_a_modeled_check(
    conn: Connection, config: EngineConfig
) -> None:
    """The live engine denied for a bound the live policy enforces; the
    CANDIDATE policy under shadow evaluation has no such bound and
    executes -- both sides are talking about bounds (a modeled check), and
    they disagree."""
    candidate_policy = Policy(
        action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False)
    )
    req = make_request("shadow.auto", {"amount": Decimal(999)})
    result = shadow.evaluate(
        conn, candidate_policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.EXECUTED
    row_id = shadow.record(
        conn,
        req,
        result,
        policy_label="candidate-v2",
        now=req.created_at,
        live_decision=_live(CheckId.BOUNDS, decision=Decision.DENIED),
    )
    row = conn.execute("SELECT * FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["comparison"] == "disagree"


@pytest.mark.parametrize(
    "approvers",
    [["alice"], ["alice", "bob"], []],  # an approval; approval-ref; a mandate-only resumption
    ids=["approval", "approval_ref", "mandate"],
)
def test_record_marks_a_resumption_as_not_modeled_never_as_disagree(
    conn: Connection, config: EngineConfig, approvers: list[str]
) -> None:
    """A live approved, approval-ref, or mandate resumption of a Tier-3
    action executes with reason code `passed` -- in the modeled set. A
    shadow verdict that never modeled resumption at all (it always proposes
    a Tier-3 candidate, since it does not know an approval resumed it)
    would read this as `disagree` if the comparison looked at the reason
    code alone. `approvers` is never `None` on a decision that resumed one
    of these, even `[]` for a mandate-only resumption no human approver
    acted on -- that is the fact this must be marked "not modeled" from."""
    candidate_policy = Policy(
        action_type="shadow.confirm", tier=Tier.CONFIRM, bounds=Bounds(strict_params=False)
    )
    req = make_request("shadow.confirm")
    result = shadow.evaluate(
        conn, candidate_policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.PROPOSED  # shadow never resumes anything
    row_id = shadow.record(
        conn,
        req,
        result,
        policy_label="candidate-v2",
        now=req.created_at,
        live_decision=_live(CheckId.PASSED, decision=Decision.EXECUTED, approvers=approvers),
    )
    row = conn.execute("SELECT * FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["comparison"] == "live decided by passed; not modeled"


def test_record_reads_not_modeled_for_a_plain_string_reason_code(
    conn: Connection, config: EngineConfig
) -> None:
    """`PolicyDecision` itself refuses an unknown string once validated, so
    a plain `str` reason code (not a `CheckId` member) only reaches here
    through a construction that skips validation -- `model_construct`,
    here, standing in for whatever unvalidated path might produce one.
    Previously this raised `AttributeError` on `.value`; it must read
    "not modeled" instead, the same as any other reason this module has
    never heard of."""
    policy = Policy(action_type="shadow.auto", tier=Tier.AUTO, bounds=Bounds(strict_params=False))
    req = make_request("shadow.auto")
    result = shadow.evaluate(
        conn, policy, req, now=req.created_at, tz=config.tz, kill_switch_engaged=False
    )
    unvalidated = PolicyDecision.model_construct(
        decision=Decision.DENIED,
        effective_tier=Tier.CONFIRM,
        nominal_tier=Tier.CONFIRM,
        reason_code="not_a_real_check_id",
    )
    row_id = shadow.record(
        conn,
        req,
        result,
        policy_label="candidate-v2",
        now=req.created_at,
        live_decision=unvalidated,
    )
    row = conn.execute("SELECT * FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["live_reason_code"] == "not_a_real_check_id"
    assert row["comparison"] == "live decided by not_a_real_check_id; not modeled"
