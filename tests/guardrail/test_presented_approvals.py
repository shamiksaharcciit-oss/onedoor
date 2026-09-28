"""A presented approval (`approval_ref`) resumes an action with the same evidence as any
other resumption, and a reference the store cannot hold is evaluated as absent."""

from __future__ import annotations

from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Decision
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _approved(conn: Connection, config: EngineConfig) -> tuple[int, int]:
    """(approval id, audit id of its proposal), approved by an operator."""
    outcome = decide_and_reserve(
        make_request("demo.confirm"), conn=conn, config=config, now=FROZEN_NOW, principal="agent"
    )
    approval_id = outcome.approval_id  # type: ignore[union-attr]
    assert approval_id is not None
    with tx(conn):
        approvals.cas_approve(conn, approval_id, "operator", FROZEN_NOW)
    proposal = approvals.proposed_audit_id(conn, approval_id)
    assert proposal is not None
    return approval_id, proposal


def test_a_presented_approval_links_the_resumption_to_its_proposal_and_approval(
    conn: Connection, config: EngineConfig
) -> None:
    approval_id, proposal = _approved(conn, config)
    presented = make_request("demo.confirm").model_copy(update={"approval_ref": approval_id})

    outcome = decide_and_reserve(presented, conn=conn, config=config, now=FROZEN_NOW)

    assert isinstance(outcome, PermittedIntent)
    row = conn.execute(
        "SELECT resumes_audit_id FROM actions_audit WHERE id=?", (outcome.intent_audit_id,)
    ).fetchone()
    assert row[0] == proposal
    linked = conn.execute(
        "SELECT resulting_audit_id FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()[0]
    assert linked == outcome.intent_audit_id


@pytest.mark.parametrize("ref", [2**63, -(2**63) - 1, 10**30])
def test_an_out_of_range_reference_is_evaluated_as_absent(
    conn: Connection, config: EngineConfig, ref: int
) -> None:
    presented = make_request("demo.confirm").model_copy(update={"approval_ref": ref})
    outcome = decide_and_reserve(presented, conn=conn, config=config, now=FROZEN_NOW)
    assert outcome.decision.decision == Decision.PROPOSED  # type: ignore[union-attr]
    status = conn.execute(
        "SELECT approval_ref_status FROM actions_audit ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "unknown"


def test_the_proposer_is_never_read_from_the_request(
    conn: Connection, config: EngineConfig
) -> None:
    """The request is written by the asker; its session_id is a claim, not an identity."""
    claims_to_be = make_request("demo.confirm").model_copy(update={"session_id": "operator"})
    outcome = decide_and_reserve(
        claims_to_be, conn=conn, config=config, now=FROZEN_NOW, principal="agent-7"
    )
    approval_id = outcome.approval_id  # type: ignore[union-attr]
    recorded = conn.execute(
        "SELECT proposed_by FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()[0]
    assert recorded == "agent-7"

    anonymous = decide_and_reserve(
        make_request("demo.confirm").model_copy(update={"session_id": "operator"}),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    recorded = conn.execute(
        "SELECT proposed_by FROM approvals WHERE id=?",
        (anonymous.approval_id,),  # type: ignore[union-attr]
    ).fetchone()[0]
    assert recorded is None
