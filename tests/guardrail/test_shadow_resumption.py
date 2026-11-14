"""The decision a caller actually holds after a resumption -- not a decision
built fresh with the approval stripped out -- is what `shadow`'s own
comparison must read `approvers` from.

Every test here goes through the REAL path (`resume_approval`, an
approval-ref resumption, `resume_ratification`, or `evaluate_and_execute`
with `approved_override=True`) and records the `ActionResult` it actually
gets back -- never an `approvers` set by hand on a `PolicyDecision` built
for the test's own convenience, since that is exactly the shape that let
this gap through a prior round's own tests.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from sqlite3 import Connection
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from onedoor.connectors import mock
from onedoor.decision_digest import decision_digest
from onedoor.guardrail import approvals, mandate, policy_loader, shadow
from onedoor.guardrail import executor as executor_mod
from onedoor.guardrail.decision import ActionResult, decide_and_reserve
from onedoor.guardrail.executor import (
    EngineConfig,
    evaluate_and_execute,
    resume_approval,
    resume_ratification,
)
from onedoor.guardrail.models import ActionRequest, Bounds, Decision, Policy, Source, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _shadow_proposes(
    conn: Connection, config: EngineConfig, action_type: str
) -> shadow.ShadowDecision:
    """A plain Tier-3 candidate for this action type, deliberately
    independent of whatever tier the live policy actually used: shadow
    never resumes anything, so it always proposes a Tier-3 action fresh,
    which is exactly why comparing it against a live EXECUTED resumption by
    reason code alone would read "disagree"."""
    candidate = Policy(
        action_type=action_type, tier=Tier.CONFIRM, bounds=Bounds(strict_params=False)
    )
    req = make_request(action_type)
    result = shadow.evaluate(
        conn, candidate, req, now=FROZEN_NOW, tz=config.tz, kill_switch_engaged=False
    )
    assert result.decision == Decision.PROPOSED
    return result


def test_resume_approvals_real_path_reads_not_modeled(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    proposed = evaluate_and_execute(
        make_request("demo.confirm"), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert proposed.approval_id is not None
    result = resume_approval(
        proposed.approval_id, "sess-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert result.executed is True
    assert result.decision.reason_code.value == "passed"

    shadow_result = _shadow_proposes(conn, config, "demo.confirm")
    row_id = shadow.record(
        conn,
        make_request("demo.confirm"),
        shadow_result,
        policy_label="candidate",
        now=FROZEN_NOW,
        live_decision=result.decision,
    )
    row = conn.execute("SELECT comparison FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["comparison"] == "live decided by passed; not modeled"


def test_an_approval_ref_resumptions_real_path_reads_not_modeled(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.refpay",
            tier=Tier.CONFIRM,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    registry.register("demo.refpay", mock.act_ok)
    request = make_request("demo.refpay", source=Source.LLM)
    with tx(conn):
        approval_id = approvals.create(conn, request, config.approval_ttl_seconds, FROZEN_NOW)
        approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)

    resumed = request.model_copy(update={"request_id": uuid4(), "approval_ref": approval_id})
    result = evaluate_and_execute(
        resumed, conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert result.executed is True
    assert result.decision.reason_code.value == "passed"

    shadow_result = _shadow_proposes(conn, config, "demo.refpay")
    row_id = shadow.record(
        conn,
        request,
        shadow_result,
        policy_label="candidate",
        now=FROZEN_NOW,
        live_decision=result.decision,
    )
    row = conn.execute("SELECT comparison FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["comparison"] == "live decided by passed; not modeled"


def _key_pair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return private, public


def test_a_mandate_resumptions_real_path_reads_not_modeled(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    private, public_key = _key_pair()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.mandatepay",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            requires_external_authorization=True,
        ),
    )
    registry.register("demo.mandatepay", mock.act_ok)

    def resolver(request: object) -> mandate.MandateVerdict:
        return mandate.MandateVerdict.PENDING

    cfg = dataclasses.replace(
        config, mandate_resolver=resolver, mandate_authority_public_key=public_key
    )
    pending = decide_and_reserve(
        make_request("demo.mandatepay"), conn=conn, config=cfg, now=FROZEN_NOW
    )
    assert isinstance(pending, ActionResult)
    assert pending.approval_id is not None
    row = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()
    digest = row["mandate_core_digest"]
    with tx(conn):
        ratified = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=private.sign(digest.encode("ascii")).hex(),
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert ratified.authorised

    result = resume_ratification(
        pending.approval_id,
        conn=conn,
        registry=registry,
        config=cfg,
        now=FROZEN_NOW,
    )
    assert result.executed is True
    assert result.decision.reason_code.value == "passed"

    shadow_result = _shadow_proposes(conn, config, "demo.mandatepay")
    row_id = shadow.record(
        conn,
        make_request("demo.mandatepay"),
        shadow_result,
        policy_label="candidate",
        now=FROZEN_NOW,
        live_decision=result.decision,
    )
    row2 = conn.execute("SELECT comparison FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row2["comparison"] == "live decided by passed; not modeled"


def test_an_approved_override_with_no_approval_row_reads_not_modeled(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """The bare-admin-override shape (`test_sabotage_omitting_resumes_audit_id_
    leaves_no_link`'s own pattern): a real approval is cast outside this
    call's own view, the resumed request carries no `approval_ref`, and no
    `consumes_approval`/`resumes_audit_id` is passed either -- the one shape
    with no approval row this call can look up at all."""
    proposed = evaluate_and_execute(
        make_request("demo.confirm"), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert proposed.approval_id is not None
    with tx(conn):
        original = approvals.cas_approve(conn, proposed.approval_id, "sess-1", FROZEN_NOW)
    resumed = original.model_copy(update={"request_id": uuid4(), "created_at": FROZEN_NOW})

    result = evaluate_and_execute(
        resumed,
        conn=conn,
        registry=registry,
        config=config,
        now=FROZEN_NOW,
        approved_override=True,
    )
    assert result.executed is True
    assert result.decision.reason_code.value == "passed"

    shadow_result = _shadow_proposes(conn, config, "demo.confirm")
    row_id = shadow.record(
        conn,
        make_request("demo.confirm"),
        shadow_result,
        policy_label="candidate",
        now=FROZEN_NOW,
        live_decision=result.decision,
    )
    row = conn.execute("SELECT comparison FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["comparison"] == "live decided by passed; not modeled"


def test_a_bare_override_denied_directly_reads_not_modeled(
    conn: Connection, config: EngineConfig
) -> None:
    """A bare override `_decide_and_reserve` denies OUTRIGHT -- default-deny,
    bounds, the kill switch, anything terminal -- never executes and never
    reaches `report_result`. The decision this call returns still needs its
    own `[]` marking, recognised from `approved_override` on this call, the
    same way an executed override's returned decision already reads it.
    `decide_and_reserve` is the one place both of its own return shapes
    (a terminal `ActionResult` here, a `PermittedIntent` `report_result`
    marks later) pass through, so this is marked there."""
    outcome = decide_and_reserve(
        make_request("demo.undeclared"),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
        approved_override=True,
    )
    assert isinstance(outcome, ActionResult)
    assert outcome.decision.decision.value == "denied"
    assert outcome.decision.reason_code.value == "default_deny"
    assert outcome.decision.approvers == []

    shadow_result = _shadow_proposes(conn, config, "demo.undeclared")
    row_id = shadow.record(
        conn,
        make_request("demo.undeclared"),
        shadow_result,
        policy_label="candidate",
        now=FROZEN_NOW,
        live_decision=outcome.decision,
    )
    row = conn.execute("SELECT comparison FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["comparison"] == "live decided by default_deny; not modeled"


def _full_row(conn: Connection, *, audit_id: int, kind: str) -> dict[str, object]:
    """Every column of one `actions_audit` row, as a plain dict, plus its
    own `decision_digest` -- the comparison this round's own test makes,
    since `approvers_json` is part of the canonical record that digest
    covers, and a prior round's own narrower column check is exactly what
    let a change to it through undetected."""
    row = (
        conn.execute("SELECT * FROM actions_audit WHERE id=?", (audit_id,)).fetchone()
        if kind == "exec_intent"
        else conn.execute(
            "SELECT * FROM actions_audit WHERE parent_id=? AND kind=?", (audit_id, kind)
        ).fetchone()
    )
    assert row is not None
    record = {key: row[key] for key in row.keys()}
    record["decision_digest"] = decision_digest(row)
    return record


# Pinned to the row shape produced before the fix that copies resumption
# facts (approvers, escalation) back from the intent's own audit row, and
# reconfirmed identical at the current head. Request ids held fixed
# (below) so these are reproducible, not just "some value or other that
# happened not to be None".
_RESUME_APPROVAL_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000101")
_MANDATE_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000102")
_APPROVAL_REF_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000103")
_APPROVAL_REF_RESUMED_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000104")
_OVERRIDE_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000105")
_OVERRIDE_RESUMED_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000106")


def test_resume_approvals_row_matches_pinned_pre_fix_shape(
    conn: Connection,
    registry: ConnectorRegistry,
    config: EngineConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This test's own reason to exist: a fix made the comparison write
    `approvers_json` into this `exec_result` row, which the row used to
    always leave NULL. This pins the row -- and its
    `decision_digest` -- back to exactly that shape. It must fail against
    the replay-path fix's own behavior, where `approvers_json == '["sess-1"]'`
    on this row (the before-log for this fails on that line, before the
    digest is ever compared), and pass at this head."""
    monkeypatch.setattr(executor_mod, "uuid4", lambda: _RESUME_APPROVAL_REQUEST_ID)
    proposed = evaluate_and_execute(
        make_request("demo.confirm"), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert proposed.approval_id is not None
    result = resume_approval(
        proposed.approval_id, "sess-1", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert result.executed is True
    assert result.decision.approvers == ["sess-1"]  # the returned decision: unaffected

    row = _full_row(conn, audit_id=result.audit_id, kind="exec_result")
    assert row["approvers_json"] is None
    assert row["escalated_to"] is None
    assert row["escalated_at"] is None
    assert row["decision"] == "executed"
    assert row["connector_ok"] == 1
    assert row["reason_code"] == "passed"
    assert row["decision_digest"] == (
        "sha256:d9bad9c412e38a88c75be810a8b36ea4c877337547c0968b269869887081de5d"
    )


def test_a_mandate_resumptions_row_matches_pinned_pre_fix_shape(
    conn: Connection,
    registry: ConnectorRegistry,
    config: EngineConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mandate-ratified kind's own `exec_result` row -- same pin, same
    reason. Must fail against the replay-path fix's own behavior, where
    `approvers_json == '[]'` on this row, and pass at this head."""
    monkeypatch.setattr(executor_mod, "uuid4", lambda: _MANDATE_REQUEST_ID)
    private, public_key = _key_pair()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.mandatepay",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            requires_external_authorization=True,
        ),
    )
    registry.register("demo.mandatepay", mock.act_ok)

    def resolver(request: object) -> mandate.MandateVerdict:
        return mandate.MandateVerdict.PENDING

    cfg = dataclasses.replace(
        config, mandate_resolver=resolver, mandate_authority_public_key=public_key
    )
    pending = decide_and_reserve(
        make_request("demo.mandatepay"), conn=conn, config=cfg, now=FROZEN_NOW
    )
    assert isinstance(pending, ActionResult)
    assert pending.approval_id is not None
    approval_row = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (pending.approval_id,)
    ).fetchone()
    digest = approval_row["mandate_core_digest"]
    with tx(conn):
        ratified = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=private.sign(digest.encode("ascii")).hex(),
            authority_public_key=public_key,
            now=FROZEN_NOW,
        )
    assert ratified.authorised

    result = resume_ratification(
        pending.approval_id, conn=conn, registry=registry, config=cfg, now=FROZEN_NOW
    )
    assert result.executed is True
    assert result.decision.approvers == []  # the returned decision: unaffected

    row = _full_row(conn, audit_id=result.audit_id, kind="exec_result")
    assert row["approvers_json"] is None
    assert row["escalated_to"] is None
    assert row["escalated_at"] is None
    assert row["decision"] == "executed"
    assert row["connector_ok"] == 1
    assert row["reason_code"] == "passed"
    assert row["decision_digest"] == (
        "sha256:c3284d38666cea75159aa52a48afe4f126d9704c29dfcde7bcf6277a7efa66cf"
    )


def test_an_approval_ref_resumptions_row_matches_pinned_pre_fix_shape(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """The approval-ref kind's own `exec_result` row -- same pin, same
    reason. Must fail against the replay-path fix's own behavior, where
    `approvers_json == '["human-1"]'` on this row, and pass at this head."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.refpay",
            tier=Tier.CONFIRM,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    registry.register("demo.refpay", mock.act_ok)
    request = ActionRequest(
        request_id=_APPROVAL_REF_REQUEST_ID,
        action_type="demo.refpay",
        params={},
        source=Source.LLM,
        rationale="test",
        cost_eur=Decimal(0),
        created_at=FROZEN_NOW,
    )
    with tx(conn):
        approval_id = approvals.create(conn, request, config.approval_ttl_seconds, FROZEN_NOW)
        approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)

    resumed = request.model_copy(
        update={"request_id": _APPROVAL_REF_RESUMED_REQUEST_ID, "approval_ref": approval_id}
    )
    result = evaluate_and_execute(
        resumed, conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert result.executed is True
    assert result.decision.approvers == ["human-1"]  # the returned decision: unaffected

    row = _full_row(conn, audit_id=result.audit_id, kind="exec_result")
    assert row["approvers_json"] is None
    assert row["escalated_to"] is None
    assert row["escalated_at"] is None
    assert row["decision"] == "executed"
    assert row["connector_ok"] == 1
    assert row["reason_code"] == "passed"
    assert row["decision_digest"] == (
        "sha256:a075efb2c4fa7249cd9224029e869edc8d1c54a2d39c015985fcee1e39854c6e"
    )


def test_an_approved_overrides_row_matches_pinned_pre_fix_shape(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """The bare-override kind's own `exec_intent` row: the fix goes
    further here than the other three kinds -- it writes a stored `[]`
    where the pre-fix behavior wrote NULL, not merely a different non-NULL
    value. Must fail against the replay-path fix's own behavior, where
    `approvers_json == '[]'` on this row, and pass at this head."""
    request = ActionRequest(
        request_id=_OVERRIDE_REQUEST_ID,
        action_type="demo.confirm",
        params={},
        source=Source.UI,
        rationale="test",
        cost_eur=Decimal(0),
        created_at=FROZEN_NOW,
    )
    proposed = evaluate_and_execute(
        request, conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert proposed.approval_id is not None
    with tx(conn):
        original = approvals.cas_approve(conn, proposed.approval_id, "sess-1", FROZEN_NOW)
    resumed = original.model_copy(
        update={"request_id": _OVERRIDE_RESUMED_REQUEST_ID, "created_at": FROZEN_NOW}
    )
    result = evaluate_and_execute(
        resumed,
        conn=conn,
        registry=registry,
        config=config,
        now=FROZEN_NOW,
        approved_override=True,
    )
    assert result.executed is True
    assert result.decision.approvers == []  # the returned decision: unaffected

    row = _full_row(conn, audit_id=result.audit_id, kind="exec_intent")
    assert row["approvers_json"] is None
    assert row["escalated_to"] is None
    assert row["escalated_at"] is None
    assert row["decision"] == "executed"
    assert row["reason_code"] == "passed"
    assert row["decision_digest"] == (
        "sha256:e74d941f1b61cda4a1a889e17d35f47ca85ad80cab3892c3937e61726043e651"
    )


def test_a_replayed_resumptions_real_path_reads_not_modeled(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """A third place the same decision-without-approvers shape recurred:
    `audit.result_for_request_id`'s own `_row_decision`, which the
    idempotency guard returns for a repeated request_id -- a replay must
    reconstruct the same resumption facts the original call made, not a
    decision built fresh from the row with them left out."""
    proposed = evaluate_and_execute(
        make_request("demo.confirm"), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert proposed.approval_id is not None
    proposal_audit_id = proposed.audit_id
    with tx(conn):
        original = approvals.cas_approve(conn, proposed.approval_id, "sess-1", FROZEN_NOW)
    resumed = original.model_copy(update={"request_id": uuid4(), "created_at": FROZEN_NOW})

    first = evaluate_and_execute(
        resumed,
        conn=conn,
        registry=registry,
        config=config,
        now=FROZEN_NOW,
        approved_override=True,
        resumes_audit_id=proposal_audit_id,
    )
    assert first.executed is True

    replay = evaluate_and_execute(
        resumed,
        conn=conn,
        registry=registry,
        config=config,
        now=FROZEN_NOW,
        approved_override=True,
        resumes_audit_id=proposal_audit_id,
    )
    assert replay.audit_id == first.audit_id  # the idempotency guard, confirmed
    assert replay.decision.reason_code.value == "passed"

    shadow_result = _shadow_proposes(conn, config, "demo.confirm")
    row_id = shadow.record(
        conn,
        make_request("demo.confirm"),
        shadow_result,
        policy_label="candidate",
        now=FROZEN_NOW,
        live_decision=replay.decision,
    )
    row = conn.execute("SELECT comparison FROM shadow_decisions WHERE id=?", (row_id,)).fetchone()
    assert row["comparison"] == "live decided by passed; not modeled"
