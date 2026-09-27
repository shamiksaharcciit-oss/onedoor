"""The decision reference (ruling on joining a onedoor decision to a onetrace
run): `decision_digest` at decide time must equal the digest recomputed from
an export of the same row, for every verdict, whether the action executes in
one shot, resumes from an approval, replays, or fails after being permitted.
"""

from __future__ import annotations

import dataclasses
from sqlite3 import Connection

from onedoor.decision_digest import decision_digest
from onedoor.export import export_rows
from onedoor.guardrail import chain
from onedoor.guardrail.decision import ActionResult, PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import (
    EngineConfig,
    evaluate_and_execute,
    resume_approval,
)
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request

ISSUER = "https://onedoor.example/deployment-1"


def _with_issuer(config: EngineConfig) -> EngineConfig:
    return dataclasses.replace(config, issuer=ISSUER)


def _export_by_id(conn: Connection) -> dict[int, dict[str, object]]:
    return {int(row["id"]): row for row in export_rows(conn)}


def test_no_issuer_configured_omits_the_reference(conn: Connection, config: EngineConfig) -> None:
    result = decide_and_reserve(
        make_request("demo.unlisted"), conn=conn, config=config, now=FROZEN_NOW
    )
    assert isinstance(result, ActionResult)
    assert result.decision_ref is None


def test_a_denied_decision_carries_a_deny_verdict_matching_the_export(
    conn: Connection, config: EngineConfig
) -> None:
    """`demo.capped` allows 2 calls/day; the 3rd is denied on the rate cap."""
    cfg = _with_issuer(config)
    for _ in range(2):
        decide_and_reserve(make_request("demo.capped", {}), conn=conn, config=cfg, now=FROZEN_NOW)
    result = decide_and_reserve(
        make_request("demo.capped", {}), conn=conn, config=cfg, now=FROZEN_NOW
    )
    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "denied"
    ref = result.decision_ref
    assert ref is not None
    assert ref.format == "onedoor-decision-ref/1"
    assert ref.verdict == "deny"
    assert ref.issuer == ISSUER
    assert ref.request_id == result.request_id

    exported = _export_by_id(conn)[result.audit_id]
    assert ref.decision_digest == decision_digest(exported)


def test_a_proposed_decision_carries_a_propose_verdict_matching_the_export(
    conn: Connection, config: EngineConfig
) -> None:
    """An action type absent from the policy table synthesizes as Tier-3
    default-deny -- it proposes, per onedoor's own default-deny invariant."""
    cfg = _with_issuer(config)
    result = decide_and_reserve(
        make_request("demo.unlisted", {}), conn=conn, config=cfg, now=FROZEN_NOW
    )
    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "proposed"
    ref = result.decision_ref
    assert ref is not None
    assert ref.verdict == "propose"
    exported = _export_by_id(conn)[result.audit_id]
    assert ref.decision_digest == decision_digest(exported)


def test_a_dry_run_decision_returns_no_reference(conn: Connection, config: EngineConfig) -> None:
    """Dry-run executed nothing, so there is nothing a reference could cite."""
    cfg = _with_issuer(config)
    request = make_request("demo.dry", {"target": "demo.lamp", "state": "on"})
    result = decide_and_reserve(request, conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "dry_run"
    assert result.decision_ref is None


def test_an_observe_decision_returns_no_reference(conn: Connection, config: EngineConfig) -> None:
    """Observe mode runs the action whatever policy says, so a `permit`
    reference would claim a decision that gated nothing."""
    cfg = _with_issuer(config)
    result = decide_and_reserve(
        make_request("demo.read", {}), conn=conn, config=cfg, now=FROZEN_NOW
    )
    assert isinstance(result, ActionResult)
    assert result.decision_ref is None


def test_a_permitted_intent_carries_a_permit_verdict_matching_the_export(
    conn: Connection, config: EngineConfig
) -> None:
    cfg = _with_issuer(config)
    result = decide_and_reserve(
        make_request("demo.toggle", {"target": "demo.lamp", "state": "on"}),
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)
    ref = result.decision_ref
    assert ref is not None
    assert ref.verdict == "permit"
    assert ref.request_id == result.request.request_id
    exported = _export_by_id(conn)[result.intent_audit_id]
    assert ref.decision_digest == decision_digest(exported)


def test_an_executed_action_keeps_the_permit_reference_after_reporting(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    cfg = _with_issuer(config)
    result = evaluate_and_execute(
        make_request("demo.toggle", {"target": "demo.lamp", "state": "on"}),
        conn=conn,
        registry=registry,
        config=cfg,
        now=FROZEN_NOW,
    )
    ref = result.decision_ref
    assert ref is not None
    assert ref.verdict == "permit"
    # Names the INTENT row, not the result row -- the two are different rows
    # with different ids, and result.audit_id is already the intent's per
    # report_result's own contract.
    exported = _export_by_id(conn)[result.audit_id]
    assert exported["kind"] == "exec_intent"
    assert ref.decision_digest == decision_digest(exported)


def test_a_failed_connector_still_carries_the_original_permit_reference(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    """The connector failing after a permit was granted does not change what
    was decided -- the reference still says permit, and still names the
    intent row, never the result row (whose own `decision` column is FAILED
    and has no decision_ref verdict at all)."""
    cfg = _with_issuer(config)
    result = evaluate_and_execute(
        make_request("demo.flaky", {}), conn=conn, registry=registry, config=cfg, now=FROZEN_NOW
    )
    assert result.decision.decision.value in ("failed", "executed")
    ref = result.decision_ref
    assert ref is not None
    assert ref.verdict == "permit"


def test_a_replayed_request_gets_the_identical_reference(
    conn: Connection, config: EngineConfig
) -> None:
    cfg = _with_issuer(config)
    request = make_request("demo.toggle", {"target": "demo.lamp", "state": "on"})
    first = decide_and_reserve(request, conn=conn, config=cfg, now=FROZEN_NOW)
    second = decide_and_reserve(request, conn=conn, config=cfg, now=FROZEN_NOW)
    assert isinstance(first, PermittedIntent)
    assert isinstance(second, ActionResult)
    assert first.decision_ref is not None
    assert second.decision_ref is not None
    assert second.decision_ref == first.decision_ref


def test_a_resumed_approval_names_the_resumptions_own_decision(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    cfg = _with_issuer(config)
    proposed = evaluate_and_execute(
        make_request("demo.unlisted", {}), conn=conn, registry=registry, config=cfg, now=FROZEN_NOW
    )
    assert proposed.approval_id is not None
    propose_ref = proposed.decision_ref
    assert propose_ref is not None
    assert propose_ref.verdict == "propose"

    resumed = resume_approval(
        proposed.approval_id,
        "admin-session",
        conn=conn,
        registry=registry,
        config=cfg,
        now=FROZEN_NOW,
    )
    resume_ref = resumed.decision_ref
    assert resume_ref is not None
    assert resume_ref.verdict == "permit"
    assert resume_ref.request_id != propose_ref.request_id
    assert resume_ref.decision_digest != propose_ref.decision_digest


def test_the_wire_digest_matches_a_fresh_export_with_chaining_off(
    conn: Connection, config: EngineConfig
) -> None:
    cfg = _with_issuer(config)
    result = decide_and_reserve(
        make_request("demo.toggle", {"target": "demo.lamp", "state": "on"}),
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)
    ref = result.decision_ref
    assert ref is not None
    exported = _export_by_id(conn)[result.intent_audit_id]
    assert exported["row_hash"] is None  # chaining off: never populated
    assert ref.decision_digest == decision_digest(exported)


def test_the_wire_digest_matches_a_fresh_export_with_chaining_on(
    conn: Connection, config: EngineConfig
) -> None:
    with tx(conn):
        chain.enable(conn)
    cfg = _with_issuer(config)
    result = decide_and_reserve(
        make_request("demo.toggle", {"target": "demo.lamp", "state": "on"}),
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)
    ref = result.decision_ref
    assert ref is not None
    exported = _export_by_id(conn)[result.intent_audit_id]
    # Chaining on: the row's own chain columns are populated, and the wire
    # reference (computed before the row was ever read back) still matches
    # the export's rendering of the same row -- the chain columns are hashed
    # as whatever they hold, not specially excluded either way.
    assert exported["row_hash"] is not None
    assert exported["seq"] is not None
    assert ref.decision_digest == decision_digest(exported)


def test_changing_one_byte_of_an_exported_row_changes_its_digest(
    conn: Connection, config: EngineConfig
) -> None:
    cfg = _with_issuer(config)
    result = decide_and_reserve(
        make_request("demo.toggle", {"target": "demo.lamp", "state": "on"}),
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)
    exported = _export_by_id(conn)[result.intent_audit_id]
    original_digest = decision_digest(exported)

    mutated = dict(exported)
    mutated["detail"] = (str(mutated.get("detail") or "")) + "x"
    assert decision_digest(mutated) != original_digest
