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

from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlite3 import Connection

from niyam.guardrail import approvals, audit, bounds, caps, killswitch
from niyam.guardrail.models import (
    ActionRequest,
    ActionResult,
    CheckId,
    Decision,
    JsonValue,
    PolicyDecision,
    Source,
    Tier,
)
from niyam.guardrail.policy import PolicyStore
from niyam.store import bus
from niyam.store.db import tx

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
    config: "object",
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

    with tx(conn):
        # 1. KILL-SWITCH FIRST (invariant: before policy lookup).
        kill = killswitch.is_engaged(conn)

        # 2. POLICY LOOKUP / DEFAULT-DENY.
        policy = store.get(conn, request.action_type)
        nominal_tier = policy.tier

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

        # Tier-1 integrity: an auto action with no reversal cannot auto-execute.
        if (
            effective_tier == Tier.AUTO
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

        # 9. CAPS — check and reserve atomically inside this transaction.
        cap_result = caps.check_and_reserve(conn, policy, request, now, config.tz)
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


def report_result(
    intent: PermittedIntent,
    *,
    conn: Connection,
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
    with tx(conn):
        result_decision = PolicyDecision(
            decision=Decision.EXECUTED if ok else Decision.FAILED,
            effective_tier=intent.effective_tier,
            nominal_tier=intent.nominal_tier,
            reason_code=CheckId.PASSED,
        )
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
        bus.publish(
            conn,
            "action.executed" if ok else "action.failed",
            {"request_id": str(intent.request.request_id), "connector_ok": ok},
        )

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
