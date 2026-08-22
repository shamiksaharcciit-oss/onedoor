"""onedoor inside LangGraph — governed tools and a governed human-in-the-loop.

Three things, each demonstrated by the self-test at the bottom:

1. ``governed(...)`` wraps any LangChain tool so every invocation goes through
   the decision pipeline: permitted -> execute + report; denied/dry-run -> the
   reason string returns as the tool's output (the agent reads it and adapts);
   proposed -> parked with an approval id.
2. The wrapped tools drop into LangGraph's ``ToolNode`` unchanged — the graph
   doesn't know the door exists.
3. Tier 3 meets LangGraph's native ``interrupt()``: a proposed action pauses
   the graph, a human approves through onedoor, and ``Command(resume=...)``
   releases exactly that action. The framework provides pause/resume; the
   engine provides the policy about *what* pauses; bounds guarantee the human
   only ever sees sane requests; the audit log records the whole arc.

Example-grade simplifications, stated honestly: the engine call is synchronous
(wrap in ``asyncio.to_thread`` for async graphs); one shared connection behind
the module lock (multi-process graphs should consult the HTTP decision
service instead — docs/integration-service.md).

Self-test (no LLM, no API keys):  python -m examples.langgraph_tools
"""

from __future__ import annotations

import functools
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, StructuredTool, tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from onedoor.guardrail import approvals, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Decision, Outcome, Source
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

# ----------------------------- engine setup ----------------------------------

_LOCK = threading.Lock()


def make_engine(db_path: str, policies: Path) -> tuple[Any, EngineConfig]:
    db = Database(db_path)
    db.init()
    conn = db.connect(check_same_thread=False)  # ToolNode may run us on a worker thread
    policy_loader.load_file(conn, policies)
    config = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=30.0, tz=ZoneInfo("UTC")
    )
    return conn, config


# ----------------------------- the wrapper ------------------------------------


def governed(
    lc_tool: BaseTool, conn: Any, config: EngineConfig, *, on_proposed: str = "message"
) -> BaseTool:
    """Wrap a LangChain tool so every call goes through the door.

    ``on_proposed="message"`` returns the approval notice as the tool output;
    ``on_proposed="interrupt"`` raises a LangGraph interrupt carrying the
    approval id (use inside a checkpointed graph).
    """
    inner: Callable[..., Any] = lc_tool.func  # type: ignore[attr-defined]
    action_type = f"tool.{lc_tool.name}"

    @functools.wraps(inner)  # real signature: LangGraph's arg-binding inspects it
    def run(**kwargs: Any) -> Any:
        now = now_utc()
        request = ActionRequest(
            request_id=uuid4(),
            action_type=action_type,
            params=kwargs,
            source=Source.LLM,
            rationale=f"langgraph tool call {lc_tool.name}",
            created_at=now,
        )
        with _LOCK:
            outcome = decide_and_reserve(request, conn=conn, config=config, now=now)
        if isinstance(outcome, PermittedIntent):
            return _enforce(outcome, inner, kwargs, conn)
        d = outcome.decision
        if d.decision == Decision.PROPOSED and on_proposed == "interrupt":
            resume = interrupt(
                {
                    "approval_id": outcome.approval_id,
                    "action_type": action_type,
                    "params": kwargs,
                    "reason": d.reason_code.value,
                }
            )
            if resume == "approved":
                return _execute_approved(outcome.approval_id, inner, conn, config)
            return f"onedoor: '{lc_tool.name}' was not approved ({resume})."
        if d.decision == Decision.PROPOSED:
            return (
                f"onedoor: '{lc_tool.name}' requires human approval "
                f"(reason: {d.reason_code.value}, approval_id={outcome.approval_id})."
            )
        return (
            f"onedoor: '{lc_tool.name}' {d.decision.value} "
            f"({d.reason_code.value}{': ' + d.detail if d.detail else ''})"
        )

    # Preserve the original schema so agents and ToolNode see identical args.
    return StructuredTool.from_function(
        func=run,
        name=lc_tool.name,
        description=lc_tool.description,
        args_schema=lc_tool.args_schema,
    )


def _enforce(intent: PermittedIntent, fn: Callable[..., Any], kwargs: dict, conn: Any) -> Any:
    try:
        result = fn(**kwargs)
    except Exception as exc:
        with _LOCK:
            report_result(
                intent,
                conn=conn,
                outcome=Outcome.FAILURE,
                payload=None,
                error=str(exc)[:200],
                now=now_utc(),
            )
        raise
    with _LOCK:
        report_result(
            intent,
            conn=conn,
            outcome=Outcome.SUCCESS,
            payload={"result": str(result)[:500]},
            error=None,
            now=now_utc(),
        )
    return result


def _execute_approved(
    approval_id: int, fn: Callable[..., Any], conn: Any, config: EngineConfig
) -> Any:
    now = now_utc()
    with _LOCK:
        original = approvals.cas_approve(conn, approval_id, "langgraph-human", now)
        resumed = original.model_copy(update={"request_id": uuid4(), "created_at": now})
        outcome = decide_and_reserve(
            resumed, conn=conn, config=config, now=now, approved_override=True
        )
        if isinstance(outcome, PermittedIntent):
            approvals.mark_executed(conn, approval_id, outcome.intent_audit_id)
    if not isinstance(outcome, PermittedIntent):
        return f"onedoor: approved action blocked ({outcome.decision.reason_code.value})"
    return _enforce(outcome, fn, dict(resumed.params), conn)


# ----------------------------- demo tools -------------------------------------


@tool
def get_weather(city: str) -> str:
    """Current weather for a city (canned)."""
    return f"Weather in {city}: 19°C, light rain (of course)."


@tool
def set_thermostat(temperature: float) -> str:
    """Set the thermostat target temperature in °C."""
    return f"Thermostat set to {temperature:.1f}°C."


@tool
def send_payment(payee: str, amount_eur: float) -> str:
    """Send a payment to a payee (simulated)."""
    return f"Sent €{amount_eur:.2f} to {payee} (simulated)."


# ----------------------------- self-test --------------------------------------


def _selftest() -> None:
    policies = Path(__file__).parent / "langgraph_policies.yaml"

    # --- 1. wrapped tools, called directly -------------------------------------
    conn, config = make_engine(tempfile.mktemp(suffix=".db"), policies)
    weather = governed(get_weather, conn, config)
    thermo = governed(set_thermostat, conn, config)
    pay = governed(send_payment, conn, config)

    print("1) wrapped tools:")
    print("   ", weather.invoke({"city": "Utrecht"}))
    print("   ", thermo.invoke({"temperature": 21}))
    print("   ", thermo.invoke({"temperature": 30}))
    print("   ", pay.invoke({"payee": "webshop", "amount_eur": 49.99}))

    # --- 2. inside a graph's ToolNode, driven by a fabricated agent message ----
    print("2) inside a LangGraph ToolNode (no LLM needed):")
    g2 = StateGraph(MessagesState)
    g2.add_node("tools", ToolNode([weather, thermo, pay]))
    g2.add_edge(START, "tools")
    g2.add_edge("tools", END)
    app2 = g2.compile()
    msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_weather", "args": {"city": "Veldhoven"}, "id": "c1"},
            {"name": "set_thermostat", "args": {"temperature": 19}, "id": "c2"},
        ],
    )
    out = app2.invoke({"messages": [msg]})
    for m in out["messages"][1:]:
        print("   ", m.content)

    # --- 3. Tier 3 meets interrupt(): the governed human-in-the-loop ----------
    print("3) governed human-in-the-loop (interrupt -> approve -> resume):")
    conn3, config3 = make_engine(tempfile.mktemp(suffix=".db"), policies)
    pay3 = governed(send_payment, conn3, config3, on_proposed="interrupt")

    class S(TypedDict):
        result: str

    def pay_node(state: S) -> S:
        return {"result": pay3.invoke({"payee": "acme", "amount_eur": 120.0})}

    g = StateGraph(S)
    g.add_node("pay", pay_node)
    g.add_edge(START, "pay")
    g.add_edge("pay", END)
    app = g.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "demo-thread"}}

    paused = app.invoke({"result": ""}, cfg)
    intr = paused["__interrupt__"][0].value
    print(f"    graph paused: approval_id={intr['approval_id']} for {intr['action_type']}")
    resumed = app.invoke(Command(resume="approved"), cfg)
    print(f"    human approved -> {resumed['result']}")


if __name__ == "__main__":
    _selftest()
