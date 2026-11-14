"""A design requirement on top of the general two-person rule
(`onedoor.guardrail.approvals`): a plan whose `amount_ceiling` crosses the
two-person threshold of at least one of its own covered actions needs a
second, different approver, neither the proposer, before it activates.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from sqlite3 import Connection

import pytest

from onedoor.guardrail import plans, policy_loader
from onedoor.guardrail.errors import ApprovalError, NeedsMoreApprovers
from onedoor.guardrail.models import ApprovalPolicy, Bounds, Policy, Tier
from tests.conftest import FROZEN_NOW

PAY = "demo.plan_two_person"
EXPIRES = FROZEN_NOW + timedelta(days=1)


def _policy(conn: Connection, *, two_person_above_eur: Decimal | None) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=PAY,
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(required=["amount_eur", "payee"], strict_params=False),
            cost_param="amount_eur",
            approval=(
                ApprovalPolicy(two_person_above_eur=two_person_above_eur)
                if two_person_above_eur is not None
                else None
            ),
        ),
    )


def _propose(conn: Connection, *, amount_ceiling: Decimal, proposer: str = "alice") -> int:
    return plans.propose(
        conn,
        proposer,
        {PAY: {"amount_param": "amount_eur", "recipient_param": "payee"}},
        2,
        amount_ceiling,
        ["acme"],
        EXPIRES,
        FROZEN_NOW,
    )


def _state(conn: Connection, plan_id: int) -> str:
    return str(conn.execute("SELECT state FROM plans WHERE id=?", (plan_id,)).fetchone()[0])


def test_a_plan_above_its_actions_threshold_needs_two_approvers(conn: Connection) -> None:
    _policy(conn, two_person_above_eur=Decimal("500"))
    plan_id = _propose(conn, amount_ceiling=Decimal("1000"))

    with pytest.raises(NeedsMoreApprovers):
        plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    assert _state(conn, plan_id) == "proposed"

    plans.approve(conn, plan_id, "carol", FROZEN_NOW)
    assert _state(conn, plan_id) == "active"


def test_a_plan_below_the_threshold_needs_only_one(conn: Connection) -> None:
    _policy(conn, two_person_above_eur=Decimal("500"))
    plan_id = _propose(conn, amount_ceiling=Decimal("100"))  # below 500
    plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    assert _state(conn, plan_id) == "active"


def test_a_plan_whose_action_declares_no_approval_block_is_unaffected(conn: Connection) -> None:
    _policy(conn, two_person_above_eur=None)
    plan_id = _propose(conn, amount_ceiling=Decimal("999999"))
    plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    assert _state(conn, plan_id) == "active"


def test_the_proposer_still_cannot_approve_their_own_two_person_plan(conn: Connection) -> None:
    _policy(conn, two_person_above_eur=Decimal("500"))
    plan_id = _propose(conn, amount_ceiling=Decimal("1000"), proposer="alice")
    with pytest.raises(ApprovalError, match="proposed"):
        plans.approve(conn, plan_id, "alice", FROZEN_NOW)


def test_the_same_identity_approving_a_plan_twice_does_not_count_as_two(
    conn: Connection,
) -> None:
    _policy(conn, two_person_above_eur=Decimal("500"))
    plan_id = _propose(conn, amount_ceiling=Decimal("1000"))
    with pytest.raises(NeedsMoreApprovers):
        plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    with pytest.raises(ApprovalError, match="already approved"):
        plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    assert _state(conn, plan_id) == "proposed"


# --- the threshold is the stricter of two policy reads ---------------------------


def test_a_policy_loosened_after_the_plans_proposal_still_needs_two(
    conn: Connection,
) -> None:
    """Proposed while the covered action's policy required two (the plan's
    own ceiling above the threshold); the two-person block is then removed
    entirely before anyone approves. The plan's own snapshot still requires
    two."""
    _policy(conn, two_person_above_eur=Decimal("500"))
    plan_id = _propose(conn, amount_ceiling=Decimal("1000"))

    _policy(conn, two_person_above_eur=None)

    with pytest.raises(NeedsMoreApprovers):
        plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    assert _state(conn, plan_id) == "proposed"

    plans.approve(conn, plan_id, "carol", FROZEN_NOW)
    assert _state(conn, plan_id) == "active"


def test_a_policy_tightened_after_the_plans_proposal_needs_two(conn: Connection) -> None:
    """Proposed while the covered action had no two-person block at all; one
    is added, with a low threshold, before anyone approves. The CURRENT
    policy is the stricter one now, so this still needs two."""
    _policy(conn, two_person_above_eur=None)
    plan_id = _propose(conn, amount_ceiling=Decimal("1000"))

    _policy(conn, two_person_above_eur=Decimal("500"))

    with pytest.raises(NeedsMoreApprovers):
        plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    assert _state(conn, plan_id) == "proposed"

    plans.approve(conn, plan_id, "carol", FROZEN_NOW)
    assert _state(conn, plan_id) == "active"


def test_a_plan_row_with_no_recorded_snapshot_uses_only_the_current_policy(
    conn: Connection,
) -> None:
    """A row created before the snapshot migration has
    `required_approvers_at_proposal` NULL -- the same "no snapshot, use
    current only" behaviour this program had before this fix."""
    _policy(conn, two_person_above_eur=Decimal("500"))
    plan_id = _propose(conn, amount_ceiling=Decimal("1000"))
    conn.execute("UPDATE plans SET required_approvers_at_proposal=NULL WHERE id=?", (plan_id,))

    _policy(conn, two_person_above_eur=None)

    plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    assert _state(conn, plan_id) == "active"
