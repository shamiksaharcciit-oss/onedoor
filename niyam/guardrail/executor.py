"""The guardrail executor — the critical path.

``evaluate_and_execute`` is a deterministic state machine over one SQLite
connection. Ordered checks: kill-switch (FIRST) -> policy lookup / default-deny ->
Tier-1 integrity -> bounds -> dry-run -> caps -> execute. It is the ONLY module
permitted to import/call connector ``act_*`` functions, via the injected
``ConnectorRegistry``.

Two-phase execution keeps the connector network call outside any DB lock:
Tx A decides + reserves caps + records intent, the connector runs unlocked, Tx B
appends the result. The audit log stays append-only throughout (two linked rows
for executed actions).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from sqlite3 import Connection
from uuid import uuid4
from zoneinfo import ZoneInfo

from niyam.config import Settings
from niyam.guardrail import approvals, audit, bounds, caps, killswitch
from niyam.guardrail.errors import ApprovalError
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
from niyam.guardrail.registry import ConnectorRegistry
from niyam.store import bus
from niyam.store.clock import now_utc
from niyam.store.db import tx


@dataclass(frozen=True)
class EngineConfig:
    approval_ttl_seconds: int
    connector_timeout_seconds: float
    tz: ZoneInfo

    @classmethod
    def from_settings(cls, settings: Settings) -> EngineConfig:
        return cls(
            approval_ttl_seconds=settings.approval_ttl_seconds,
            connector_timeout_seconds=settings.connector_timeout_seconds,
            tz=ZoneInfo(settings.timezone),
        )


def _redact(message: str) -> str:
    return message[:200]


def _call_with_timeout(
    act: object, params: dict[str, JsonValue], timeout: float
) -> dict[str, JsonValue]:
    from niyam.guardrail.registry import ActFn

    fn: ActFn = act  # type: ignore[assignment]
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn, params)
    try:
        return future.result(timeout=timeout)
    finally:
        # Don't block on a still-running connector call (the worker can't be
        # cancelled once started); return immediately after a timeout.
        pool.shutdown(wait=False, cancel_futures=True)


def evaluate_and_execute(
    request: ActionRequest,
    *,
    conn: Connection,
    registry: ConnectorRegistry,
    config: EngineConfig,
    now: datetime,
    policy_store: PolicyStore | None = None,
    approved_override: bool = False,
) -> ActionResult:
    """Evaluate a request against policy and, if permitted, execute it."""
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
                # Even an approved action does not execute while killed. Block, do
                # not create a new approval (would loop).
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

        # 10. INTENT — record that we are about to execute. Set the undo window for
        #     reversible Tier-1 actions.
        undo_until = None
        if effective_tier == Tier.AUTO and not approved_override and policy.compensating_command:
            from datetime import timedelta

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

    # --- CONNECTOR CALL (outside any DB lock), fail-soft. ---
    connector_ok: bool
    error: str | None
    payload: dict[str, JsonValue] | None
    act = registry.resolve(request.action_type)
    if act is None:
        connector_ok, error, payload = False, "no connector registered for action_type", None
    else:
        try:
            payload = _call_with_timeout(act, request.params, config.connector_timeout_seconds)
            connector_ok, error = True, None
        except FuturesTimeout:
            connector_ok, error, payload = False, "connector timeout", None
        except Exception as exc:
            connector_ok, error, payload = False, _redact(str(exc)), None

    # --- Tx B: append the execution result. ---
    with tx(conn):
        result_decision = PolicyDecision(
            decision=Decision.EXECUTED if connector_ok else Decision.FAILED,
            effective_tier=effective_tier,
            nominal_tier=nominal_tier,
            reason_code=CheckId.PASSED,
        )
        audit.append(
            conn,
            request,
            result_decision,
            kind="exec_result",
            now=now,
            parent_id=intent_id,
            connector_ok=connector_ok,
            error=error,
            payload=payload,
            undo_of=undo_of,
        )
        bus.publish(
            conn,
            "action.executed" if connector_ok else "action.failed",
            {"request_id": str(request.request_id), "connector_ok": connector_ok},
        )

    return ActionResult(
        request_id=request.request_id,
        decision=result_decision,
        executed=connector_ok,
        connector_ok=connector_ok,
        connector_payload=payload,
        error=error,
        audit_id=intent_id,
        undo_available_until=undo_until if connector_ok else None,
    )


def propose_action(
    action_type: str,
    params: dict[str, JsonValue],
    rationale: str,
    *,
    conn: Connection,
    registry: ConnectorRegistry,
    config: EngineConfig,
    source: Source = Source.LLM,
    session_id: str | None = None,
    cost_eur: Decimal = Decimal(0),
    now: datetime | None = None,
    policy_store: PolicyStore | None = None,
) -> ActionResult:
    """The single write path. Mints the request id server-side (invariant 1/3/11)."""
    when = now or now_utc()
    request = ActionRequest(
        request_id=uuid4(),
        action_type=action_type,
        params=params,
        source=source,
        rationale=rationale,
        session_id=session_id,
        cost_eur=cost_eur,
        created_at=when,
    )
    return evaluate_and_execute(
        request, conn=conn, registry=registry, config=config, now=when, policy_store=policy_store
    )


def resume_approval(
    approval_id: int,
    session_id: str,
    *,
    conn: Connection,
    registry: ConnectorRegistry,
    config: EngineConfig,
    now: datetime | None = None,
    policy_store: PolicyStore | None = None,
) -> ActionResult:
    """Approve a Tier-3 request (auth-gated) and resume it through the full pipeline."""
    when = now or now_utc()
    with tx(conn):
        original = approvals.cas_approve(conn, approval_id, session_id, when)
    resumed = original.model_copy(update={"request_id": uuid4(), "created_at": when})
    result = evaluate_and_execute(
        resumed,
        conn=conn,
        registry=registry,
        config=config,
        now=when,
        policy_store=policy_store,
        approved_override=True,
    )
    with tx(conn):
        approvals.mark_executed(conn, approval_id, result.audit_id)
    return result


def deny_approval(
    approval_id: int, session_id: str, *, conn: Connection, now: datetime | None = None
) -> None:
    when = now or now_utc()
    with tx(conn):
        approvals.deny(conn, approval_id, session_id, when)


__all__ = [
    "ApprovalError",
    "EngineConfig",
    "deny_approval",
    "evaluate_and_execute",
    "propose_action",
    "resume_approval",
]
