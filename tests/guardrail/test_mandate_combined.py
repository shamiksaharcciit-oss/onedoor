"""A mandate deferral combined with an escalation of onedoor's own needs both authorities.

When the mandate layer defers an action that onedoor's own checks would already send to a
human (here: a tier-3 policy), there is one proposal, carrying onedoor's own reason, and
one approval that is released only when the mandate authority has ratified it AND an
approver has approved it. Neither authority alone resumes it.

Test keys are generated in-process, never written anywhere.
"""

from __future__ import annotations

import dataclasses
import json
from sqlite3 import Connection

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from onedoor.connectors import mock
from onedoor.guardrail import killswitch, mandate, policy_loader
from onedoor.guardrail.decision import ActionResult, decide_and_reserve
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig, resume_approval, resume_ratification
from onedoor.guardrail.models import Bounds, CheckId, Decision, Policy, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request

ACTION = "demo.mandate_confirm"


def _setup(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> tuple[EngineConfig, Ed25519PrivateKey]:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(strict_params=False),
            requires_external_authorization=True,
        ),
    )
    registry.register(ACTION, mock.act_ok)
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    cfg = dataclasses.replace(
        config,
        mandate_resolver=lambda request: mandate.MandateVerdict.PENDING,
        mandate_authority_public_key=public,
    )
    return cfg, private


def _propose(conn: Connection, cfg: EngineConfig) -> ActionResult:
    result = decide_and_reserve(make_request(ACTION), conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.approval_id is not None
    return result


def _ratify(conn: Connection, approval_id: int, private: Ed25519PrivateKey, public: bytes) -> None:
    digest = conn.execute(
        "SELECT mandate_core_digest FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()[0]
    with tx(conn):
        result = mandate.ratify(
            conn,
            core_digest_value=digest,
            signature_hex=private.sign(digest.encode("ascii")).hex(),
            authority_public_key=public,
            now=FROZEN_NOW,
        )
    assert result.authorised


def _intents(conn: Connection) -> int:
    return int(
        conn.execute("SELECT COUNT(*) FROM actions_audit WHERE kind='exec_intent'").fetchone()[0]
    )


def test_a_combined_deferral_proposes_once_with_onedoors_own_reason(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    cfg, _ = _setup(conn, config, registry)
    result = _propose(conn, cfg)

    assert result.decision.decision.value == "proposed"
    assert result.decision.reason_code.value == "tier_confirm"
    assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1
    trace = json.loads(
        conn.execute(
            "SELECT evaluation_trace_json FROM actions_audit WHERE id=?", (result.audit_id,)
        ).fetchone()[0]
    )
    mandate_entries = [e for e in trace if e["check"] == "external_authorization"]
    assert mandate_entries and mandate_entries[-1]["result"] == "fail"


def test_ratification_alone_does_not_resume_a_combined_approval(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    cfg, private = _setup(conn, config, registry)
    result = _propose(conn, cfg)
    assert result.approval_id is not None
    _ratify(conn, result.approval_id, private, cfg.mandate_authority_public_key)  # type: ignore[arg-type]

    with pytest.raises(ApprovalError):
        resume_ratification(
            result.approval_id, conn=conn, registry=registry, config=cfg, now=FROZEN_NOW
        )
    assert _intents(conn) == 0


def test_an_approver_alone_does_not_resume_a_combined_approval(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    cfg, _ = _setup(conn, config, registry)
    result = _propose(conn, cfg)
    assert result.approval_id is not None

    with pytest.raises(ApprovalError):
        resume_approval(
            result.approval_id, "operator", conn=conn, registry=registry, config=cfg, now=FROZEN_NOW
        )
    assert _intents(conn) == 0
    state = conn.execute("SELECT state FROM approvals WHERE id=?", (result.approval_id,))
    assert state.fetchone()[0] == "pending"


def test_both_authorities_together_release_a_combined_approval(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    cfg, private = _setup(conn, config, registry)
    result = _propose(conn, cfg)
    assert result.approval_id is not None
    _ratify(conn, result.approval_id, private, cfg.mandate_authority_public_key)  # type: ignore[arg-type]

    released = resume_approval(
        result.approval_id, "operator", conn=conn, registry=registry, config=cfg, now=FROZEN_NOW
    )

    assert released.executed is True
    state = conn.execute("SELECT state FROM approvals WHERE id=?", (result.approval_id,))
    assert state.fetchone()[0] == "consumed"


def test_an_engaged_kill_switch_denies_a_mandate_pending_action_outright(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    """A correct-but-untested interaction between the kill switch's own-first
    denial and the combined mandate deferral: a policy that would otherwise
    propose a combined (mandate-PENDING + onedoor's-own-escalation) approval,
    decided while the kill switch is engaged.

    The mandate resolver still gets consulted (nothing gates it on the kill
    switch), but by the time its PENDING verdict is read, `effective_tier` is
    already CONFIRM and `reason_confirm` is already KILL_SWITCH from the earlier
    tier-resolution step -- so the mandate branch only escalates a tier that is
    already at its ceiling, never overwriting the reason. The action must deny
    outright with `kill_switch`, not propose a combined approval: no approval row,
    no exec_intent, and nothing a later ratification could ever resume.
    """
    cfg, _ = _setup(conn, config, registry)
    with tx(conn):
        killswitch.set_engaged(conn, True)

    result = decide_and_reserve(make_request(ACTION), conn=conn, config=cfg, now=FROZEN_NOW)

    assert isinstance(result, ActionResult)
    assert result.decision.decision is Decision.DENIED
    assert result.decision.reason_code is CheckId.KILL_SWITCH
    assert result.approval_id is None
    assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    assert _intents(conn) == 0
    trace = json.loads(
        conn.execute(
            "SELECT evaluation_trace_json FROM actions_audit WHERE id=?", (result.audit_id,)
        ).fetchone()[0]
    )
    mandate_entries = [e for e in trace if e["check"] == "external_authorization"]
    assert mandate_entries and mandate_entries[-1]["result"] == "fail", (
        "the mandate resolver is still consulted (nothing gates it on the switch); "
        "it finding PENDING must not turn an outright denial into a proposal"
    )
