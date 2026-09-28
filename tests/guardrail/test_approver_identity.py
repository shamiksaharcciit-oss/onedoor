"""The principal that proposed an action can never approve it.

Enforced where approvals are decided (`approvals.cas_approve`), not in any one
enforcement point: a PEP that stops offering an approve method is a promise, and a
refusal in the store is a rule. The principal is supplied by whoever authenticated the
caller -- never read from the request, which the caller writes.
"""

from __future__ import annotations

from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute, resume_approval
from onedoor.guardrail.models import Decision
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _propose(conn: Connection, config: EngineConfig, principal: str | None) -> int:
    outcome = decide_and_reserve(
        make_request("money.transfer", {"amount_eur": 5}),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
        principal=principal,
    )
    assert outcome.decision.decision == Decision.PROPOSED  # type: ignore[union-attr]
    approval_id = outcome.approval_id  # type: ignore[union-attr]
    assert approval_id is not None
    return int(approval_id)


def _state(conn: Connection, approval_id: int) -> str:
    return str(conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()[0])


def test_the_proposing_principal_cannot_approve(conn: Connection, config: EngineConfig) -> None:
    approval_id = _propose(conn, config, "agent-7")

    with pytest.raises(ApprovalError, match="proposed"), tx(conn):
        approvals.cas_approve(conn, approval_id, "agent-7", FROZEN_NOW)
    assert _state(conn, approval_id) == "pending"

    with tx(conn):
        approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)
    assert _state(conn, approval_id) == "approved"


def test_the_approval_records_who_proposed_it(conn: Connection, config: EngineConfig) -> None:
    approval_id = _propose(conn, config, "agent-7")
    row = conn.execute("SELECT proposed_by FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row[0] == "agent-7"


def test_resume_approval_refuses_the_proposer_and_executes_nothing(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    result = evaluate_and_execute(
        make_request("money.transfer", {"amount_eur": 5}),
        conn=conn,
        registry=registry,
        config=config,
        now=FROZEN_NOW,
        principal="agent-7",
    )
    assert result.approval_id is not None

    with pytest.raises(ApprovalError):
        resume_approval(
            result.approval_id,
            "agent-7",
            conn=conn,
            registry=registry,
            config=config,
            now=FROZEN_NOW,
        )
    assert _state(conn, result.approval_id) == "pending"
    intents = conn.execute("SELECT COUNT(*) FROM actions_audit WHERE kind='exec_intent'")
    assert intents.fetchone()[0] == 0


def test_an_approval_with_no_recorded_proposer_is_approvable_as_before(
    conn: Connection, config: EngineConfig
) -> None:
    """A caller that authenticates nobody has no principal to record, and an approval
    written before proposers were recorded has none either: there is nothing to compare,
    so nothing is refused on this ground."""
    approval_id = _propose(conn, config, None)
    with tx(conn):
        approvals.cas_approve(conn, approval_id, "anyone", FROZEN_NOW)
    assert _state(conn, approval_id) == "approved"
