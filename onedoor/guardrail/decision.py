"""The decision half of the engine — the Policy Decision Point (PDP).

v0.2 splits the executor into two public phases so that enforcement can live
anywhere (an in-process connector registry, an MCP proxy, an API gateway
filter) while the decision semantics stay in exactly one place:

- :func:`decide_and_reserve` — Tx A. Runs the full ordered check pipeline
  (kill switch -> policy/default-deny -> tier-1 integrity -> bounds -> dry-run
  -> caps check-and-reserve) and records the execution *intent* in the
  append-only audit log. Returns either a terminal :class:`ActionResult`
  (denied / proposed / dry-run / observed / replayed) or a
  :class:`PermittedIntent` — an obligation for the caller to enforce.

- :func:`report_result` — Tx B. The enforcement point calls this exactly once
  after acting (or failing to act), which appends the linked result row and
  publishes the outcome.

The in-process executor (`evaluate_and_execute`) is now a thin composition of
these two phases around a connector call; external enforcement points compose
them around whatever their "act" is. The audit log, cap accounting, undo
windows and approval flow are identical in both cases — one door, wherever the
door is installed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from sqlite3 import Connection
from uuid import UUID

from onedoor.guardrail import approvals, audit, bounds, caps, killswitch
from onedoor.guardrail.models import (
    ActionRequest,
    ActionResult,
    CheckId,
    Decision,
    EngineConfigLike,
    JsonValue,
    PolicyDecision,
    Source,
    Tier,
)
from onedoor.guardrail.policy import PolicyStore
from onedoor.store import bus
from onedoor.store.clock import to_iso
from onedoor.store.db import tx

# EngineConfig lives in executor.py for backwards compatibility; import lazily
# to avoid a circular import at module load.


@dataclass(frozen=True)
class PermittedIntent:
    """A permitted action whose execution is now the caller's obligation.

    Produced by :func:`decide_and_reserve` after Tx A commits: the caps are
    reserved, the intent row is in the audit log, and the undo window (if any)
    is set. The enforcement point MUST follow up with :func:`report_result`
    exactly once, whatever happened.
    """

    request: ActionRequest
    intent_audit_id: int
    effective_tier: Tier
    nominal_tier: Tier
    compensating_command: str | None
    undo_until: datetime | None
    undo_of: int | None


def decide_and_reserve(
    request: ActionRequest,
    *,
    conn: Connection,
    config: EngineConfigLike,
    now: datetime,
    policy_store: PolicyStore | None = None,
    approved_override: bool = False,
) -> ActionResult | PermittedIntent:
    """Phase A: evaluate the ordered checks; reserve caps; record intent.

    Returns an :class:`ActionResult` when the decision is terminal (nothing to
    enforce), or a :class:`PermittedIntent` when the action may proceed and the
    caller owns execution + :func:`report_result`.
    """
    store = policy_store or PolicyStore()
    undo_of = request.parent_audit_id if request.source == Source.UNDO else None

    # --- Idempotency / replay guard (no transaction) ---
    prior = audit.result_for_request_id(conn, request.request_id)
    if prior is not None:
        return prior

    # Reclaim any reservation abandoned past its deadline before evaluating, so
    # budget a never-reported permit is still holding is freed for this request.
    reclaim_expired_reservations(conn, config, now)

    with tx(conn):
        # 1. KILL-SWITCH FIRST (invariant: before policy lookup).
        kill = killswitch.is_engaged(conn)

        # 2. POLICY LOOKUP / DEFAULT-DENY.
        policy = store.get(conn, request.action_type)
        nominal_tier = policy.tier

        # 2b. EFFECT RESOLUTION — declared labels plus deterministic parameter
        #     rules (a generic tool's effect can depend on its arguments).
        effects: list[str] = list(policy.effects)
        for rule in policy.param_effects:
            value = request.params.get(rule.param)
            if value is not None and re.fullmatch(rule.pattern, str(value)):
                effects.extend(e for e in rule.add_effects if e not in effects)
        effect_policies = [ep for e in effects if (ep := store.get_effect(conn, e)) is not None]

        # 3/4. Resolve effective tier (+ Tier-1 integrity, kill-switch clamp).
        reason_confirm = CheckId.TIER_CONFIRM
        if approved_override:
            if kill:
                decision = PolicyDecision(
                    decision=Decision.DENIED,
                    effective_tier=Tier.CONFIRM,
                    nominal_tier=nominal_tier,
                    reason_code=CheckId.KILL_SWITCH,
                    detail="kill switch engaged; approved action blocked",
                )
                aid = audit.append(
                    conn, request, decision, kind="decision", now=now, undo_of=undo_of
                )
                bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)
            effective_tier = Tier.AUTO
        elif policy.tier == Tier.OBSERVE:
            effective_tier = Tier.OBSERVE  # reads are exempt from the kill switch
        elif kill:
            effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.KILL_SWITCH
        else:
            effective_tier = policy.tier
            if policy.is_default_deny:
                reason_confirm = CheckId.DEFAULT_DENY
            # Effect tier floors: an action inherits the strictest floor of its
            # effects — aliasing-resistant escalation ("moves money" is Tier 3
            # no matter which tool name moved it).
            for ep in effect_policies:
                if ep.min_tier is not None and int(ep.min_tier) > int(effective_tier):
                    effective_tier = ep.min_tier
                    if effective_tier == Tier.CONFIRM:
                        reason_confirm = CheckId.EFFECT_FLOOR

        # Reversibility precondition: ANY tier that may execute without a human
        # (auto and auto_capped alike) requires a registered means of reversal.
        # Scoping this to Tier.AUTO alone let an irreversible action auto-execute
        # merely because it also carried a budget.
        if (
            effective_tier in (Tier.AUTO, Tier.AUTO_CAPPED)
            and not approved_override
            and not policy.compensating_command
        ):
            effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.NO_COMPENSATION

        # 5. OBSERVE — audit a no-op read and return.
        if effective_tier == Tier.OBSERVE:
            decision = PolicyDecision(
                decision=Decision.EXECUTED,
                effective_tier=Tier.OBSERVE,
                nominal_tier=nominal_tier,
                reason_code=CheckId.OBSERVE,
            )
            aid = audit.append(conn, request, decision, kind="decision", now=now, undo_of=undo_of)
            bus.publish(conn, "action.observed", {"request_id": str(request.request_id)})
            return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)

        # 6. BOUNDS — validated for every tier that could execute OR be proposed,
        #    so a human never approves an out-of-bounds action.
        bounds_result = bounds.validate(policy.bounds, request.params)
        if not bounds_result.ok:
            decision = PolicyDecision(
                decision=Decision.DENIED,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=CheckId.BOUNDS,
                detail=bounds_result.detail,
            )
            aid = audit.append(conn, request, decision, kind="decision", now=now, undo_of=undo_of)
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)

        # 7. TIER 3 — propose and confirm.
        if effective_tier == Tier.CONFIRM:
            approval_id = approvals.create(conn, request, config.approval_ttl_seconds, now)
            decision = PolicyDecision(
                decision=Decision.PROPOSED,
                effective_tier=Tier.CONFIRM,
                nominal_tier=nominal_tier,
                reason_code=reason_confirm,
                requires_approval=True,
                compensating_command=policy.compensating_command,
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_id=approval_id,
                undo_of=undo_of,
            )
            bus.publish(
                conn,
                "action.proposed",
                {"request_id": str(request.request_id), "approval_id": approval_id},
            )
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                approval_id=approval_id,
            )

        # --- Auto path (Tier 1, Tier 2, or approved override) ---

        # 8. DRY-RUN — before caps (a rehearsal must not spend a real budget).
        is_dry = not approved_override and (
            policy.dry_run or (policy.dry_run_until is not None and now < policy.dry_run_until)
        )
        if is_dry:
            decision = PolicyDecision(
                decision=Decision.DRY_RUN,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=CheckId.DRY_RUN,
                dry_run=True,
                detail="would have executed",
            )
            aid = audit.append(conn, request, decision, kind="decision", now=now, undo_of=undo_of)
            bus.publish(conn, "action.dry_run", {"request_id": str(request.request_id)})
            return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)

        # 9. CAPS — action caps AND effect-shared caps, all-or-nothing.
        cap_result = caps.check_and_reserve(
            conn,
            policy,
            request,
            now,
            config.tz,
            effect_caps=[(ep.effect, ep.caps) for ep in effect_policies],
        )
        if cap_result.exceeded:
            assert cap_result.reason is not None
            decision = PolicyDecision(
                decision=Decision.DENIED,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=cap_result.reason,
                detail=cap_result.detail,
            )
            aid = audit.append(conn, request, decision, kind="decision", now=now, undo_of=undo_of)
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)

        # 10. INTENT — record that we are about to execute. Set the undo window
        #     for reversible Tier-1 actions.
        undo_until = None
        if effective_tier == Tier.AUTO and not approved_override and policy.compensating_command:
            undo_until = now + timedelta(seconds=policy.undo_window_seconds)
        intent_decision = PolicyDecision(
            decision=Decision.EXECUTED,
            effective_tier=effective_tier,
            nominal_tier=nominal_tier,
            reason_code=CheckId.PASSED,
            compensating_command=policy.compensating_command,
        )
        intent_id = audit.append(
            conn,
            request,
            intent_decision,
            kind="exec_intent",
            now=now,
            undo_until=undo_until,
            undo_of=undo_of,
        )

        # 10b. RESERVATION LEDGER — if this permit reserved budget, record the
        #      exact deltas and a deadline so the reservation can be reclaimed
        #      (AADP section 6) should the permit never be reported. No caps
        #      reserved (tier-1, unbudgeted) means nothing to reclaim.
        ttl = int(getattr(config, "reservation_ttl_seconds", 3600) or 0)
        if cap_result.deltas and ttl > 0:
            deadline = now + timedelta(seconds=ttl)
            conn.execute(
                "INSERT INTO cap_reservations "
                "(intent_audit_id, request_id, deadline_utc, deltas_json, status, created_utc) "
                "VALUES (?, ?, ?, ?, 'held', ?)",
                (
                    intent_id,
                    str(request.request_id),
                    to_iso(deadline),
                    json.dumps([list(d) for d in cap_result.deltas]),
                    to_iso(now),
                ),
            )
    # ==== Tx A committed: caps reserved + intent recorded ====

    return PermittedIntent(
        request=request,
        intent_audit_id=intent_id,
        effective_tier=effective_tier,
        nominal_tier=nominal_tier,
        compensating_command=policy.compensating_command,
        undo_until=undo_until,
        undo_of=undo_of,
    )


def reclaim_expired_reservations(conn: Connection, config: EngineConfigLike, now: datetime) -> int:
    """Release the budget of every permit past its deadline with no report.

    A permit that reserved budget but was never reported holds that budget until
    reclaimed. Once the reservation's deadline (``execute_within``) has passed,
    this subtracts the reserved deltas back out of the cap counters, appends a
    ``reservation_expired`` row to the audit log, and voids the reservation.
    Per AADP section 6 the release is an audited event, not a silent timeout.

    Returns the number of reservations reclaimed. Safe to call on every decide
    (the open-reservation lookup is indexed and normally empty) or from a
    maintenance loop. A deadline in the future, or a reservation already settled
    or expired, is left untouched.
    """
    ttl = int(getattr(config, "reservation_ttl_seconds", 3600) or 0)
    if ttl <= 0:
        return 0
    now_iso = to_iso(now)
    reclaimed = 0
    with tx(conn):
        rows = conn.execute(
            "SELECT intent_audit_id, deltas_json FROM cap_reservations "
            "WHERE status='held' AND deadline_utc <= ? ORDER BY intent_audit_id",
            (now_iso,),
        ).fetchall()
        for r in rows:
            rid = int(r["intent_audit_id"])
            intent_row = conn.execute("SELECT * FROM actions_audit WHERE id=?", (rid,)).fetchone()
            if intent_row is not None:
                caps.release(
                    conn,
                    [tuple(d) for d in json.loads(r["deltas_json"], parse_float=Decimal)],
                )
                audit.append_expiry(
                    conn,
                    intent_row,
                    now,
                    detail="reservation reclaimed: deadline passed with no report",
                )
                bus.publish(
                    conn,
                    "action.reservation_expired",
                    {"request_id": intent_row["request_id"], "intent_audit_id": rid},
                )
            conn.execute(
                "UPDATE cap_reservations SET status='expired' WHERE intent_audit_id=?",
                (rid,),
            )
            reclaimed += 1
    return reclaimed


def report_result(
    intent: PermittedIntent,
    *,
    conn: Connection,
    config: EngineConfigLike | None = None,
    ok: bool,
    payload: dict[str, JsonValue] | None,
    error: str | None,
    now: datetime,
) -> ActionResult:
    """Phase B: append the linked execution result for a permitted intent.

    Must be called exactly once per :class:`PermittedIntent`, whatever the
    enforcement outcome — success, failure, or timeout. The audit log stays
    append-only: this adds a second row linked to the intent, never edits it.
    """
    # Settle the reservation so the reclaimer leaves its budget spent. If the
    # permit was already reclaimed (deadline passed before this report), the
    # reservation is 'expired', this matches nothing, and the released budget
    # stays released: the permit was void, and a late report is recorded for
    # audit but does not silently re-charge the counter.
    with tx(conn):
        conn.execute(
            "UPDATE cap_reservations SET status='settled' "
            "WHERE intent_audit_id=? AND status='held'",
            (intent.intent_audit_id,),
        )

    result_decision = PolicyDecision(
        decision=Decision.EXECUTED if ok else Decision.FAILED,
        effective_tier=intent.effective_tier,
        nominal_tier=intent.nominal_tier,
        reason_code=CheckId.PASSED,
    )
    topic = "action.executed" if ok else "action.failed"
    event = {"request_id": str(intent.request.request_id), "connector_ok": ok}
    batch = int(getattr(config, "audit_group_commit", 0) or 0)

    if batch > 0:
        # Buffered path: the row is queued and written with its neighbours. A crash
        # before the flush leaves an intent with no result — the recoverable state
        # invariant 9 already requires — never a permit that looks discharged.
        audit.append_buffered(
            conn,
            intent.request,
            result_decision,
            kind="exec_result",
            now=now,
            parent_id=intent.intent_audit_id,
            connector_ok=ok,
            error=error,
            payload=payload,
            undo_of=intent.undo_of,
            event_topic=topic,
            event_payload=json.dumps(event, default=str),
        )
        if audit.buffered_len(conn) >= batch:
            audit.flush(conn)
    else:
        with tx(conn):
            audit.append(
                conn,
                intent.request,
                result_decision,
                kind="exec_result",
                now=now,
                parent_id=intent.intent_audit_id,
                connector_ok=ok,
                error=error,
                payload=payload,
                undo_of=intent.undo_of,
            )
            bus.publish(conn, topic, event)

    return ActionResult(
        request_id=intent.request.request_id,
        decision=result_decision,
        executed=ok,
        connector_ok=ok,
        connector_payload=payload,
        error=error,
        audit_id=intent.intent_audit_id,
        undo_available_until=intent.undo_until if ok else None,
    )


NIL_REQUEST_ID = UUID(int=0)


def decide_raw(
    raw: Mapping[str, object],
    *,
    conn: Connection,
    config: EngineConfigLike,
    now: datetime,
    policy_store: PolicyStore | None = None,
) -> ActionResult | PermittedIntent:
    """Total form of :func:`decide_and_reserve` — never raises on a malformed request.

    ``decide_and_reserve`` takes a validated :class:`ActionRequest`, so a caller
    that hands it attacker-shaped input gets a ``ValidationError`` rather than a
    verdict. Fail-closed behaviour then depends on whether *that caller* wraps the
    call, i.e. on code the decision point does not own.

    ``decide_raw`` accepts the unvalidated mapping and turns a validation failure
    into an ordinary denial with reason ``malformed``, so the guarantee belongs to
    the decision point.

    Internal errors are deliberately **not** swallowed: an exception from the
    policy store, the database or the cap ledger propagates, because converting a
    bug into a routine denial would hide it. From an enforcement point's view an
    unreachable or erroring PDP is already governed by its configured
    unreachability behaviour.
    """
    try:
        request = ActionRequest.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - any validation failure is a denial
        request_id = raw.get("request_id") if isinstance(raw, Mapping) else None
        try:
            resolved = UUID(str(request_id))
        except (TypeError, ValueError):
            resolved = NIL_REQUEST_ID
        return ActionResult(
            request_id=resolved,
            decision=PolicyDecision(
                decision=Decision.DENIED,
                # No policy was resolved, so no tier applies; report the most
                # restrictive one rather than inventing a permissive default.
                effective_tier=Tier.CONFIRM,
                nominal_tier=Tier.CONFIRM,
                reason_code=CheckId.MALFORMED,
                detail=f"request failed validation: {type(exc).__name__}",
            ),
        )
    return decide_and_reserve(request, conn=conn, config=config, now=now, policy_store=policy_store)
