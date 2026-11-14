"""`propose_action` -- the single library write path -- records who proposed
a Tier-3 action only when its caller says so. Without a
`principal`, the row stays unattributed, exactly as every 0.10.2 caller of
this function already expects; the design note's self-approval exclusion
for a library caller depends on this being recorded.
"""

from __future__ import annotations

from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig, propose_action
from onedoor.guardrail.models import Decision
from onedoor.guardrail.registry import ConnectorRegistry
from tests.conftest import FROZEN_NOW


def _propose(
    conn: Connection,
    registry: ConnectorRegistry,
    config: EngineConfig,
    *,
    principal: str | None,
) -> int:
    result = propose_action(
        "demo.confirm",
        {},
        "a rationale",
        conn=conn,
        registry=registry,
        config=config,
        now=FROZEN_NOW,
        principal=principal,
    )
    assert result.decision.decision == Decision.PROPOSED
    assert result.approval_id is not None
    return result.approval_id


def test_propose_action_records_the_given_principal(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    approval_id = _propose(conn, registry, config, principal="alice")
    row = conn.execute("SELECT proposed_by FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["proposed_by"] == "alice"


def test_propose_action_without_a_principal_stays_unattributed(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    approval_id = _propose(conn, registry, config, principal=None)
    row = conn.execute("SELECT proposed_by FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["proposed_by"] is None


def test_the_recorded_principal_cannot_approve_its_own_proposal(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    approval_id = _propose(conn, registry, config, principal="alice")
    with pytest.raises(ApprovalError, match="cannot approve it"):
        approvals.cas_approve(conn, approval_id, "alice", FROZEN_NOW)
    approvals.cas_approve(conn, approval_id, "bob", FROZEN_NOW)
    row = conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["state"] == "approved"


def test_with_no_recorded_principal_the_proposer_can_still_approve_it(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """The exact pre-fix gap this closes: with nothing recorded, there is
    no proposer to exclude -- unchanged, 0.10.2 behaviour, not a new hole
    this fix introduces."""
    approval_id = _propose(conn, registry, config, principal=None)
    approvals.cas_approve(conn, approval_id, "alice", FROZEN_NOW)
    row = conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["state"] == "approved"
