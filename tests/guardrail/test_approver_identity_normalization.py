"""`cas_approve` compared approver identities as exact strings:
"alice", "Alice", "alice " and "alice" followed by a zero-width
space counted as four different people, each able to cast its own vote
toward the same two-person threshold, or to approve its own proposal
under a differently-cased or padded form of the same identity.
"""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals, policy_loader
from onedoor.guardrail.errors import ApprovalError, NeedsMoreApprovers
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ApprovalPolicy, Bounds, Policy, Tier
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request

ZWSP = "​"


def _two_person(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.identity_norm",
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(strict_params=False),
            approval=ApprovalPolicy(two_person_above_eur=Decimal("100")),
        ),
    )


def _propose(conn: Connection, config: EngineConfig, *, proposed_by: str | None) -> int:
    with tx(conn):
        approval_id = approvals.create(
            conn,
            make_request("demo.identity_norm", {}, cost_eur=Decimal("150")),
            config.approval_ttl_seconds,
            FROZEN_NOW,
            proposed_by=proposed_by,
        )
    return approval_id


def test_case_and_whitespace_variants_do_not_count_as_two(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, proposed_by="agent-7")
    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "Bob", FROZEN_NOW)
    with pytest.raises(ApprovalError, match="already approved"):
        approvals.cas_approve(conn, approval_id, " bob ", FROZEN_NOW)


def test_a_zero_width_space_in_an_identity_is_refused(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, proposed_by="agent-7")
    with pytest.raises(ApprovalError, match="format character"):
        approvals.cas_approve(conn, approval_id, f"bob{ZWSP}", FROZEN_NOW)


def test_the_proposer_cannot_approve_using_a_differently_cased_identity(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, proposed_by="Agent-7")
    with pytest.raises(ApprovalError, match="cannot approve it"):
        approvals.cas_approve(conn, approval_id, " agent-7", FROZEN_NOW)


def test_two_genuinely_different_identities_still_both_count(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, proposed_by="agent-7")
    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "bob", FROZEN_NOW)
    approvals.cas_approve(conn, approval_id, "carol", FROZEN_NOW)
    row = conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["state"] == "approved"
