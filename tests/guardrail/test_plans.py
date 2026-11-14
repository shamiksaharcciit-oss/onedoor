"""Approving a plan once: a plan replaces
exactly the approval step a nominal Tier-3 action would otherwise require,
and nothing else -- every other check still decides fully on its own merits.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from decimal import Decimal
from sqlite3 import Connection

import pytest

from onedoor.guardrail import killswitch, plan_ref, plans, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    Bounds,
    Caps,
    CheckId,
    Decision,
    Policy,
    SequencePolicy,
    SequenceRule,
    Source,
    Tier,
    UntrustedParams,
)
from onedoor.store.db import Database
from tests.conftest import FROZEN_NOW, make_request

PAY = "demo.plan_payment"
EXPIRES = FROZEN_NOW + timedelta(days=1)


def _policy(conn: Connection, **kw: object) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=PAY,
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(required=["amount_eur", "payee"], strict_params=False),
            cost_param="amount_eur",
            **kw,  # type: ignore[arg-type]
        ),
    )


def _propose_and_activate(
    conn: Connection,
    *,
    proposer: str = "alice",
    approver: str = "bob",
    count_ceiling: int = 2,
    amount_ceiling: Decimal = Decimal(1000),
    recipients: list[str] | None = None,
    expires_at: datetime = EXPIRES,
    action_specs: dict[str, object] | None = None,
) -> int:
    plan_id = plans.propose(
        conn,
        proposer,
        action_specs or {PAY: {"amount_param": "amount_eur", "recipient_param": "payee"}},
        count_ceiling,
        amount_ceiling,
        recipients or ["acme"],
        expires_at,
        FROZEN_NOW,
    )
    plans.approve(conn, plan_id, approver, FROZEN_NOW)
    return plan_id


def _request(plan_id: int, amount: object = Decimal("100"), payee: str = "acme") -> object:
    return make_request(PAY, {"amount_eur": amount, "payee": payee}, source=Source.LLM).model_copy(
        update={"plan_ref": plan_id}
    )


# --- the basic match ----------------------------------------------------------------


def test_a_call_inside_a_plans_ceilings_is_permitted_with_no_fresh_prompt(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn)
    result = decide_and_reserve(_request(plan_id), conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    assert result.plan_ref == plan_id
    assert result.plan_consumed_count_after == 1
    assert result.plan_consumed_amount_after == Decimal("100")

    row = conn.execute(
        "SELECT reason_code, plan_ref, plan_consumed_count_after, plan_consumed_amount_after "
        "FROM actions_audit WHERE id=?",
        (result.intent_audit_id,),
    ).fetchone()
    assert row["reason_code"] == "plan_ref"
    assert row["plan_ref"] == plan_id
    assert row["plan_consumed_count_after"] == 1
    assert row["plan_consumed_amount_after"] == "100"


def test_a_second_call_accumulates_against_the_same_plan(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn, count_ceiling=2, amount_ceiling=Decimal(1000))
    r1 = decide_and_reserve(
        _request(plan_id, Decimal("100")), conn=conn, config=config, now=FROZEN_NOW
    )
    assert isinstance(r1, PermittedIntent)
    r2 = decide_and_reserve(
        _request(plan_id, Decimal("200")),
        conn=conn,
        config=config,
        now=FROZEN_NOW + timedelta(seconds=1),
    )
    assert isinstance(r2, PermittedIntent)
    assert r2.plan_consumed_count_after == 2
    assert r2.plan_consumed_amount_after == Decimal("300")


# --- a plan is spent only by a call that is actually permitted ---------------------


def test_a_dry_run_with_a_matching_plan_leaves_the_plan_unspent(
    conn: Connection, config: EngineConfig
) -> None:
    """A dry run must say it would have matched, but never actually spend
    the plan -- the same "a rehearsal must not spend a real budget"
    reasoning this engine already applies to caps."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=PAY,
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(required=["amount_eur", "payee"], strict_params=False),
            cost_param="amount_eur",
        ),
    )
    plan_id = _propose_and_activate(conn)
    result = decide_and_reserve(
        _request(plan_id, Decimal("100")), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DRY_RUN
    assert result.decision.plan_ref == plan_id
    assert result.decision.plan_consumed_count_after == 1
    assert result.decision.plan_consumed_amount_after == Decimal("100")

    row = conn.execute(
        "SELECT consumed_count, consumed_amount FROM plans WHERE id=?", (plan_id,)
    ).fetchone()
    assert row["consumed_count"] == 0
    assert Decimal(str(row["consumed_amount"])) == Decimal(0)


def test_a_permitted_call_consumes_the_plan_exactly_once(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn)
    result = decide_and_reserve(
        _request(plan_id, Decimal("100")), conn=conn, config=config, now=FROZEN_NOW
    )
    assert isinstance(result, PermittedIntent)
    row = conn.execute(
        "SELECT consumed_count, consumed_amount FROM plans WHERE id=?", (plan_id,)
    ).fetchone()
    assert row["consumed_count"] == 1
    assert Decimal(str(row["consumed_amount"])) == Decimal("100")


# --- a non-positive or non-finite amount does not match, ever ----------------------


@pytest.mark.parametrize("bad_amount", [Decimal("-400"), Decimal("0")])
def test_a_non_positive_amount_does_not_match_and_leaves_the_plan_unspent(
    conn: Connection, config: EngineConfig, bad_amount: Decimal
) -> None:
    """A negative or zero amount must not match the plan at all -- letting
    one through would lower `consumed_amount`, spending back room a ceiling
    already granted rather than using any of it."""
    _policy(conn)
    plan_id = _propose_and_activate(conn)
    result = decide_and_reserve(
        _request(plan_id, bad_amount), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.plan_ref is None

    row = conn.execute(
        "SELECT consumed_count, consumed_amount FROM plans WHERE id=?", (plan_id,)
    ).fetchone()
    assert row["consumed_count"] == 0
    assert Decimal(str(row["consumed_amount"])) == Decimal(0)


# --- every way a call can fail to match, each falling back to ordinary approval ----


def test_over_the_amount_ceiling_falls_back_to_ordinary_approval(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn, amount_ceiling=Decimal("50"))
    result = decide_and_reserve(
        _request(plan_id, Decimal("100")), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.TIER_CONFIRM
    assert result.decision.plan_ref is None


def test_over_the_count_ceiling_falls_back_to_ordinary_approval(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn, count_ceiling=1)
    r1 = decide_and_reserve(_request(plan_id), conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(r1, PermittedIntent)
    r2 = decide_and_reserve(
        _request(plan_id), conn=conn, config=config, now=FROZEN_NOW + timedelta(seconds=1)
    )
    assert not isinstance(r2, PermittedIntent)
    assert r2.decision.decision == Decision.PROPOSED
    assert r2.decision.reason_code == CheckId.TIER_CONFIRM


def test_an_unlisted_recipient_falls_back_to_ordinary_approval(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn, recipients=["acme"])
    result = decide_and_reserve(
        _request(plan_id, payee="someone-else"), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED


def test_a_call_missing_the_plans_own_declared_param_falls_back(
    conn: Connection, config: EngineConfig
) -> None:
    """`payee` is declared as the plan's own `recipient_param`, but bounds
    does not require it on this policy -- a call omitting it entirely must
    fail to MATCH the plan (not fail bounds), and fall back to ordinary
    Tier-3 approval."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=PAY,
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(required=["amount_eur"], strict_params=False),
            cost_param="amount_eur",
        ),
    )
    plan_id = _propose_and_activate(conn)
    req = make_request(PAY, {"amount_eur": Decimal("10")}).model_copy(update={"plan_ref": plan_id})
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.plan_ref is None


def test_an_expired_plan_falls_back_to_ordinary_approval(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn, expires_at=FROZEN_NOW + timedelta(seconds=1))
    result = decide_and_reserve(
        _request(plan_id), conn=conn, config=config, now=FROZEN_NOW + timedelta(seconds=2)
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED


def test_an_action_type_the_plan_does_not_name_falls_back(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.plan_other",
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(strict_params=False),
        ),
    )
    plan_id = _propose_and_activate(conn)
    req = make_request("demo.plan_other", {}).model_copy(update={"plan_ref": plan_id})
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED


def test_an_unknown_plan_ref_evaluates_as_absent_not_an_error(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    req = make_request(PAY, {"amount_eur": Decimal("10"), "payee": "acme"}).model_copy(
        update={"plan_ref": 999999}
    )
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED


# --- a plan replaces exactly the approval step, nothing else -----------------------


def test_a_call_inside_a_plan_is_still_denied_by_bounds(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn)
    req = make_request(PAY, {"amount_eur": Decimal("10")}).model_copy(  # missing "payee"
        update={"plan_ref": plan_id}
    )
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.BOUNDS


def test_a_call_inside_a_plan_is_still_denied_by_a_cap(
    conn: Connection, config: EngineConfig
) -> None:
    """A call that matches a plan but is then denied by caps must not spend
    the plan either -- the match alone is not enough; only a call that is
    actually permitted may consume it."""
    _policy(conn, caps=Caps(eur_day=Decimal("50")))
    plan_id = _propose_and_activate(conn, amount_ceiling=Decimal(1000))
    result = decide_and_reserve(
        _request(plan_id, Decimal("100")), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.BUDGET_EXHAUSTED
    row = conn.execute(
        "SELECT consumed_count, consumed_amount FROM plans WHERE id=?", (plan_id,)
    ).fetchone()
    assert row["consumed_count"] == 0
    assert Decimal(str(row["consumed_amount"])) == Decimal(0)


def test_a_call_inside_a_plan_is_still_denied_by_the_kill_switch(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = _propose_and_activate(conn)
    killswitch.set_engaged(conn, True)
    result = decide_and_reserve(_request(plan_id), conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.KILL_SWITCH


def test_a_call_inside_a_plan_is_still_denied_by_an_untrusted_input_check(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn, untrusted_params=UntrustedParams(deny=["payee"]))
    plan_id = _propose_and_activate(conn)
    req = _request(plan_id).model_copy(update={"untrusted": ["payee"]})  # type: ignore[attr-defined]
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.UNTRUSTED_INPUT


def test_a_call_inside_a_plan_is_still_denied_by_a_sequence_rule(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(
        conn,
        sequence=SequencePolicy(
            rules=[
                SequenceRule(
                    count_over={
                        "action_type": PAY,
                        "max_count": 0,
                        "within_seconds": 86400,
                    },
                    effect="deny",
                )
            ]
        ),
    )
    plan_id = _propose_and_activate(conn)
    req = _request(plan_id).model_copy(update={"session_id": "s-plan"})  # type: ignore[attr-defined]
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.SEQUENCE_RULE


def test_a_plan_match_still_meets_its_own_session_requirement(
    conn: Connection, config: EngineConfig
) -> None:
    """A call inside a plan still meets the sequence feature's own session
    requirement: with no `session_id` presented and `sequence.rules` non-
    empty, `SEQUENCE_NO_SESSION` fires before the plan is ever consulted --
    the plan gate only applies when the sole reason for the approval step
    is the action's own nominal tier, and `SEQUENCE_NO_SESSION` is a
    different reason."""
    _policy(
        conn,
        sequence=SequencePolicy(
            rules=[
                SequenceRule(
                    count_over={
                        "action_type": PAY,
                        "max_count": 5,
                        "within_seconds": 86400,
                    },
                    effect="hold",
                )
            ]
        ),
    )
    plan_id = _propose_and_activate(conn)
    result = decide_and_reserve(_request(plan_id), conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.SEQUENCE_NO_SESSION
    assert result.decision.plan_ref is None


# --- concurrency: the compare-and-swap path -----------------------------------------


def test_two_calls_racing_a_near_exhausted_ceiling_never_both_succeed(tmp_path) -> None:  # noqa: ANN001
    db_path = str(tmp_path / "race.db")
    database = Database(db_path)
    database.init()
    setup_conn = database.connect()
    _policy(setup_conn)
    plan_id = plans.propose(
        setup_conn,
        "alice",
        {PAY: {"amount_param": "amount_eur", "recipient_param": "payee"}},
        count_ceiling=1,
        amount_ceiling=Decimal(1000),
        recipients=["acme"],
        expires_at=EXPIRES,
        now=FROZEN_NOW,
    )
    plans.approve(setup_conn, plan_id, "bob", FROZEN_NOW)
    setup_conn.close()

    from zoneinfo import ZoneInfo

    config = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC")
    )

    results: list[object] = []
    lock = threading.Lock()

    def _attempt() -> None:
        conn = database.connect()
        try:
            result = decide_and_reserve(_request(plan_id), conn=conn, config=config, now=FROZEN_NOW)
        finally:
            conn.close()
        with lock:
            results.append(result)

    threads = [threading.Thread(target=_attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    permitted = [r for r in results if isinstance(r, PermittedIntent)]
    assert len(permitted) == 1, "exactly one of the two racing calls must consume the plan"


# --- the propose/approve/deny lifecycle itself --------------------------------------


def test_propose_creates_a_proposal_not_an_active_plan(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "amount_eur", "recipient_param": "payee"}},
        1,
        Decimal(100),
        ["acme"],
        EXPIRES,
        FROZEN_NOW,
    )
    row = conn.execute("SELECT state FROM plans WHERE id=?", (plan_id,)).fetchone()
    assert row["state"] == "proposed"

    result = decide_and_reserve(_request(plan_id), conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED, "a mere proposal must not be matchable"


def test_the_proposer_cannot_approve_their_own_plan(conn: Connection) -> None:
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {}},
        1,
        Decimal(100),
        ["acme"],
        EXPIRES,
        FROZEN_NOW,
    )
    with pytest.raises(ApprovalError):
        plans.approve(conn, plan_id, "alice", FROZEN_NOW)


def test_approving_an_already_active_plan_fails(conn: Connection) -> None:
    plan_id = _propose_and_activate(conn)
    with pytest.raises(ApprovalError):
        plans.approve(conn, plan_id, "carol", FROZEN_NOW)


def test_a_denied_proposal_never_becomes_matchable(conn: Connection, config: EngineConfig) -> None:
    _policy(conn)
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "amount_eur", "recipient_param": "payee"}},
        1,
        Decimal(1000),
        ["acme"],
        EXPIRES,
        FROZEN_NOW,
    )
    plans.deny(conn, plan_id, "bob", FROZEN_NOW)
    result = decide_and_reserve(_request(plan_id), conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED


# --- parity -------------------------------------------------------------------------


def test_a_policy_with_no_plan_ever_presented_decides_identically_to_0_10_x(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    req = make_request(PAY, {"amount_eur": Decimal("10"), "payee": "acme"})
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.TIER_CONFIRM
    assert result.decision.plan_ref is None


# --- the resolution module's own anti-probing shape ---------------------------------


def test_resolve_match_returns_none_for_a_plan_ref_outside_the_store_range(
    conn: Connection,
) -> None:
    assert (
        plan_ref.resolve_match(conn, plan_ref=2**63, request=make_request(PAY, {}), now=FROZEN_NOW)
        is None
    )
    assert (
        plan_ref.resolve_match(conn, plan_ref=None, request=make_request(PAY, {}), now=FROZEN_NOW)
        is None
    )
