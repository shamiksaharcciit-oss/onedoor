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
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import (
    PermittedIntent,
    decide_and_reserve,
    report_result,
)
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Decision, Source
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
    """

    def __init__(
        self,
        conn: Any,
        config: EngineConfig,
        *,
        on_proposed: Literal["message", "interrupt"] = "message",
        action_prefix: str = "tool.",
        source: Source = Source.LLM,
    ) -> None:
        super().__init__()
        self._conn = conn
        self._config = config
        self._on_proposed = on_proposed
        self._prefix = action_prefix
        self._source = source
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- helpers

    def _tool_message(self, request: ToolCallRequest, text: str) -> ToolMessage:
        from langchain_core.messages import ToolMessage

        return ToolMessage(
            content=text,
            name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"],
        )

    def _decide(self, request: ToolCallRequest) -> Any:
        name = request.tool_call["name"]
        args = dict(request.tool_call.get("args") or {})
        now = now_utc()
        action = ActionRequest(
            request_id=uuid4(),
            action_type=f"{self._prefix}{name}",
            params=args,
            source=self._source,
            rationale=f"langchain tool call {name}",
            created_at=now,
        )
        with self._lock:
            return decide_and_reserve(action, conn=self._conn, config=self._config, now=now)

    def _report(self, intent: PermittedIntent, ok: bool, payload: Any, error: str | None) -> None:
        with self._lock:
            report_result(
                intent,
                conn=self._conn,
                config=self._config,
                ok=ok,
                payload=payload,
                error=error,
                now=now_utc(),
            )

    def _execute_approved(self, approval_id: int, request: ToolCallRequest, handler: Any) -> Any:
        """Run an action a human just approved, re-checked rather than trusted.

        The approval is consumed atomically and the request is evaluated again:
        an approval is permission to ask a second time, not a permit. The kill
        switch, the caps and the bounds all still apply.
        """
        now = now_utc()
        with self._lock:
            original = approvals.cas_approve(self._conn, approval_id, "langchain-human", now)
            resumed = original.model_copy(update={"request_id": uuid4(), "created_at": now})
            outcome = decide_and_reserve(
                resumed, conn=self._conn, config=self._config, now=now, approved_override=True
            )
            if isinstance(outcome, PermittedIntent):
                approvals.mark_executed(self._conn, approval_id, outcome.intent_audit_id)
        if not isinstance(outcome, PermittedIntent):
            return self._tool_message(
                request,
                f"onedoor: approved action still blocked ({outcome.decision.reason_code.value})",
            )
        return self._run(outcome, request, handler)

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
            if resume == "approved":
                return self._execute_approved(outcome.approval_id, request, handler)
            return self._tool_message(request, f"onedoor: '{name}' was not approved ({resume}).")
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
