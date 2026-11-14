"""The two-person threshold is the stricter of the policy snapshot recorded
with the proposal and the current policy.

Before this fix, `_required_approvers` read only the live policy at approval
time -- a policy edited between proposal and approval (the threshold raised,
or the two-person block removed) let a large action proposed under the
stricter rule complete with only one approver.
"""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals, policy_loader
from onedoor.guardrail.errors import NeedsMoreApprovers
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ApprovalPolicy, Bounds, Policy, Tier
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _policy(*, two_person_above_eur: Decimal | None) -> Policy:
    return Policy(
        action_type="demo.threshold_drift",
        tier=Tier.CONFIRM,
        dry_run=True,
        bounds=Bounds(strict_params=False),
        approval=(
            None
            if two_person_above_eur is None
            else ApprovalPolicy(two_person_above_eur=two_person_above_eur)
        ),
    )


def _propose(conn: Connection, config: EngineConfig, *, cost: Decimal) -> int:
    with tx(conn):
        approval_id = approvals.create(
            conn,
            make_request("demo.threshold_drift", {}, cost_eur=cost),
            config.approval_ttl_seconds,
            FROZEN_NOW,
            proposed_by="agent-7",
        )
    return approval_id


def _state(conn: Connection, approval_id: int) -> str:
    return str(conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()[0])


def test_a_policy_loosened_after_the_proposal_still_needs_two(
    conn: Connection, config: EngineConfig
) -> None:
    """Proposed while the policy required two (cost above the threshold);
    the block is then removed entirely before anyone approves. The
    proposal's own snapshot still requires two."""
    policy_loader.upsert(conn, _policy(two_person_above_eur=Decimal("100")))
    approval_id = _propose(conn, config, cost=Decimal("150"))

    policy_loader.upsert(conn, _policy(two_person_above_eur=None))

    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)
    assert _state(conn, approval_id) == "pending"

    approvals.cas_approve(conn, approval_id, "operator-2", FROZEN_NOW)
    assert _state(conn, approval_id) == "approved"


def test_a_policy_tightened_after_the_proposal_needs_two(
    conn: Connection, config: EngineConfig
) -> None:
    """Proposed while the policy had no two-person block at all; one is
    added, with a low threshold, before anyone approves. The CURRENT
    policy is the stricter one now, so this still needs two."""
    policy_loader.upsert(conn, _policy(two_person_above_eur=None))
    approval_id = _propose(conn, config, cost=Decimal("150"))

    policy_loader.upsert(conn, _policy(two_person_above_eur=Decimal("100")))

    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)
    assert _state(conn, approval_id) == "pending"

    approvals.cas_approve(conn, approval_id, "operator-2", FROZEN_NOW)
    assert _state(conn, approval_id) == "approved"


def test_an_unchanged_policy_still_needs_only_one_below_its_own_threshold(
    conn: Connection, config: EngineConfig
) -> None:
    """Control: no drift at all, cost under the threshold -- one approver,
    exactly as every policy before this feature existed."""
    policy_loader.upsert(conn, _policy(two_person_above_eur=Decimal("100")))
    approval_id = _propose(conn, config, cost=Decimal("50"))

    approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)
    assert _state(conn, approval_id) == "approved"


def test_a_row_with_no_recorded_snapshot_uses_only_the_current_policy(
    conn: Connection, config: EngineConfig
) -> None:
    """A row created before migration 0042 has `required_approvers_at_proposal`
    NULL -- the same "no snapshot, use current only" behaviour this program
    had before this fix, not retroactively stricter."""
    policy_loader.upsert(conn, _policy(two_person_above_eur=Decimal("100")))
    with tx(conn):
        approval_id = approvals.create(
            conn,
            make_request("demo.threshold_drift", {}, cost_eur=Decimal("150")),
            config.approval_ttl_seconds,
            FROZEN_NOW,
            proposed_by="agent-7",
        )
    conn.execute(
        "UPDATE approvals SET required_approvers_at_proposal=NULL WHERE id=?",
        (approval_id,),
    )

    policy_loader.upsert(conn, _policy(two_person_above_eur=None))

    approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)
    assert _state(conn, approval_id) == "approved"
