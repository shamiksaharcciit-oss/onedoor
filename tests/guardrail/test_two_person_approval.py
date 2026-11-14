"""Two-person rule and escalation (onedoor 0.11, design note "Two-person
rule and escalation"). Above a policy's own threshold, two different
approvers; the proposer never counts, whether an ordinary approver or a
backup escalation assigned; an unanswered approval escalates to a backup
approver before the existing full-TTL expiry, which this never replaces.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from decimal import Decimal
from sqlite3 import Connection

import pytest

from onedoor import decision_digest as decision_digest_module
from onedoor.guardrail import approvals, policy_loader
from onedoor.guardrail.approval_ref import ApprovalRefStatus
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.errors import ApprovalError, NeedsMoreApprovers
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute, resume_approval
from onedoor.guardrail.models import ApprovalPolicy, Bounds, Decision, Policy, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _two_person(conn: Connection, *, escalate_after_seconds: int | None = None) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.two_person",
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(strict_params=False),
            approval=ApprovalPolicy(
                two_person_above_eur=Decimal("100"),
                escalate_after_seconds=escalate_after_seconds,
            ),
        ),
    )


def _propose(
    conn: Connection,
    config: EngineConfig,
    *,
    cost: Decimal,
    proposed_by: str | None = "agent-7",
) -> int:
    with tx(conn):
        approval_id = approvals.create(
            conn,
            make_request("demo.two_person", {}, cost_eur=cost),
            config.approval_ttl_seconds,
            FROZEN_NOW,
            proposed_by=proposed_by,
        )
    return approval_id


def _state(conn: Connection, approval_id: int) -> str:
    return str(conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()[0])


def _approvers(conn: Connection, approval_id: int) -> list[str]:
    row = conn.execute("SELECT approvers_json FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return list(json.loads(row["approvers_json"]))


def _ref_status(conn: Connection) -> str | None:
    row = conn.execute(
        "SELECT approval_ref_status FROM actions_audit ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["approval_ref_status"] if row else None


def _present(
    conn: Connection,
    config: EngineConfig,
    approval_id: int,
    *,
    cost: Decimal,
    now: object,
    principal: str | None = None,
) -> object:
    request = make_request("demo.two_person", {}, cost_eur=cost)
    resumed = request.model_copy(update={"approval_ref": approval_id})
    return decide_and_reserve(resumed, conn=conn, config=config, now=now, principal=principal)


# --- the two-person rule itself ---------------------------------------------------


def test_one_approver_alone_does_not_release_an_action_above_the_threshold(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("150"))

    # Not wrapped in tx(): cas_approve's own UPDATE is already one atomic,
    # self-committing CAS -- see its own docstring on why an outer tx()
    # would roll back the very approver this call just recorded.
    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)

    assert _state(conn, approval_id) == "pending"
    assert _approvers(conn, approval_id) == ["operator-1"]


def test_a_second_different_approver_releases_it(conn: Connection, config: EngineConfig) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("150"))

    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)
    approvals.cas_approve(conn, approval_id, "operator-2", FROZEN_NOW)

    assert _state(conn, approval_id) == "approved"
    assert _approvers(conn, approval_id) == ["operator-1", "operator-2"]


def test_the_same_identity_approving_twice_does_not_count_as_two(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("150"))

    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)

    with pytest.raises(ApprovalError, match="already approved"):
        approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)

    assert _state(conn, approval_id) == "pending"
    assert _approvers(conn, approval_id) == ["operator-1"]


def test_a_requester_still_cannot_approve_their_own_two_person_action(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("150"), proposed_by="agent-7")

    with pytest.raises(ApprovalError, match="proposed"):
        approvals.cas_approve(conn, approval_id, "agent-7", FROZEN_NOW)

    assert _state(conn, approval_id) == "pending"
    assert _approvers(conn, approval_id) == []


def test_a_policy_with_no_approval_block_decides_identically_to_before(
    conn: Connection, config: EngineConfig
) -> None:
    """No `approval` block (every policy before this feature existed): one
    approver, any identity but the proposer, flips straight to approved --
    the same behaviour `test_approver_identity.py` already covers,
    confirmed again here with the two-person machinery now present."""
    with tx(conn):
        approval_id = approvals.create(
            conn,
            make_request("money.transfer", {"amount_eur": 5}),
            config.approval_ttl_seconds,
            FROZEN_NOW,
            proposed_by="agent-7",
        )
    approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)
    assert _state(conn, approval_id) == "approved"


def test_below_the_threshold_one_approver_still_releases_it(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("50"))  # below 100
    approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)
    assert _state(conn, approval_id) == "approved"


def test_an_unresolvable_amount_needs_two_approvers_not_one(
    conn: Connection, config: EngineConfig
) -> None:
    """Unknown is never a free pass: a cost of 0 reads as unset (`caps.
    resolve_cost`'s own rule), not as a real zero below the threshold, so
    it gets the stronger protection rather than the weaker one."""
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("0"))
    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "operator-1", FROZEN_NOW)


# --- escalation --------------------------------------------------------------------


def test_escalation_sets_a_backup_approver_after_its_own_window(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn, escalate_after_seconds=1800)
    approval_id = _propose(conn, config, cost=Decimal("150"))
    escalating = EngineConfig(
        approval_ttl_seconds=config.approval_ttl_seconds,
        connector_timeout_seconds=config.connector_timeout_seconds,
        tz=config.tz,
        escalation_resolver=lambda action_type: "backup-1",
    )
    later = FROZEN_NOW + timedelta(seconds=1801)
    _present(conn, escalating, approval_id, cost=Decimal("150"), now=later, principal="checker")

    row = conn.execute(
        "SELECT backup_approver, escalated_at FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["backup_approver"] == "backup-1"
    assert row["escalated_at"] is not None


def test_escalation_does_not_fire_before_its_own_window(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn, escalate_after_seconds=1800)
    approval_id = _propose(conn, config, cost=Decimal("150"))
    escalating = EngineConfig(
        approval_ttl_seconds=config.approval_ttl_seconds,
        connector_timeout_seconds=config.connector_timeout_seconds,
        tz=config.tz,
        escalation_resolver=lambda action_type: "backup-1",
    )
    too_soon = FROZEN_NOW + timedelta(seconds=1799)
    _present(conn, escalating, approval_id, cost=Decimal("150"), now=too_soon, principal="checker")

    row = conn.execute(
        "SELECT backup_approver FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["backup_approver"] is None


def test_a_backup_approver_alone_still_does_not_release_a_two_person_action(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn, escalate_after_seconds=1800)
    approval_id = _propose(conn, config, cost=Decimal("150"))
    escalating = EngineConfig(
        approval_ttl_seconds=config.approval_ttl_seconds,
        connector_timeout_seconds=config.connector_timeout_seconds,
        tz=config.tz,
        escalation_resolver=lambda action_type: "backup-1",
    )
    later = FROZEN_NOW + timedelta(seconds=1801)
    _present(conn, escalating, approval_id, cost=Decimal("150"), now=later, principal="checker")

    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "backup-1", later)

    assert _state(conn, approval_id) == "pending"


def test_a_backup_approver_who_is_also_the_proposer_is_excluded(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn, escalate_after_seconds=1800)
    approval_id = _propose(conn, config, cost=Decimal("150"), proposed_by="agent-7")
    escalating = EngineConfig(
        approval_ttl_seconds=config.approval_ttl_seconds,
        connector_timeout_seconds=config.connector_timeout_seconds,
        tz=config.tz,
        escalation_resolver=lambda action_type: "agent-7",  # happens to be the proposer
    )
    later = FROZEN_NOW + timedelta(seconds=1801)
    _present(conn, escalating, approval_id, cost=Decimal("150"), now=later, principal="checker")

    row = conn.execute(
        "SELECT backup_approver FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["backup_approver"] == "agent-7"  # escalation still assigns it...

    with pytest.raises(ApprovalError, match="proposed"):
        approvals.cas_approve(conn, approval_id, "agent-7", later)  # ...but cannot approve


def test_with_no_resolver_configured_an_approval_still_expires_and_denies_as_before(
    conn: Connection, config: EngineConfig
) -> None:
    _two_person(conn, escalate_after_seconds=1800)
    approval_id = _propose(conn, config, cost=Decimal("150"))
    past_full_ttl = FROZEN_NOW + timedelta(seconds=config.approval_ttl_seconds + 1)

    # config.escalation_resolver is None (the default) -- escalation never fires,
    # whatever the policy's own escalate_after_seconds says.
    _present(conn, config, approval_id, cost=Decimal("150"), now=past_full_ttl, principal="checker")

    row = conn.execute(
        "SELECT backup_approver, escalated_at FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["backup_approver"] is None
    assert row["escalated_at"] is None
    assert _ref_status(conn) == ApprovalRefStatus.EXPIRED.value


# --- resuming through executor.resume_approval ----------------------------
#
# `resume_approval` -- unlike `_present`'s `decide_and_reserve(approval_ref=...)`
# path above, and unlike `cas_approve` called directly -- is the one entry point
# that used to wrap `cas_approve` inside `tx(conn)`. Above the two-person
# threshold, the first approver's `NeedsMoreApprovers` rolled that `tx` back,
# erasing the very vote `cas_approve`'s own atomic UPDATE had just committed.


def test_one_approver_through_resume_approval_leaves_the_vote_recorded(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("150"))

    with pytest.raises(NeedsMoreApprovers):
        resume_approval(
            approval_id, "operator-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
        )

    # The vote must survive: an enclosing tx() that rolled back on this
    # exception would erase it, and a second approver would then be
    # recorded as if first, forever short of the threshold.
    assert _state(conn, approval_id) == "pending"
    assert _approvers(conn, approval_id) == ["operator-1"]


def test_resume_approval_tags_its_own_vote_as_the_library_channel(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    """A vote through `resume_approval` must carry its own channel,
    the same way a key vote and a link vote already do -- otherwise it is
    invisible to the mixed-channel check and could pair with either one to
    complete a two-person approval that was never really two different
    identities checked against each other's channel. Demonstrated here
    against a vote planted directly as `channel="key"` (standing in for an
    admin-key vote, without needing the HTTP service): a SECOND vote
    through `resume_approval` must be refused as a mixed pair, not
    silently counted."""
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("150"))
    with pytest.raises(NeedsMoreApprovers):
        approvals.cas_approve(conn, approval_id, "key-holder-1", FROZEN_NOW, channel="key")

    with pytest.raises(ApprovalError, match="different"):
        resume_approval(
            approval_id, "operator-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
        )
    assert _state(conn, approval_id) == "pending"
    assert _approvers(conn, approval_id) == ["key-holder-1"]


def test_a_second_different_approver_through_resume_approval_resumes_exactly_once(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    _two_person(conn)
    called = _spy(registry, "demo.two_person")
    approval_id = _propose(conn, config, cost=Decimal("150"))

    with pytest.raises(NeedsMoreApprovers):
        resume_approval(
            approval_id, "operator-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
        )
    result = resume_approval(
        approval_id, "operator-2", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )

    assert result.decision.decision == Decision.EXECUTED
    assert len(called) == 1, "exactly one execution, from the second, completing approver"
    assert _state(conn, approval_id) == "consumed"
    assert _approvers(conn, approval_id) == ["operator-1", "operator-2"]


def test_the_same_approver_twice_through_resume_approval_is_refused(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("150"))

    with pytest.raises(NeedsMoreApprovers):
        resume_approval(
            approval_id, "operator-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
        )
    with pytest.raises(ApprovalError, match="already approved"):
        resume_approval(
            approval_id, "operator-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
        )

    assert _state(conn, approval_id) == "pending"
    assert _approvers(conn, approval_id) == ["operator-1"]


def test_the_proposer_through_resume_approval_is_still_refused(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    _two_person(conn)
    approval_id = _propose(conn, config, cost=Decimal("150"), proposed_by="agent-7")

    with pytest.raises(ApprovalError, match="proposed"):
        resume_approval(
            approval_id, "agent-7", conn=conn, registry=registry, config=config, now=FROZEN_NOW
        )

    assert _state(conn, approval_id) == "pending"
    assert _approvers(conn, approval_id) == []


def _spy(registry: ConnectorRegistry, action_type: str) -> list[object]:
    called: list[object] = []
    registry.register(action_type, lambda params: called.append(params) or {"ok": True})
    return called


# --- the receipt names who approved ----------------------------------------


def _audit_row(conn: Connection, audit_id: int | None) -> sqlite3.Row:
    assert audit_id is not None
    row = conn.execute(
        "SELECT approvers_json, escalated_to, escalated_at FROM actions_audit WHERE id=?",
        (audit_id,),
    ).fetchone()
    assert row is not None
    return row


def test_a_two_person_resumptions_receipt_names_both_approvers_in_order(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    _two_person(conn)
    _spy(registry, "demo.two_person")
    approval_id = _propose(conn, config, cost=Decimal("150"))

    with pytest.raises(NeedsMoreApprovers):
        resume_approval(
            approval_id, "operator-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
        )
    result = resume_approval(
        approval_id, "operator-2", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )

    # `result.decision` is Tx B's own exec_result decision (EXECUTED), which --
    # like every other 0.11 receipt member -- never carries this; the real
    # receipt is the intent row `result.audit_id` names (Tx A, the decision
    # that actually resumed the approval), read back here the same way
    # test_sequence.py's own receipt tests read sequence_events_considered
    # back off an EXECUTED call.
    row = _audit_row(conn, result.audit_id)
    assert json.loads(row["approvers_json"]) == ["operator-1", "operator-2"]
    assert row["escalated_to"] is None
    assert row["escalated_at"] is None


def test_a_one_person_resumptions_receipt_names_one_approver(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    """Below the two-person threshold -- a policy that declares the block but
    an amount under it -- one approver still resumes, and the receipt names
    exactly that one, never `None`."""
    _two_person(conn)
    _spy(registry, "demo.two_person")
    approval_id = _propose(conn, config, cost=Decimal("50"))

    result = resume_approval(
        approval_id, "operator-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )

    row = _audit_row(conn, result.audit_id)
    assert json.loads(row["approvers_json"]) == ["operator-1"]


def test_an_escalated_resumptions_receipt_names_the_backup_and_the_time(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    _two_person(conn, escalate_after_seconds=1800)
    _spy(registry, "demo.two_person")
    approval_id = _propose(conn, config, cost=Decimal("150"))
    escalating = EngineConfig(
        approval_ttl_seconds=config.approval_ttl_seconds,
        connector_timeout_seconds=config.connector_timeout_seconds,
        tz=config.tz,
        escalation_resolver=lambda action_type: "backup-1",
    )
    later = FROZEN_NOW + timedelta(seconds=1801)
    # escalate_if_due runs inside approval_ref.resolve before the state check,
    # so presenting the ref (still pending -- not yet authorised) is enough to
    # make escalation fire.
    _present(conn, escalating, approval_id, cost=Decimal("150"), now=later, principal="checker")

    with pytest.raises(NeedsMoreApprovers):
        resume_approval(
            approval_id, "operator-1", conn=conn, registry=registry, config=escalating, now=later
        )
    result = resume_approval(
        approval_id, "backup-1", conn=conn, registry=registry, config=escalating, now=later
    )

    row = _audit_row(conn, result.audit_id)
    assert json.loads(row["approvers_json"]) == ["operator-1", "backup-1"]
    assert row["escalated_to"] == "backup-1"
    assert row["escalated_at"] is not None


def test_a_non_resumptions_receipt_has_the_two_person_fields_null_digest_unchanged(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    """An ordinary, non-resuming decision -- the common case, and every
    decision before this feature existed -- gets `None` for all three, never
    `[]` or any other real value, and its digest must be exactly what it
    would be without these columns at all (migration 0041's own
    `OMIT_WHEN_NONE` guarantee, proven here against a real row, not only the
    unit-level fixture in `tests/test_decision_digest.py`)."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.plain_auto",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.plain_auto",
            bounds=Bounds(strict_params=False),
        ),
    )
    _spy(registry, "demo.plain_auto")
    result = evaluate_and_execute(
        make_request("demo.plain_auto"), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )

    assert result.decision.approvers is None
    assert result.decision.escalated_to is None
    assert result.decision.escalated_at is None
    row = conn.execute("SELECT * FROM actions_audit WHERE id=?", (result.audit_id,)).fetchone()
    assert row["approvers_json"] is None
    assert row["escalated_to"] is None
    assert row["escalated_at"] is None

    full_digest = decision_digest_module.decision_digest(row)
    stripped = {
        k: row[k] for k in row.keys() if k not in ("approvers_json", "escalated_to", "escalated_at")
    }
    assert decision_digest_module.decision_digest(stripped) == full_digest
