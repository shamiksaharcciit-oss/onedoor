"""What a second caller can learn or do with a first caller's own
``(thread_id, tool_call_id)`` resume key, today — diagnostic only.

No fix lands here. These tests pin down exactly what the unscoped lookup in
``approvals.find_by_resume_key`` lets a second caller see or do, for each
state the first caller's row can be in, and for a request that does or does
not match what the first caller actually proposed.
"""

from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionResult, CheckId, Decision
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request

THREAD = "shared-thread-1"
CALL = "shared-call-1"
PARAMS_A = {"amount": "10"}
PARAMS_B = {"amount": "99"}


def _propose(
    conn: Connection,
    config: EngineConfig,
    *,
    principal: str | None,
    params: dict[str, object],
    now=FROZEN_NOW,
):
    req = make_request("demo.confirm", params, now=now)
    return decide_and_reserve(
        req,
        conn=conn,
        config=config,
        now=now,
        principal=principal,
        thread_id=THREAD,
        tool_call_id=CALL,
    )


def _resume(
    conn: Connection,
    config: EngineConfig,
    *,
    principal: str | None,
    params: dict[str, object],
    now=FROZEN_NOW,
):
    req = make_request("demo.confirm", params, now=now)
    return decide_and_reserve(
        req,
        conn=conn,
        config=config,
        now=now,
        principal=principal,
        thread_id=THREAD,
        tool_call_id=CALL,
    )


def _present_ref(
    conn: Connection,
    config: EngineConfig,
    *,
    approval_id: int,
    principal: str | None,
    params: dict[str, object],
    now=FROZEN_NOW,
):
    req = make_request("demo.confirm", params, now=now).model_copy(
        update={"approval_ref": approval_id}
    )
    return decide_and_reserve(req, conn=conn, config=config, now=now, principal=principal)


def _approval_state(conn: Connection, approval_id: int) -> str:
    row = conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return str(row["state"])


# --- Same request shape, by state ------------------------------------------


def test_a_second_caller_learns_the_first_callers_pending_approval_id(
    conn: Connection, config: EngineConfig
) -> None:
    """Pending: a second caller presenting the same key and the same action
    shape is handed back the first caller's own approval id, not a fresh one.

    This alone does not execute or consume anything — it is proposed again,
    same as the first caller's own call was.
    """
    first = _propose(conn, config, principal="principal-a", params=PARAMS_A)
    assert first.decision.decision == Decision.PROPOSED
    assert isinstance(first, ActionResult)
    first_approval_id = first.approval_id

    second = _resume(conn, config, principal="principal-b", params=PARAMS_A)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
    assert second.approval_id == first_approval_id

    rows = conn.execute("SELECT COUNT(*) AS n FROM approvals").fetchone()
    assert rows["n"] == 1, "no second approval row should have been created"


def test_a_second_caller_cannot_consume_an_approved_approval_when_the_first_caller_named_a_principal(
    conn: Connection, config: EngineConfig
) -> None:
    """Approved, first proposal had a real principal: the second caller still
    learns the approval id through the shared key, but presenting that id as
    its own approval_ref is refused — the reference path's own principal
    check catches it even though the resume-key lookup itself did not.
    """
    first = _propose(conn, config, principal="principal-a", params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None
    with tx(conn):
        approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)
    assert _approval_state(conn, approval_id) == "approved"

    second = _resume(conn, config, principal="principal-b", params=PARAMS_A)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
    assert second.approval_id == approval_id, "the id is learned via the shared key"

    third = _present_ref(
        conn, config, approval_id=approval_id, principal="principal-b", params=PARAMS_A
    )
    assert isinstance(third, ActionResult)
    # A refused reference never denies outright — by design, it evaluates as
    # though absent, so a nominal Tier-3 action simply proposes again, as a
    # brand new, unrelated approval.
    assert third.decision.decision == Decision.PROPOSED
    assert third.approval_id != approval_id, "a refused reference must not hand back the original"
    audit_row = conn.execute(
        "SELECT approval_ref_status FROM actions_audit WHERE id=?", (third.audit_id,)
    ).fetchone()
    assert audit_row["approval_ref_status"] == "principal_mismatch"
    assert _approval_state(conn, approval_id) == "approved", (
        "the approval must remain unconsumed: the reference path's own principal "
        "check refuses the second caller"
    )


def test_a_second_caller_can_consume_an_approved_approval_when_the_first_proposal_named_no_principal(
    conn: Connection, config: EngineConfig
) -> None:
    """Approved, first proposal had NO principal: the second caller learns
    the approval id through the shared key, and the reference path's own
    principal check is a no-op for a row with nothing recorded to check
    against — so presenting the learned id grants, and the action executes
    for the second caller.

    This is the finding ruling 30sr asks to be answered unambiguously:
    **yes, under this precondition.**
    """
    first = _propose(conn, config, principal=None, params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None
    with tx(conn):
        approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)
    assert _approval_state(conn, approval_id) == "approved"

    second = _resume(conn, config, principal="principal-b", params=PARAMS_A)
    assert isinstance(second, ActionResult)
    assert second.approval_id == approval_id, "the id is learned via the shared key"

    third = _present_ref(
        conn, config, approval_id=approval_id, principal="principal-b", params=PARAMS_A
    )
    assert isinstance(third, PermittedIntent), (
        "the second caller's presentation of the learned id is GRANTED — "
        "the action proceeds to execution"
    )
    assert _approval_state(conn, approval_id) == "consumed"


def test_a_second_callers_resume_on_an_expired_key_gets_an_unlinked_fresh_proposal(
    conn: Connection, config: EngineConfig
) -> None:
    """Expired: today, a resume on an expired key does not reuse or reveal
    the first caller's approval id at all — it silently proposes a brand new,
    unrelated approval, indistinguishable from a key that was never used.
    """
    first = _propose(conn, config, principal="principal-a", params=PARAMS_A)
    assert isinstance(first, ActionResult)
    first_approval_id = first.approval_id

    later = FROZEN_NOW + timedelta(seconds=config.approval_ttl_seconds + 1)
    second = _resume(conn, config, principal="principal-b", params=PARAMS_A, now=later)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
    assert second.approval_id != first_approval_id, "expired must not hand over the old id"

    assert _approval_state(conn, first_approval_id) == "expired"


# --- A different request shape presented against the first caller's live key --


def test_a_second_callers_mismatched_request_is_told_apart_from_no_key_while_pending(
    conn: Connection, config: EngineConfig
) -> None:
    """Pending, different shape: the second caller is refused with a specific
    reason that only fires because a row for this key exists — silence (an
    ordinary fresh proposal) would be the behaviour with no row at all.
    """
    _propose(conn, config, principal="principal-a", params=PARAMS_A)
    second = _resume(conn, config, principal="principal-b", params=PARAMS_B)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.DENIED
    assert second.decision.reason_code == CheckId.RESUME_REQUEST_MISMATCH


def test_a_second_callers_mismatched_request_is_told_apart_from_no_key_while_approved(
    conn: Connection, config: EngineConfig
) -> None:
    """Approved, different shape: same tell as the pending case."""
    first = _propose(conn, config, principal="principal-a", params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None
    with tx(conn):
        approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)

    second = _resume(conn, config, principal="principal-b", params=PARAMS_B)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.DENIED
    assert second.decision.reason_code == CheckId.RESUME_REQUEST_MISMATCH


def test_a_second_callers_mismatched_request_is_not_told_apart_from_no_key_once_expired(
    conn: Connection, config: EngineConfig
) -> None:
    """Expired, different shape: the tell disappears — the second caller's
    differently-shaped request simply proposes fresh, exactly as it would
    against a key nobody had ever used.
    """
    _propose(conn, config, principal="principal-a", params=PARAMS_A)
    later = FROZEN_NOW + timedelta(seconds=config.approval_ttl_seconds + 1)
    second = _resume(conn, config, principal="principal-b", params=PARAMS_B, now=later)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
