"""The onedoor decision service — the PDP over HTTP (v0.3).

Any enforcement point in any language can now consult the engine:

    POST /v1/decide            submit an ActionRequest -> decision (+ obligation)
    POST /v1/report            report the enforcement outcome for a permitted intent
    GET  /v1/approvals         list pending approvals              (admin)
    POST /v1/approvals/{id}/approve   approve -> permitted intent  (admin)
    POST /v1/approvals/{id}/grant      approve only, no resume      (admin)
    POST /v1/approvals/{id}/deny      deny                         (admin)
    GET  /v1/approvals/by-link/{token}  confirmation page only, never acts
    POST /v1/approvals/by-link/{token}  acts -- approve or deny, by the
                                         token's own claim  (unauthenticated;
                                         the signed token is the credential)
    POST /v1/killswitch        engage/release the kill switch      (admin)
    GET  /v1/health            liveness + engine state

Authentication: static API keys with a two-role split —
*decide* keys may decide and report; *admin* keys may list, approve and deny
approvals and operate the kill switch, and nothing else. Set
``ONEDOOR_DECIDE_KEYS`` and ``ONEDOOR_ADMIN_KEYS`` (comma-separated) and send
``Authorization: Bearer <key>``. A key in both sets stops the service from
starting: the process that asks for permission is never the one that grants it.

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

A deployment using signed approval links (below) should also consider
``--no-access-log``: this module installs a filter on uvicorn's own
access logger that redacts a by-link token from every line it writes,
but a log sink outside this process -- a reverse
proxy, a load balancer -- sees the real request line regardless, which
this process has no way to filter. ``--no-access-log`` removes the
request-line log at its source instead of relying on a filter catching
every path that writes it.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from onedoor.guardrail import approval_link, approvals, audit, killswitch, policy_loader
from onedoor.guardrail import rebuild as rebuild_module
from onedoor.guardrail.approval_link import LinkVerifyStatus, NotifyConfig
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.errors import ApprovalError, NeedsMoreApprovers, ReportError
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Budget, Decision, DecisionRef, Outcome, Source
from onedoor.guardrail.policy import PolicyStore
from onedoor.guardrail.received import extract_raw_member
from onedoor.integrations import approval_notify
from onedoor.service import keys
from onedoor.service.notify import Notifier, build_notifier
from onedoor.service.telemetry import record_decision, span
from onedoor.store.clock import now_utc, to_iso
from onedoor.store.db import Database

log = logging.getLogger("onedoor.service.approval_link")
"""The signed-approval-link routes' own access/error logger. Every line this module writes through it names the route with the
token replaced by the literal text `<token>` -- never the real value,
whether the request succeeded, was refused, or crashed."""

_BY_LINK_TOKEN_RE = re.compile(r"(/v1/approvals/by-link/)([^\s\"?]+)")


class _ByLinkTokenRedactingFilter(logging.Filter):
    """This module's own `log` already redacts, but
    uvicorn's OWN `uvicorn.access` logger is a separate
    logger this module never writes to -- it logs the real request line,
    token included, regardless of what this module's handlers do. Installed
    on that logger (see `create_app`), this filter rewrites a by-link
    token out of a record's own args (uvicorn's `AccessFormatter` reads
    `record.args` as `(client_addr, method, full_path, http_version,
    status_code)`) before formatting, so the real token never reaches
    wherever the access log is written."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _BY_LINK_TOKEN_RE.sub(r"\1<token>", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        elif isinstance(record.msg, str):
            record.msg = _BY_LINK_TOKEN_RE.sub(r"\1<token>", record.msg)
        return True


def _set_link_page_headers(response: Response) -> None:
    """Both by-link routes carry this: no referrer leaves the page, no
    cache stores it, and its own CSP loads nothing from another origin --
    the page's whole body is already in this one JSON response, and it has
    no reason to fetch, script, or link out anywhere."""
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'"


# ----------------------------- auth ------------------------------------------


def _keys(env: str) -> set[str]:
    return {k.strip() for k in os.environ.get(env, "").split(",") if k.strip()}


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


def require_decide(authorization: str | None = Header(default=None)) -> str:
    token = _extract_bearer(authorization)
    if token in _keys("ONEDOOR_DECIDE_KEYS"):
        return token
    raise HTTPException(status_code=403, detail="key lacks decide role")


def _refuse_overlapping_roles() -> None:
    """Each key holds exactly one role. A key in both sets would let one credential
    propose an action and approve it, so the service does not start. The message names
    no key: it is the kind of line that ends up in a startup log."""
    shared = _keys("ONEDOOR_DECIDE_KEYS") & _keys("ONEDOOR_ADMIN_KEYS")
    if shared:
        raise RuntimeError(
            f"{len(shared)} key(s) appear in both ONEDOOR_DECIDE_KEYS and "
            f"ONEDOOR_ADMIN_KEYS; each key must hold exactly one role"
        )


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
    approval_ref: int | None = None
    """Same field as the engine's `ActionRequest.approval_ref`
    (models.py) -- an enforcement point resuming a previously-approved action
    presents it here on a fresh request. Absent, invalid, expired, consumed or
    mismatched all evaluate as absent (ND-009); the engine, never this route,
    decides which."""
    presented_audience: str | None = None
    """Same field as `ActionRequest.presented_audience` -- the
    audience URI this enforcement point declares it will present the permit to,
    compared against the action type's `present_bound` when one is declared."""
    untrusted: list[str] = Field(default_factory=list)
    """Same field as `ActionRequest.untrusted` -- dotted paths into `params`
    this enforcement point asserts are derived from content it does not
    control. Absent means nothing is marked, the same default a 0.10.x caller
    already produces."""
    session_id: str | None = None
    """Same field as `ActionRequest.session_id` -- the sequence-tracking key
    (onedoor 0.11). Absent means no sequence tracking for this call, the same
    default a 0.10.x caller already produces."""
    plan_ref: int | None = Field(default=None, strict=True)
    """Same field as `ActionRequest.plan_ref` (onedoor 0.11). Absent,
    invalid, expired, exhausted or mismatched all evaluate as
    absent; the engine, never this route, decides which.
    `strict=True` so this takes a plain integer only -- `true`, `"1"`
    and other JSON shapes pydantic's own lax `int` coercion would
    otherwise accept (including a bool, itself an `int` subclass) are
    refused with `422`, matching what the MCP proxy's own `isinstance(x,
    int) and not isinstance(x, bool)` check already enforces."""


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
    """ND-003. Present **iff** the verdict is a denial with reason `budget_exhausted`
    or `rate_exhausted` -- the machine-readable budget state that these
    unit-neutral codes no longer carry by themselves. A PEP can act on this; it
    could not act on the prose in `detail`. A row sealed before 0.8.0 carries
    this same field under the deprecated `cap_value`/`cap_rate` reasons, in the
    shape those codes used."""
    present_bound: str | None = None
    """The audience this permit may be exercised against. Present iff permitted
    and the policy declared one. A PEP that does not recognize this obligation
    MUST refuse to exercise the permit itself and report `not_attempted`
    (AADP -03 §6's fail-closed rule)."""
    decision_ref: DecisionRef | None = None
    """A reference to this decision, joinable and checkable against an export of
    `actions_audit` (`python -m onedoor.decision_ref check`). Present iff this
    deployment has configured `EngineConfig.issuer`; absent otherwise, never a
    guessed value."""
    bound_permit: str | None = None
    """The compact JWS, present iff the policy issued one for THIS decide call.
    Never present on a replayed answer to the same `request_id`: a bound permit
    is a short-lived, one-time credential, and reissuing one for an old call
    would be handing out a credential that already expired or was already
    presented, not reporting what was decided."""
    untrusted_matched: list[str] = Field(default_factory=list)
    """Which of `DecideBody.untrusted`'s own paths actually matched this
    action type's own `untrusted_params.deny`/`hold` -- empty when none did."""
    sequence_events_considered: int = 0
    """Same field as `PolicyDecision.sequence_events_considered` (onedoor
    0.11) -- how many of this session's own settled events the sequence check
    read. Present only on the decision the sequence check itself produced
    (its own deny, or the confirm it escalated to), the same as every other
    per-check field here -- zero on a decision this check did not itself
    decide or escalate."""
    sequence_rule_matched: str | None = None
    """Same field as `PolicyDecision.sequence_rule_matched` -- which rule
    matched, or `None`."""
    sequence_history_incomplete: bool = False
    """Same field as `PolicyDecision.sequence_history_incomplete` -- the
    matched (or evaluated) rule's own window reached further back than this
    session's retained history."""
    plan_ref: int | None = None
    """Same field as `PolicyDecision.plan_ref` (onedoor 0.11) -- the
    plan whose match satisfied this decision's own approval
    step. `None` when no plan decided this call."""
    plan_consumed_count_after: int | None = None
    """Same field as `PolicyDecision.plan_consumed_count_after` -- `None`
    unless `plan_ref` is set."""
    plan_consumed_amount_after: Decimal | None = None
    """Same field as `PolicyDecision.plan_consumed_amount_after` -- `None`
    unless `plan_ref` is set, or the matched action name declares no
    `amount_param`."""


class ReportBody(BaseModel):
    intent_audit_id: int
    outcome: Outcome
    """The four-value report vocabulary (ND-039). Already normative in `-00`; this
    is conformance catch-up, not a wire break. `success`/`failure`/`timeout` settle
    the budget reservation, `not_attempted` RELEASES it as an audited event -- so a
    PEP that correctly refuses to act no longer has its tenant charged for an action
    that never occurred."""
    payload: dict[str, Any] | None = None
    error: str | None = None
    no_effect: bool = False
    """AADP -03 §4.1. On a `failure` report, a positive assertion
    that the action is known to have had no effect: the reservation releases like
    `not_attempted`, except the rate-dimension budget stays charged -- an attempt
    was made, which is why this is a `failure` and not a `not_attempted`. Refused
    (400) on any outcome other than `failure`."""


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

    def __init__(
        self,
        db_path: str,
        policies: Path,
        *,
        notify_config: NotifyConfig | None = None,
        send_email: approval_notify.EmailSender | None = None,
        send_webhook: approval_notify.WebhookSender | None = None,
    ) -> None:
        db = Database(db_path)
        db.init()
        self.conn = db.connect(check_same_thread=False)
        policy_loader.load_file(self.conn, policies)
        self.config = EngineConfig(
            approval_ttl_seconds=int(os.environ.get("ONEDOOR_APPROVAL_TTL", "3600")),
            connector_timeout_seconds=30.0,
            tz=ZoneInfo(os.environ.get("ONEDOOR_TZ", "UTC")),
            # A deployment-declared id, never guessed: absent means no decide
            # response ever carries a decision_ref, not a fabricated hostname.
            issuer=os.environ.get("ONEDOOR_ISSUER") or None,
        )
        self.lock = threading.Lock()
        self.notifier: Notifier = build_notifier()
        self.key_secret = keys.load_secret(db_path)
        # Signed approval links (onedoor 0.11). None (absent, the
        # default) means the by-link routes refuse everything with 404, and
        # the propose path's own notify step never fires -- the feature is
        # off, unaffected, the same opt-in default every 0.11 feature has.
        self.notify_config = notify_config
        self.send_email = send_email
        self.send_webhook = send_webhook

    def principal(self, key: str) -> str:
        """How a key is recorded: a keyed fingerprint, never any part of the key."""
        return keys.fingerprint(key, self.key_secret)

    @property
    def pending(self) -> list[int]:
        """Every permit awaiting a report, read from the ledger (ND-010).

        This used to be `dict[int, PermittedIntent]` held in memory, and a restart
        between decide and report stranded every in-flight permit: the reservation
        stayed held, the deadline ran, and the reclaimer eventually voided budget for
        an action that may well have happened. The docstring at the top of this module
        promised `0.4` would fix that; this is the fix, and the promise was three
        releases old.

        A property rather than a cached list on purpose: any other process writing a
        result row makes this answer change, and a cache would be a second copy of a
        truth the ledger already holds.
        """
        return rebuild_module.pending(self.conn)


async def raw_params(request: Request) -> str | None:
    """The verbatim source text of `params` from the request body (E10).

    An async dependency, deliberately: the endpoint stays synchronous so FastAPI runs
    it in a threadpool and the engine's threading lock never blocks the event loop,
    while the dependency still gets to await the raw body. Returns None if the body
    is not a plain JSON object with a top-level `params` -- an approximate answer
    would be recorded as *verbatim*, which is worse than recording nothing.
    """
    body = await request.body()
    try:
        return extract_raw_member(body.decode("utf-8"), "params")
    except UnicodeDecodeError:
        return None


def _decide_reply(outcome: Any, state: EngineState) -> DecideReply:
    if isinstance(outcome, PermittedIntent):
        # Nothing is stashed: the `exec_intent` row IS the record of this permit, and
        # `/v1/report` rebuilds from it. Memory held it before, which is exactly what
        # a restart lost.
        return DecideReply(
            decision="permitted",
            reason="passed",
            effective_tier=int(outcome.effective_tier),
            request_id=outcome.request.request_id,
            intent_audit_id=outcome.intent_audit_id,
            undo_until=outcome.undo_until,
            present_bound=outcome.present_bound,
            decision_ref=outcome.decision_ref,
            bound_permit=outcome.bound_permit,
            plan_ref=outcome.plan_ref,
            plan_consumed_count_after=outcome.plan_consumed_count_after,
            plan_consumed_amount_after=outcome.plan_consumed_amount_after,
        )
    d = outcome.decision
    # A replayed answer to a request_id that was permitted reconstructs an
    # ActionResult (audit.result_for_request_id), not a fresh PermittedIntent --
    # its decision reads EXECUTED because that is what the exec_intent row has
    # said since the moment it was written (decision.py's intent recording).
    # Naming that same row under a DIFFERENT field than the live reply used
    # (audit_id here, intent_audit_id there) would be two names for one row
    # depending only on which call happened to answer it; set both so a caller
    # checking intent_audit_id sees the same value on a replay as on the
    # original call. bound_permit is deliberately NOT reissued here -- see
    # DecideReply.bound_permit's own docstring.
    replayed_intent_audit_id = outcome.audit_id if d.decision == Decision.EXECUTED else None
    return DecideReply(
        decision=d.decision.value,
        reason=d.reason_code.value,
        detail=d.detail,
        effective_tier=int(d.effective_tier),
        request_id=outcome.request_id,
        audit_id=outcome.audit_id,
        approval_id=outcome.approval_id,
        intent_audit_id=replayed_intent_audit_id,
        budget=d.budget,
        decision_ref=outcome.decision_ref,
        untrusted_matched=d.untrusted_matched if d.untrusted_matched is not None else [],
        sequence_events_considered=d.sequence_events_considered or 0,
        sequence_rule_matched=d.sequence_rule_matched,
        sequence_history_incomplete=bool(d.sequence_history_incomplete),
        plan_ref=d.plan_ref,
        plan_consumed_count_after=d.plan_consumed_count_after,
        plan_consumed_amount_after=d.plan_consumed_amount_after,
    )


def create_app(
    db_path: str | None = None,
    policies: str | None = None,
    *,
    notify_config: NotifyConfig | None = None,
    send_email: approval_notify.EmailSender | None = None,
    send_webhook: approval_notify.WebhookSender | None = None,
) -> FastAPI:
    _refuse_overlapping_roles()
    # Installed once per app, not per request -- uvicorn's own access
    # logger is a module-level singleton, and a second create_app() call in
    # the same process (as tests do) must not stack duplicate filters.
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _ByLinkTokenRedactingFilter) for f in access_logger.filters):
        access_logger.addFilter(_ByLinkTokenRedactingFilter())
    state = EngineState(
        db_path or os.environ.get("ONEDOOR_DB", "onedoor-service.db"),
        Path(policies or os.environ.get("ONEDOOR_POLICIES", "config/policies.yaml")),
        notify_config=notify_config,
        send_email=send_email,
        send_webhook=send_webhook,
    )
    app = FastAPI(title="onedoor decision service", version="0.3.0")
    app.state.engine = state

    @app.middleware("http")
    async def _link_leak_safety_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """The two by-link handlers' own
        `_set_link_page_headers(response)` call only reaches the client on
        the path where the handler returns normally -- every
        `HTTPException` it raises, and any unhandled exception, builds an
        entirely separate response that never carried it, and a path under
        this prefix no route even matches (a plain 404) never reached a
        handler to set anything at all. Applied here instead, to every
        response under the prefix regardless of how it was built,
        including an unhandled exception this process turns into its own
        plain 500 rather than letting Starlette's own debug/default page
        answer without the headers."""
        if not request.url.path.startswith("/v1/approvals/by-link/"):
            return await call_next(request)
        try:
            response = await call_next(request)
        except Exception:
            log.error("by-link request failed before a response was built")
            response = JSONResponse(status_code=500, content={"detail": "internal error"})
        _set_link_page_headers(response)
        return response

    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        with state.lock:
            killed = killswitch.is_engaged(state.conn)
        return {"status": "ok", "kill_switch": killed, "pending_intents": len(state.pending)}

    @app.post("/v1/decide", response_model=DecideReply)
    def decide(
        body: DecideBody,
        _key: str = Depends(require_decide),
        params_raw: str | None = Depends(raw_params),
    ) -> DecideReply:
        now = now_utc()
        request = ActionRequest(
            request_id=body.request_id or uuid4(),
            action_type=body.action_type,
            params=body.params,
            source=body.source,
            rationale=body.rationale or f"service decide {body.action_type}",
            params_raw=params_raw,
            approval_ref=body.approval_ref,
            presented_audience=body.presented_audience,
            untrusted=body.untrusted,
            session_id=body.session_id,
            plan_ref=body.plan_ref,
            created_at=now,
        )
        with span("onedoor.decide", body.action_type), state.lock:
            # Whether this exact request_id already has a prior
            # audit row -- decide_and_reserve's own idempotency guard (see
            # its docstring) reuses that prior result rather than
            # proposing again, but this route's own notify step below
            # does not otherwise know that, and would mint and send a
            # brand new link pair for an approval this presentation did
            # not actually create.
            was_replay = audit.result_for_request_id(state.conn, request.request_id) is not None
            outcome = decide_and_reserve(
                request,
                conn=state.conn,
                config=state.config,
                now=now,
                principal=state.principal(_key),
            )
        reply = _decide_reply(outcome, state)
        record_decision(body.action_type, reply.decision, reply.reason, reply.effective_tier)
        if (
            not was_replay
            and reply.decision == Decision.PROPOSED.value
            and reply.approval_id is not None
        ):
            state.notifier.proposed(
                reply.approval_id, body.action_type, body.params, body.rationale
            )
            policy = PolicyStore().get(state.conn, body.action_type)
            if policy.approval_notify is not None and state.notify_config is not None:
                notify_result = approval_notify.notify(
                    approval_id=reply.approval_id,
                    notify_policy=policy.approval_notify,
                    config=state.notify_config,
                    now=now,
                    ttl_seconds=state.config.approval_ttl_seconds,
                    request_digest=approvals.resume_digest(body.action_type, body.params),
                    send_email=state.send_email,
                    send_webhook=state.send_webhook,
                )
                # link_sent records what notify() actually did --
                # the design note's own receipt wording promises a link
                # "built and dispatched", not merely attempted. Left at
                # its default (0, NULL) for a failed issue or a failed
                # or never-configured send, rather than always writing 1.
                if notify_result is not None and notify_result.sent:
                    with state.lock:
                        state.conn.execute(
                            "UPDATE approvals SET link_sent=1, link_channel=? WHERE id=?",
                            (policy.approval_notify.channel, reply.approval_id),
                        )
        return reply

    @app.post("/v1/report", response_model=DecideReply)
    def report(body: ReportBody, _key: str = Depends(require_decide)) -> DecideReply:
        outcome = rebuild_module.rebuild(
            state.conn, body.intent_audit_id, issuer=getattr(state.config, "issuer", None)
        )
        if outcome.status is not rebuild_module.RebuildStatus.REBUILT:
            # Four outcomes, and the HTTP status distinguishes them: an absent intent
            # is the client asking about something that is not pending (404), while an
            # `unverifiable` or `failed` one is the STORE disagreeing with itself and
            # is nobody's client error (500). Collapsing them would report a damaged
            # ledger as a bad request and send an operator looking in the wrong place.
            code = 404 if outcome.status is rebuild_module.RebuildStatus.ABSENT else 500
            raise HTTPException(
                status_code=code, detail=f"{outcome.status.value}: {outcome.detail}"
            )
        intent = outcome.intent
        assert intent is not None
        if intent.decide_principal is None or not hmac.compare_digest(
            intent.decide_principal, state.principal(_key)
        ):
            # A report is accepted only from the decide key that received the
            # permit. A different decide key -- or a row with no recorded decide
            # key at all (NULL: it predates this column, or was written in-process
            # with no key to fingerprint) -- gets the exact refusal an unknown
            # handle gets: same status, same detail text, never a message that
            # confirms the intent exists but names the wrong caller. This fails
            # closed on an upgrade rather than trusting an unidentified row.
            raise HTTPException(
                status_code=404, detail=f"absent: no pending intent {body.intent_audit_id}"
            )
        with span("onedoor.report", intent.action_type), state.lock:
            try:
                result = report_result(
                    intent,
                    conn=state.conn,
                    outcome=body.outcome,
                    payload=body.payload,
                    error=body.error,
                    no_effect=body.no_effect,
                    now=now_utc(),
                )
            except ReportError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_decision(
            intent.action_type,
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

    def _recorded_reply(approval_id: int, exc: NeedsMoreApprovers) -> JSONResponse:
        """A recorded-but-insufficient two-person vote is its own result, not a
        refusal: `202`, not `409` -- `409` stays for an actual refusal (the
        proposer, the same identity twice, expired, not pending)."""
        return JSONResponse(
            status_code=202,
            content={
                "status": "recorded",
                "approval_id": approval_id,
                "recorded": exc.recorded,
                "required": exc.required,
            },
        )

    @app.post("/v1/approvals/{approval_id}/approve", response_model=DecideReply)
    def approve(approval_id: int, _key: str = Depends(require_admin)) -> Any:
        now = now_utc()
        with state.lock:
            try:
                original = approvals.cas_approve(
                    state.conn, approval_id, state.principal(_key), now, channel="key"
                )
            except NeedsMoreApprovers as exc:
                return _recorded_reply(approval_id, exc)
            except ApprovalError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            try:
                proposal_audit_id = approvals.proposed_audit_id(state.conn, approval_id)
                proposer_principal = approvals.proposed_decide_principal(state.conn, approval_id)
                resumed = original.model_copy(update={"request_id": uuid4(), "created_at": now})
                # The resumed decision consumes the approval whatever its verdict. Its
                # principal is the decide key that PROPOSED the action, not the admin
                # key that approved it here -- that key cannot report later (each key
                # holds exactly one role), and the decide key that proposed the action
                # is the one meant to report its outcome once approved.
                outcome = decide_and_reserve(
                    resumed,
                    conn=state.conn,
                    config=state.config,
                    now=now,
                    approved_override=True,
                    resumes_audit_id=proposal_audit_id,
                    consumes_approval=approval_id,
                    principal=proposer_principal,
                )
            except ApprovalError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _decide_reply(outcome, state)

    @app.post("/v1/approvals/{approval_id}/grant")
    def grant(approval_id: int, _key: str = Depends(require_admin)) -> Any:
        """Approve only: leaves the row `approved`, resumes nothing.

        For an integration with no persistent "approved but not yet executed"
        window of its own (the LangChain middleware) -- a human grants
        here, through an authenticated admin key `cas_approve` itself refuses
        from the proposer, and the holder of the proposal's own
        principal resumes it later, anywhere, through the approval-reference
        flow, which binds to that exact principal.
        """
        with state.lock:
            try:
                approvals.cas_approve(
                    state.conn, approval_id, state.principal(_key), now_utc(), channel="key"
                )
            except NeedsMoreApprovers as exc:
                return _recorded_reply(approval_id, exc)
            except ApprovalError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"status": "approved", "approval_id": approval_id}

    @app.post("/v1/approvals/{approval_id}/deny")
    def deny(approval_id: int, _key: str = Depends(require_admin)) -> dict[str, str]:
        with state.lock:
            try:
                approvals.deny(state.conn, approval_id, state.principal(_key), now_utc())
            except ApprovalError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"status": "denied"}

    @app.get("/v1/approvals/by-link/{token}")
    def approval_link_confirm(token: str) -> dict[str, Any]:
        """A confirmation page only -- never acts. Deliberately
        unauthenticated (the token itself is the credential): a mail
        scanner or link-preview generator fetching this GET by itself,
        before any person sees it, must never approve or deny anything,
        so this route never calls `resolve` (which consumes the nonce),
        only `verify` (which never touches the database).

        No referrer, no cache, no cross-origin load, on every response
        under this prefix, by middleware; the access log and
        any error path name the route with the
        token replaced by the literal text `<token>`, never the real
        value."""
        log.info("GET /v1/approvals/by-link/<token>")
        try:
            if state.notify_config is None:
                raise HTTPException(status_code=404, detail="not found")
            result = approval_link.verify(
                token, signing_keys=state.notify_config.approval_link_signing_keys, now=now_utc()
            )
            if result.status == LinkVerifyStatus.VALID:
                assert result.claims is not None
                if approval_link.is_consumed(state.conn, result.claims.nonce):
                    # "used" is the one distinct reason a GET
                    # states -- unlike the key/signature distinctions kept
                    # opaque, telling a human their OWN link was
                    # already used does not help anyone enumerate a
                    # different key or token.
                    return {"valid": False, "status": "consumed"}
                return {
                    "valid": True,
                    "action": result.claims.action,
                    "approval_id": result.claims.approval_id,
                }
            # The design note and migration 0045 already say a
            # failed link states no reason beyond that -- the same
            # anti-probing posture approval_ref/plan_ref already have.
            # The real status (which of unknown_key/bad_signature/
            # expired) is not returned; it is logged here, never in the
            # response, so it cannot be used to enumerate key ids.
            log.info("GET /v1/approvals/by-link/<token> invalid: %s", result.status.value)
            return {"valid": False}
        except HTTPException:
            raise
        except Exception:
            log.error("GET /v1/approvals/by-link/<token> failed")
            raise

    @app.post("/v1/approvals/by-link/{token}", response_model=None)
    def approval_link_act(token: str) -> dict[str, Any] | JSONResponse:
        """Acts -- approves or denies, whichever the token itself names.
        Deliberately unauthenticated; the signed, single-use token is the
        credential. The identity the link was sent to is the identity
        recorded as having approved or denied -- `cas_approve`/`deny`'s own
        self-approval and same-identity-twice refusals apply to it exactly
        as they do to any other approver identity.

        No referrer, no cache, no cross-origin load, on every response
        under this prefix, by middleware; the access log and
        any error path name the route with the
        token replaced by the literal text `<token>`, never the real
        value."""
        log.info("POST /v1/approvals/by-link/<token>")
        try:
            if state.notify_config is None:
                raise HTTPException(status_code=404, detail="not found")
            now = now_utc()
            with state.lock:
                result = approval_link.resolve(
                    state.conn,
                    token,
                    signing_keys=state.notify_config.approval_link_signing_keys,
                    now=now,
                )
                if result.status != LinkVerifyStatus.VALID:
                    # The same anti-probing posture as the GET route
                    # above -- the real status is logged, never answered.
                    log.info("POST /v1/approvals/by-link/<token> invalid: %s", result.status.value)
                    raise HTTPException(status_code=409, detail="link can't be used")
                claims = result.claims
                assert claims is not None
                if claims.issuer != state.notify_config.approval_link_issuer:
                    # A token issued by a different deployment (one
                    # replayed from a restored backup of a different
                    # deployment that happens to share a signing key, for
                    # instance) is refused regardless of its signature.
                    log.info("POST /v1/approvals/by-link/<token> invalid: issuer_mismatch")
                    raise HTTPException(status_code=409, detail="link can't be used")
                action_row = state.conn.execute(
                    "SELECT action_type, request_json FROM approvals WHERE id=?",
                    (claims.approval_id,),
                ).fetchone()
                policy = (
                    PolicyStore().get(state.conn, action_row["action_type"])
                    if action_row is not None
                    else None
                )
                expected_recipient = (
                    policy.approval_notify.recipient
                    if policy is not None and policy.approval_notify is not None
                    else None
                )
                if expected_recipient is not None and claims.recipient != expected_recipient:
                    # A token whose own claimed recipient no longer matches
                    # the policy's configured one (the key it was signed under
                    # leaked, or the policy's approval_notify.recipient changed
                    # since) is refused -- never acted on just because the
                    # signature itself still verifies. The reason
                    # (recipient mismatch, specifically) is logged, not
                    # answered, the same posture as every other reason a
                    # link can fail for.
                    log.info("POST /v1/approvals/by-link/<token> invalid: recipient_mismatch")
                    raise HTTPException(status_code=409, detail="link can't be used")
                if action_row is not None:
                    # A token whose own claimed request digest no
                    # longer matches the approval it names (a different
                    # approval id reused after a restore, for instance) is
                    # refused regardless of its signature or issuer.
                    current_request = approvals.loads_request(action_row["request_json"])
                    expected_digest = approvals.resume_digest(
                        current_request.action_type, current_request.params
                    )
                    if claims.request_digest != expected_digest:
                        log.info("POST /v1/approvals/by-link/<token> invalid: digest_mismatch")
                        raise HTTPException(status_code=409, detail="link can't be used")
                # The FIRST link vote sets link_used_at, not every
                # one -- set here, once, as soon as a presented link is
                # confirmed valid and about to be acted on, guarded by
                # "only if still NULL" so a second vote through the
                # approval's other token (e.g. a recorded-but-insufficient
                # approve vote, followed later by its separate deny token)
                # never overwrites the first timestamp.
                state.conn.execute(
                    "UPDATE approvals SET link_used_at=? WHERE id=? AND link_used_at IS NULL",
                    (to_iso(now), claims.approval_id),
                )
                try:
                    if claims.action == "approve":
                        try:
                            approvals.cas_approve(
                                state.conn,
                                claims.approval_id,
                                claims.recipient,
                                now,
                                channel="link",
                            )
                            outcome = "approved"
                        except NeedsMoreApprovers as exc:
                            # A recorded-but-insufficient vote
                            # answers 202, matching /grant's own answer
                            # for the exact same NeedsMoreApprovers case
                            # -- it used to answer 200 here, as though
                            # fully decided.
                            return _recorded_reply(claims.approval_id, exc)
                    else:
                        approvals.deny(state.conn, claims.approval_id, claims.recipient, now)
                        outcome = "denied"
                except ApprovalError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception:
            log.error("POST /v1/approvals/by-link/<token> failed")
            raise
        return {"status": outcome, "approval_id": claims.approval_id}

    @app.post("/v1/killswitch")
    def kill(body: KillBody, _key: str = Depends(require_admin)) -> dict[str, Any]:
        with state.lock:
            report = killswitch.set_engaged(state.conn, body.engaged, origin=body.origin)
        # The lift is where a policy change made behind a shut door becomes
        # visible. Surfaced, never blocking -- an operator lifting the switch is told
        # that the rules moved while it was held, and lifts anyway if that is the call.
        # `null` while engaging, because there is no lift to report on.
        return {
            "kill_switch": body.engaged,
            "policy_change_while_engaged": None if report is None else report.to_object(),
        }

    return app
