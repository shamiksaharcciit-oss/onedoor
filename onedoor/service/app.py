"""The onedoor decision service — the PDP over HTTP (v0.3).

Any enforcement point in any language can now consult the engine:

    POST /v1/decide            submit an ActionRequest -> decision (+ obligation)
    POST /v1/report            report the enforcement outcome for a permitted intent
    GET  /v1/approvals         list pending approvals              (admin)
    POST /v1/approvals/{id}/approve   approve -> permitted intent  (admin)
    POST /v1/approvals/{id}/deny      deny                         (admin)
    POST /v1/killswitch        engage/release the kill switch      (admin)
    GET  /v1/health            liveness + engine state

Authentication: static API keys with a two-role split from day one —
*decide* keys may decide and report; *admin* keys may additionally approve,
deny, and operate the kill switch. Set ``ONEDOOR_DECIDE_KEYS`` and
``ONEDOOR_ADMIN_KEYS`` (comma-separated) and send ``Authorization: Bearer <key>``.
Separation of duties is a governance property: the process that asks for
permission should not be the process that grants it.

Obligations across the wire: a permitted decision returns an
``intent_audit_id``; the caller enforces, then reports. The service keeps the
pending-intent state in memory (single-process, self-hosted v0.3); a restart
between decide and report leaves the honest "intended, unconfirmed" row in
the audit log, and v0.4 rebuilds intents from that row instead of memory.

Observability: if ``opentelemetry-api`` is installed, every decision emits a
span (action type, outcome, reason, tier) and counters; without it, the
no-op API keeps the code path identical. The engine never requires a
collector.

Run:  ONEDOOR_DECIDE_KEYS=dev ONEDOOR_ADMIN_KEYS=root \\
      uvicorn onedoor.service.app:create_app --factory --port 8470
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from onedoor.guardrail import approvals, killswitch, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Budget, Decision, Source
from onedoor.service.notify import Notifier, build_notifier
from onedoor.service.telemetry import record_decision, span
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

# ----------------------------- auth ------------------------------------------


def _keys(env: str) -> set[str]:
    return {k.strip() for k in os.environ.get(env, "").split(",") if k.strip()}


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


def require_decide(authorization: str | None = Header(default=None)) -> str:
    token = _extract_bearer(authorization)
    if token in _keys("ONEDOOR_DECIDE_KEYS") or token in _keys("ONEDOOR_ADMIN_KEYS"):
        return token
    raise HTTPException(status_code=403, detail="key lacks decide role")


def require_admin(authorization: str | None = Header(default=None)) -> str:
    token = _extract_bearer(authorization)
    if token in _keys("ONEDOOR_ADMIN_KEYS"):
        return token
    raise HTTPException(status_code=403, detail="key lacks admin role")


# ----------------------------- wire models ------------------------------------


class DecideBody(BaseModel):
    action_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    source: Source = Source.LLM
    request_id: UUID | None = None  # omit to let the service mint one


class DecideReply(BaseModel):
    decision: str
    reason: str
    detail: str | None = None
    effective_tier: int
    request_id: UUID
    audit_id: int | None = None
    approval_id: int | None = None
    intent_audit_id: int | None = None  # present iff permitted: enforce, then report
    undo_until: datetime | None = None
    budget: Budget | None = None
    """ND-003. Present **iff** the verdict is a denial with reason `cap_value` or
    `cap_rate` -- the machine-readable budget state that `aadp/0.2`'s unit-neutral
    codes no longer carry. A PEP can act on this; it could not act on the prose in
    `detail`."""


class ReportBody(BaseModel):
    intent_audit_id: int
    ok: bool
    payload: dict[str, Any] | None = None
    error: str | None = None


class KillBody(BaseModel):
    engaged: bool
    origin: str = "service"


class ApprovalView(BaseModel):
    id: int
    action_type: str
    params: dict[str, Any]
    rationale: str
    state: str
    expires_at: datetime


# ----------------------------- app --------------------------------------------


class EngineState:
    """Single-process engine state: one connection, one intent registry."""

    def __init__(self, db_path: str, policies: Path) -> None:
        db = Database(db_path)
        db.init()
        self.conn = db.connect(check_same_thread=False)
        policy_loader.load_file(self.conn, policies)
        self.config = EngineConfig(
            approval_ttl_seconds=int(os.environ.get("ONEDOOR_APPROVAL_TTL", "3600")),
            connector_timeout_seconds=30.0,
            tz=ZoneInfo(os.environ.get("ONEDOOR_TZ", "UTC")),
        )
        self.lock = threading.Lock()
        self.pending: dict[int, PermittedIntent] = {}
        self.notifier: Notifier = build_notifier()


def _decide_reply(outcome: Any, state: EngineState) -> DecideReply:
    if isinstance(outcome, PermittedIntent):
        state.pending[outcome.intent_audit_id] = outcome
        return DecideReply(
            decision="permitted",
            reason="passed",
            effective_tier=int(outcome.effective_tier),
            request_id=outcome.request.request_id,
            intent_audit_id=outcome.intent_audit_id,
            undo_until=outcome.undo_until,
        )
    d = outcome.decision
    return DecideReply(
        decision=d.decision.value,
        reason=d.reason_code.value,
        detail=d.detail,
        effective_tier=int(d.effective_tier),
        request_id=outcome.request_id,
        audit_id=outcome.audit_id,
        approval_id=outcome.approval_id,
        budget=d.budget,
    )


def create_app(db_path: str | None = None, policies: str | None = None) -> FastAPI:
    state = EngineState(
        db_path or os.environ.get("ONEDOOR_DB", "onedoor-service.db"),
        Path(policies or os.environ.get("ONEDOOR_POLICIES", "config/policies.yaml")),
    )
    app = FastAPI(title="onedoor decision service", version="0.3.0")
    app.state.engine = state

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        with state.lock:
            killed = killswitch.is_engaged(state.conn)
        return {"status": "ok", "kill_switch": killed, "pending_intents": len(state.pending)}

    @app.post("/v1/decide", response_model=DecideReply)
    def decide(body: DecideBody, _key: str = Depends(require_decide)) -> DecideReply:
        now = now_utc()
        request = ActionRequest(
            request_id=body.request_id or uuid4(),
            action_type=body.action_type,
            params=body.params,
            source=body.source,
            rationale=body.rationale or f"service decide {body.action_type}",
            created_at=now,
        )
        with span("onedoor.decide", body.action_type), state.lock:
            outcome = decide_and_reserve(request, conn=state.conn, config=state.config, now=now)
        reply = _decide_reply(outcome, state)
        record_decision(body.action_type, reply.decision, reply.reason, reply.effective_tier)
        if reply.decision == Decision.PROPOSED.value and reply.approval_id is not None:
            state.notifier.proposed(
                reply.approval_id, body.action_type, body.params, body.rationale
            )
        return reply

    @app.post("/v1/report", response_model=DecideReply)
    def report(body: ReportBody, _key: str = Depends(require_decide)) -> DecideReply:
        intent = state.pending.pop(body.intent_audit_id, None)
        if intent is None:
            raise HTTPException(status_code=404, detail="unknown or already-reported intent")
        with span("onedoor.report", intent.request.action_type), state.lock:
            result = report_result(
                intent,
                conn=state.conn,
                ok=body.ok,
                payload=body.payload,
                error=body.error,
                now=now_utc(),
            )
        record_decision(
            intent.request.action_type,
            result.decision.decision.value,
            "reported",
            int(intent.effective_tier),
        )
        return _decide_reply(result, state)

    @app.get("/v1/approvals", response_model=list[ApprovalView])
    def list_approvals(_key: str = Depends(require_admin)) -> list[ApprovalView]:
        with state.lock:
            rows = approvals.list_pending(state.conn)
        return [
            ApprovalView(
                id=a.approval_id,
                action_type=a.request.action_type,
                params=dict(a.request.params),
                rationale=a.request.rationale,
                state=a.state.value,
                expires_at=a.expires_at,
            )
            for a in rows
        ]

    @app.post("/v1/approvals/{approval_id}/approve", response_model=DecideReply)
    def approve(approval_id: int, _key: str = Depends(require_admin)) -> DecideReply:
        now = now_utc()
        with state.lock:
            try:
                original = approvals.cas_approve(state.conn, approval_id, f"key:{_key[:6]}", now)
            except ApprovalError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            resumed = original.model_copy(update={"request_id": uuid4(), "created_at": now})
            outcome = decide_and_reserve(
                resumed, conn=state.conn, config=state.config, now=now, approved_override=True
            )
            if isinstance(outcome, PermittedIntent):
                approvals.mark_executed(state.conn, approval_id, outcome.intent_audit_id)
        return _decide_reply(outcome, state)

    @app.post("/v1/approvals/{approval_id}/deny")
    def deny(approval_id: int, _key: str = Depends(require_admin)) -> dict[str, str]:
        with state.lock:
            try:
                approvals.deny(state.conn, approval_id, f"key:{_key[:6]}", now_utc())
            except ApprovalError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"status": "denied"}

    @app.post("/v1/killswitch")
    def kill(body: KillBody, _key: str = Depends(require_admin)) -> dict[str, Any]:
        with state.lock:
            killswitch.set_engaged(state.conn, body.engaged, origin=body.origin)
        return {"kill_switch": body.engaged}

    return app
