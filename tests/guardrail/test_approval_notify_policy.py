"""`Policy.approval_notify` (signed approval links): the policy-syntax half
only. A policy configuring no notify
adapter decides identically to its 0.10.x self; one that does configure one
round-trips through the policy store unchanged, and decision-making itself
is untouched (notification is a side channel, never part of the verdict).
"""

from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ApprovalNotify, Bounds, Policy, Tier
from onedoor.guardrail.policy import PolicyStore
from tests.conftest import FROZEN_NOW, make_request

ACTION = "demo.approval_notify"


def test_a_policy_with_no_approval_notify_block_decides_identically_to_before(
    conn: Connection, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
        ),
    )
    result = decide_and_reserve(make_request(ACTION), conn=conn, config=config, now=FROZEN_NOW)
    assert result.decision.decision.value == "proposed"


def test_an_approval_notify_block_round_trips_through_the_policy_store(
    conn: Connection,
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
            approval_notify=ApprovalNotify(channel="email", recipient="approver@example.test"),
        ),
    )
    policy = PolicyStore().get(conn, ACTION)
    assert policy.approval_notify == ApprovalNotify(
        channel="email", recipient="approver@example.test"
    )


def test_an_approval_notify_block_does_not_change_the_decision(
    conn: Connection, config: EngineConfig
) -> None:
    """Notification is a side channel layered on top of the existing
    approval mechanics (the design note's own "Reason code" section): a
    policy that configures one decides exactly as one that does not."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
            approval_notify=ApprovalNotify(
                channel="webhook", recipient="https://example.test/hook"
            ),
        ),
    )
    result = decide_and_reserve(make_request(ACTION), conn=conn, config=config, now=FROZEN_NOW)
    assert result.decision.decision.value == "proposed"
