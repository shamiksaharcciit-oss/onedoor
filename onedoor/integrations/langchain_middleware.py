"""onedoor as LangChain agent middleware.

`wrap_tool_call` receives the model's proposed tool call *before* it runs and
may return its own `ToolMessage` instead of invoking the handler. That is
exactly the shape of a decision point: decide first, execute only if permitted,
report what happened.

    from langchain.agents import create_agent
    from onedoor.integrations.langchain_middleware import (
        OneDoorMiddleware, open_engine,
    )

    conn, config = open_engine("agent.db", "policies.yaml")
    agent = create_agent(
        model, tools,
        middleware=[OneDoorMiddleware(conn, config)],
    )

Compared with wrapping each tool by hand (`examples/langgraph_tools.py`), the
middleware governs every tool the agent has, including ones added later, and it
cannot be forgotten on one of them. The wrapper still has a job: it works with a
bare `ToolNode` in a hand-built graph, where there is no agent harness for
middleware to attach to.

Three outcomes, matching the engine:

  permit   the handler runs, the result is reported, the ToolMessage passes back
  deny     the handler never runs; the reason returns as the tool's output
  propose  a human decides -- as a message, or as a real graph interrupt

Async is native: `awrap_tool_call` runs the engine in a worker thread rather
than blocking the loop, because the engine call is synchronous and short.
"""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from onedoor.guardrail.approval_ref import ApprovalRefStatus
from onedoor.guardrail.decision import (
    PermittedIntent,
    decide_and_reserve,
    report_result,
)
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    CheckId,
    Decision,
    DecisionRef,
    Outcome,
    Source,
)
from onedoor.store.clock import now_utc

if TYPE_CHECKING:  # pragma: no cover - typing only
    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import ToolMessage


def open_engine(
    db_path: str,
    policies: str | None = None,
    *,
    approval_ttl_seconds: int = 3600,
    connector_timeout_seconds: float = 30.0,
    tz: str = "UTC",
) -> tuple[Any, EngineConfig]:
    """Open a connection an agent can actually use, and load policy into it.

    The reason this helper exists rather than a line of documentation: LangGraph
    executes the tools node on a worker thread, and a SQLite connection opened
    with the default ``check_same_thread=True`` raises
    ``sqlite3.ProgrammingError`` the moment it is touched there. The failure does
    not appear in a unit test that calls the middleware directly -- only in a
    real agent run, which is the worst place to discover it.
    """
    from zoneinfo import ZoneInfo

    from onedoor.guardrail import policy_loader
    from onedoor.store.db import Database

    database = Database(db_path)
    database.init()
    conn = database.connect(check_same_thread=False)
    if policies is not None:
        policy_loader.load_file(conn, policies)
    config = EngineConfig(
        approval_ttl_seconds=approval_ttl_seconds,
        connector_timeout_seconds=connector_timeout_seconds,
        tz=ZoneInfo(tz),
    )
    return conn, config


def _canonical_args(args: dict[str, Any]) -> dict[str, Any]:
    """Params that may ever be presented for action-equivalence (`approval_ref`)
    must carry `Decimal`, never `float` (E10) -- LangChain hands a numeric tool
    argument back as a Python `float`, whatever the tool's own type hint says.
    Rendered through `str()` first, never `Decimal(float)` directly, so the
    binary float's own imprecision never becomes part of the canonical form."""
    return {k: Decimal(str(v)) if isinstance(v, float) else v for k, v in args.items()}


def _import_middleware_base() -> type:
    try:
        from langchain.agents.middleware import AgentMiddleware
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            'OneDoorMiddleware needs LangChain v1 or later: pip install "onedoor[langchain]"'
        ) from exc
    return AgentMiddleware


_BASE = _import_middleware_base()


class OneDoorMiddleware(_BASE):  # type: ignore[misc,valid-type]
    """Resolve every tool call through the decision point before it executes.

    Args:
        conn: an open onedoor connection. One connection, guarded by a lock --
            for multi-process agents consult the HTTP decision service instead.
        config: the engine config (tiers, approval TTL, timezone).
        on_proposed: what a Tier-3 action does. ``"message"`` returns the
            approval notice as the tool's output, so the agent can carry on and
            tell the user. ``"interrupt"`` raises a LangGraph interrupt, which
            pauses the graph until a human resumes it; that requires a
            checkpointer.
        action_prefix: how a tool name becomes an action type. The default
            matches the tool wrapper, so one policy file governs both.
        agent_principal: this middleware instance's own identity, recorded as
            the proposer of everything it proposes. Never valid as an
            approver (the engine's own self-approval check refuses a match,
            defense in depth).
        allow_same_process_approval: this middleware holds a direct database
            connection (``conn`` above), so code in the agent's own process
            can write to the ``approvals`` table directly -- there is no
            process boundary between the agent and whoever would approve,
            whatever this middleware does on resume. ``"interrupt"`` mode
            refuses to resume anything unless this is explicitly ``True``,
            naming that lack of separation rather than silently trusting it.
            There is currently no alternative wiring (talking to the HTTP
            decision service with only a decide key) that would give a real
            boundary; until one exists, this flag is the honest acknowledgment
            that approving and proposing share one process.
    """

    def __init__(
        self,
        conn: Any,
        config: EngineConfig,
        *,
        on_proposed: Literal["message", "interrupt"] = "message",
        action_prefix: str = "tool.",
        source: Source = Source.LLM,
        agent_principal: str = "onedoor-langchain-agent",
        allow_same_process_approval: bool = False,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._config = config
        self._on_proposed = on_proposed
        self._prefix = action_prefix
        self._source = source
        self._agent_principal = agent_principal
        self._allow_same_process_approval = allow_same_process_approval
        self._lock = threading.Lock()
        self.last_decision_ref: DecisionRef | None = None
        """The reference to the most recent decision this middleware acted on --
        `None` before any call, or if no `EngineConfig.issuer` was configured.
        The same documented hook `onedoor.mcp.proxy.Proxy.last_decision_ref` is,
        for the same reason: a tool call's result is a plain string/content
        payload this middleware does not own the shape of, so the reference
        cannot be embedded in it without conflating two different things. Set
        from `_decide()`, so it covers both `wrap_tool_call` and
        `awrap_tool_call` (the latter calls `_decide` via a worker thread, not
        a separate implementation)."""
        self.last_bound_permit: str | None = None
        """The most recent decision's bound permit (compact JWS), iff the policy
        issued one. Same hook, same set site as `last_decision_ref` above."""

    # ---------------------------------------------------------------- helpers

    def _tool_message(self, request: ToolCallRequest, text: str) -> ToolMessage:
        from langchain_core.messages import ToolMessage

        return ToolMessage(
            content=text,
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
        )

    @staticmethod
    def _resume_key(request: ToolCallRequest) -> tuple[str | None, str | None]:
        """The resume key a re-executed node would present a second time: LangGraph's
        own `configurable.thread_id`, and the tool call this proposal answers.

        `None`/`None` outside a graph (`request.runtime` is `None`, per its own
        docstring) or when the running graph was never given a `thread_id` -- both
        behave exactly as a caller with no resume key always has.
        """
        runtime = request.runtime
        if runtime is None:
            return None, None
        config = getattr(runtime, "config", None) or {}
        thread_id = config.get("configurable", {}).get("thread_id")
        tool_call_id = request.tool_call.get("id")
        return thread_id, tool_call_id

    def _decide(self, request: ToolCallRequest, *, approval_ref: int | None = None) -> Any:
        name = request.tool_call["name"]
        args = _canonical_args(dict(request.tool_call.get("args") or {}))
        now = now_utc()
        action = ActionRequest(
            request_id=uuid4(),
            action_type=f"{self._prefix}{name}",
            params=args,
            source=self._source,
            rationale=f"langchain tool call {name}",
            created_at=now,
            approval_ref=approval_ref,
        )
        thread_id, tool_call_id = self._resume_key(request)
        with self._lock:
            outcome = decide_and_reserve(
                action,
                conn=self._conn,
                config=self._config,
                now=now,
                principal=self._agent_principal,
                thread_id=thread_id,
                tool_call_id=tool_call_id,
            )
        self.last_decision_ref = outcome.decision_ref
        self.last_bound_permit = (
            outcome.bound_permit if isinstance(outcome, PermittedIntent) else None
        )
        return outcome

    def _report(self, intent: PermittedIntent, ok: bool, payload: Any, error: str | None) -> None:
        with self._lock:
            report_result(
                intent,
                conn=self._conn,
                config=self._config,
                outcome=Outcome.SUCCESS if ok else Outcome.FAILURE,
                payload=payload,
                error=error,
                now=now_utc(),
            )

    @staticmethod
    def _parse_approval_ref(resume: object) -> int | None:
        """The resume value's ``approval_id`` field, strictly: present, a
        string, and that string holds nothing but decimal digits. Every other
        key in `resume` is ignored -- a former credential shape, a claimed
        decision, anything else -- and anything short of this exact shape
        parses as no reference at all, never a best-effort guess."""
        if not isinstance(resume, dict):
            return None
        raw = resume.get("approval_id")
        if not isinstance(raw, str) or not re.fullmatch(r"[0-9]+", raw):
            return None
        return int(raw)

    def _ref_status(self, audit_id: int | None) -> str | None:
        if audit_id is None:
            return None
        row = self._conn.execute(
            "SELECT approval_ref_status FROM actions_audit WHERE id=?", (audit_id,)
        ).fetchone()
        return str(row["approval_ref_status"]) if row is not None else None

    _REF_REFUSALS = {
        ApprovalRefStatus.EXPIRED.value: "the approval has expired; a new approval is needed.",
        ApprovalRefStatus.CONSUMED.value: "the approval has already been used; a new approval "
        "is needed.",
        ApprovalRefStatus.ACTION_MISMATCH.value: "the approval does not match this exact "
        "action; a new approval is needed.",
        ApprovalRefStatus.PRINCIPAL_MISMATCH.value: "the approval was granted for a different "
        "agent.",
    }

    def _resume_refusal(self, request: ToolCallRequest, name: str, outcome: Any) -> Any:
        """Named from the engine's own evidence (`approval_ref_status`), never a
        single generic "not resumed" -- but the kill switch wins the naming
        first: a stop burns the approval in the same call that denies it, so
        the refusal says that happened rather than "already used", which would
        be true but would hide why."""
        if outcome.decision.reason_code == CheckId.KILL_SWITCH:
            message = "the approval was used up by a stop; a new approval is needed."
        else:
            status = self._ref_status(outcome.audit_id)
            message = self._REF_REFUSALS.get(status or "", "the approval is not approved.")
        return self._tool_message(request, f"onedoor: '{name}' was not resumed: {message}")

    def _run(self, intent: PermittedIntent, request: ToolCallRequest, handler: Any) -> Any:
        try:
            result = handler(request)
        except Exception as exc:
            self._report(intent, ok=False, payload=None, error=str(exc)[:200])
            raise
        self._report(intent, ok=True, payload={"result": str(result)[:500]}, error=None)
        return result

    def _denied_message(self, request: ToolCallRequest, outcome: Any) -> Any:
        d = outcome.decision
        name = request.tool_call["name"]
        if self._on_proposed == "interrupt" and d.reason_code == CheckId.KILL_SWITCH:
            # Resuming re-runs this whole method from the top (a known,
            # documented limitation), so THIS proposal attempt -- the one the
            # kill switch just denied -- is a fresh one, not the one a human
            # may have already granted through `/grant`. The kill-switch-first
            # check denies it before `approval_ref` is ever presented, so
            # unlike the MCP path (which presents the ref in the same call
            # that denies it, and so DOES consume it), nothing here ever
            # touches a prior grant -- it is left `approved`, not used up.
            return self._tool_message(
                request,
                f"onedoor: '{name}' denied: the kill switch is on; nothing ran. If an "
                f"approval was already granted for this action, it was not used, and "
                f"can still be resumed once the switch is lifted.",
            )
        detail = f": {d.detail}" if d.detail else ""
        return self._tool_message(
            request,
            f"onedoor: '{name}' {d.decision.value} ({d.reason_code.value}{detail})",
        )

    def _proposed(self, request: ToolCallRequest, outcome: Any, handler: Any) -> Any:
        name = request.tool_call["name"]
        if self._on_proposed == "interrupt":
            from langgraph.types import interrupt

            resume = interrupt(
                {
                    "approval_id": outcome.approval_id,
                    "action_type": f"{self._prefix}{name}",
                    "args": dict(request.tool_call.get("args") or {}),
                    "reason": outcome.decision.reason_code.value,
                }
            )
            if not self._allow_same_process_approval:
                return self._tool_message(
                    request,
                    f"onedoor: '{name}' was not resumed: this middleware holds a direct "
                    f"database connection, with no process boundary between the agent and "
                    f"whoever would approve. Pass allow_same_process_approval=True only if "
                    f"that is accepted, or wire the agent through the HTTP decision "
                    f"service instead.",
                )
            ref = self._parse_approval_ref(resume)
            if ref is None:
                return self._tool_message(
                    request,
                    f"onedoor: '{name}' was not resumed: no approval reference was given.",
                )
            # Resuming re-runs this whole function from the top (a LangGraph
            # property, not a onedoor one): `outcome.approval_id` above names a
            # fresh, never-granted proposal this very call just created, not the
            # one a human approved earlier. The reference comes only from `ref`
            # -- read from the resume value, never from this call's own outcome.
            resumed_outcome = self._decide(request, approval_ref=ref)
            if isinstance(resumed_outcome, PermittedIntent):
                return self._run(resumed_outcome, request, handler)
            return self._resume_refusal(request, name, resumed_outcome)
        return self._tool_message(
            request,
            f"onedoor: '{name}' requires human approval "
            f"(reason: {outcome.decision.reason_code.value}, "
            f"approval_id={outcome.approval_id}).",
        )

    # ------------------------------------------------------------------ hooks

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """Resuming a Tier-3 proposal in ``"interrupt"`` mode:

            agent.invoke(
                Command(resume={"decision": "approved", "approval_id": "<id>"}),
                cfg,
            )

        ``approval_id`` is the id from the interrupt payload this same call
        received -- a bare reference, never a credential. This middleware
        never calls the engine's ``cas_approve``: a human (or whatever process
        actually faces one) grants the proposal through the service's
        ``POST /v1/approvals/{id}/grant``, over HTTP, with an admin key the
        agent's process never holds. The resume value only tells this
        middleware *which* granted row to present -- every other key in it
        (a former credential, a claimed decision) is ignored.

        Presenting the reference grants nothing by itself. ``decide_and_
        reserve`` resolves it (``onedoor.guardrail.approval_ref``) against the
        SAME checks every presented reference gets: the row must already be
        ``approved`` (settable only through ``/grant``), the action and
        arguments must match what was actually proposed, the principal
        presenting it must match the principal that proposed it, and it is
        consumed once, atomically. An agent process free to put any string it
        likes into the resume value gains nothing from that freedom -- it
        cannot manufacture an ``approved`` row, and a reference to someone
        else's approval, or to one for different arguments, refuses exactly
        like a reference to nothing. A missing or malformed ``approval_id``,
        or a plain decline, all give a named refusal and run nothing.

        One LangGraph property this depends on: resuming re-executes this
        whole method from the top, including the ``self._decide(request)``
        call above ``_proposed`` -- so a resume decides twice: once here, with
        no reference, and once more inside ``_proposed`` once the resume
        value is read, with it. The first of those two finds the SAME row the
        human already acted on, whether it is still ``pending`` or has been
        ``approved`` in the meantime (``find_by_resume_key``, keyed on
        ``thread_id``/``tool_call_id``) -- it does not propose a second,
        never-granted one. The resumed branch still never reads that first
        call's own id, by design; it reads the id out of the resume value
        instead, which is the one the human actually saw and granted.

        Same-process mode: this middleware holds a direct database
        connection, so there is no process boundary between the agent
        proposing and whatever calls ``/grant`` if they share this same
        connection and process -- resuming refuses by default
        (``allow_same_process_approval``, see the class docstring) unless a
        deployer explicitly accepts that.
        """
        outcome = self._decide(request)
        if isinstance(outcome, PermittedIntent):
            return self._run(outcome, request, handler)
        if outcome.decision.decision == Decision.PROPOSED:
            return self._proposed(request, outcome, handler)
        return self._denied_message(request, outcome)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """Same decision, off the event loop.

        The engine call is synchronous and sub-millisecond, but it touches
        SQLite, so it belongs in a worker thread rather than on the loop. The
        tool itself is awaited normally.
        """
        outcome = await asyncio.to_thread(self._decide, request)
        if isinstance(outcome, PermittedIntent):
            try:
                result = await handler(request)
            except Exception as exc:
                await asyncio.to_thread(self._report, outcome, False, None, str(exc)[:200])
                raise
            await asyncio.to_thread(
                self._report, outcome, True, {"result": str(result)[:500]}, None
            )
            return result
        if outcome.decision.decision == Decision.PROPOSED:
            return await asyncio.to_thread(self._proposed, request, outcome, handler)
        return self._denied_message(request, outcome)


__all__ = ["OneDoorMiddleware", "open_engine"]
