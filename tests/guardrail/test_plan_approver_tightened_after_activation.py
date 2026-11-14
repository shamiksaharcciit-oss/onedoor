"""A policy tightened after a plan already activated must not let
that plan go on matching at the approver count it merely had -- the same
stricter-of-two-reads rule already applies at a plan's own
approval, extended here to match time. The report's reproduction: a plan
activates with one approver while its covered action needs only one below
1000; the threshold then drops to 100, so the plan's own 800-euro ceiling
would need two approvers under the policy as it reads now -- it must stop
matching, not keep spending at the one approver it already had.
"""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

from onedoor.guardrail import plans, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ApprovalPolicy, Bounds, Decision, Policy, Tier
from tests.conftest import FROZEN_NOW, make_request

PAY = "demo.plan_tightened"


def _policy(conn: Connection, *, two_person_above_eur: Decimal) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=PAY,
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(required=["amount_eur", "payee"], strict_params=False),
            cost_param="amount_eur",
            approval=ApprovalPolicy(two_person_above_eur=two_person_above_eur),
        ),
    )


def test_a_plan_that_activated_with_one_approver_stops_matching_once_tightened(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn, two_person_above_eur=Decimal("1000"))
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "amount_eur", "recipient_param": "payee"}},
        count_ceiling=10,
        amount_ceiling=Decimal("800"),
        recipients=["acme"],
        expires_at=FROZEN_NOW.replace(year=FROZEN_NOW.year + 1),
        now=FROZEN_NOW,
    )
    plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    row = conn.execute("SELECT state FROM plans WHERE id=?", (plan_id,)).fetchone()
    assert row["state"] == "active"

    _policy(conn, two_person_above_eur=Decimal("100"))

    result = decide_and_reserve(
        make_request(PAY, {"amount_eur": Decimal("150"), "payee": "acme"}).model_copy(
            update={"plan_ref": plan_id}
        ),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.plan_ref is None

    spent = conn.execute(
        "SELECT consumed_count, consumed_amount FROM plans WHERE id=?", (plan_id,)
    ).fetchone()
    assert spent["consumed_count"] == 0
    assert Decimal(str(spent["consumed_amount"])) == Decimal(0)


def test_an_untightened_plan_still_matches_normally(conn: Connection, config: EngineConfig) -> None:
    _policy(conn, two_person_above_eur=Decimal("1000"))
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "amount_eur", "recipient_param": "payee"}},
        count_ceiling=10,
        amount_ceiling=Decimal("800"),
        recipients=["acme"],
        expires_at=FROZEN_NOW.replace(year=FROZEN_NOW.year + 1),
        now=FROZEN_NOW,
    )
    plans.approve(conn, plan_id, "bob", FROZEN_NOW)

    result = decide_and_reserve(
        make_request(PAY, {"amount_eur": Decimal("150"), "payee": "acme"}).model_copy(
            update={"plan_ref": plan_id}
        ),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)
    assert result.plan_ref == plan_id
