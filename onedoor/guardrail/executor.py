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

from onedoor.config import Settings
from onedoor.guardrail import approvals
from onedoor.guardrail import decision as decision_mod
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.models import (
    ActionRequest,
    ActionResult,
    JsonValue,
    Source,
)
from onedoor.guardrail.policy import PolicyStore
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.clock import now_utc
from onedoor.store.db import tx


@dataclass(frozen=True)
class EngineConfig:
    approval_ttl_seconds: int
    connector_timeout_seconds: float
    tz: ZoneInfo
    # Group-commit batch size for RESULT audit rows. 0 = off (default): every
    # report is its own durable transaction. Intent rows are never buffered —
    # invariant 9 requires them durable before the permit is returned.
    audit_group_commit: int = 0
    # How long a permit may hold its budget reservation before, absent a report,
    # the reservation is reclaimed and the permit voided (AADP section 6). This
    # is the "execute_within" deadline. 0 disables reclamation.
    reservation_ttl_seconds: int = 3600

    @classmethod
    def from_settings(cls, settings: Settings) -> EngineConfig:
        return cls(
            approval_ttl_seconds=settings.approval_ttl_seconds,
            connector_timeout_seconds=settings.connector_timeout_seconds,
            tz=ZoneInfo(settings.timezone),
            reservation_ttl_seconds=getattr(settings, "reservation_ttl_seconds", 3600),
        )


def _redact(message: str) -> str:
    return message[:200]


def _call_with_timeout(
    act: object, params: dict[str, JsonValue], timeout: float
) -> dict[str, JsonValue]:
    from onedoor.guardrail.registry import ActFn

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
    """Evaluate a request against policy and, if permitted, execute it.

    Since v0.2 this is a thin composition of the decision/enforcement split:
    :func:`onedoor.guardrail.decision.decide_and_reserve` (Tx A) -> connector call
    outside any DB lock -> :func:`onedoor.guardrail.decision.report_result` (Tx B).
    External enforcement points (an MCP proxy, a gateway filter) compose the
    same two phases around their own act.
    """
    outcome = decision_mod.decide_and_reserve(
        request,
        conn=conn,
        config=config,
        now=now,
        policy_store=policy_store,
        approved_override=approved_override,
    )
    if not isinstance(outcome, decision_mod.PermittedIntent):
        return outcome

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

    return decision_mod.report_result(
        outcome, conn=conn, config=config, ok=connector_ok, payload=payload, error=error, now=now
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
