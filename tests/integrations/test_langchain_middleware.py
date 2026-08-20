"""The middleware must reach the same verdicts as the tool wrapper.

These run a real `create_agent` loop against a scripted fake model, so the
assertions are about what LangChain actually does with what the middleware
returns -- not about what the middleware would like to happen.
"""

from __future__ import annotations

from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("langchain.agents")

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import (
    GenericFakeChatModel,
)
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    Bounds,
    Caps,
    NumericBound,
    Policy,
    Tier,
)
from onedoor.integrations.langchain_middleware import OneDoorMiddleware
from onedoor.store.db import Connection, Database

PAID: list[float] = []


@pytest.fixture
def agent_conn(tmp_path: object) -> Connection:
    """A connection the agent's worker threads can use.

    LangGraph runs the tools node off the calling thread, so the default
    check_same_thread=True connection the rest of the suite uses would raise.
    """
    database = Database(str(tmp_path / "agent.db"))  # type: ignore[operator]
    database.init()
    return database.connect(check_same_thread=False)


@tool
def pay_invoice(invoice_id: str, amount_eur: float) -> str:
    """Pay a supplier invoice."""
    PAID.append(amount_eur)
    return f"paid {amount_eur} for {invoice_id}"


@tool
def send_wire(beneficiary: str, amount_eur: float) -> str:
    """Send an irreversible wire."""
    PAID.append(amount_eur)
    return f"wired {amount_eur} to {beneficiary}"


def _config() -> EngineConfig:
    return EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC")
    )


def _seed(conn: Connection) -> None:
    policy_loader.upsert(conn, Policy(
        action_type="tool.refund", tier=Tier.AUTO, dry_run=False,
        compensating_command="tool.refund", bounds=Bounds(strict_params=False)))
    policy_loader.upsert(conn, Policy(
        action_type="tool.pay_invoice", tier=Tier.AUTO_CAPPED, dry_run=False,
        compensating_command="tool.refund", cost_param="amount_eur",
        caps=Caps(eur_day=Decimal("250.00")),
        bounds=Bounds(numeric={"amount_eur": NumericBound(min=0.01, max=100)},
                      required=["invoice_id", "amount_eur"], strict_params=True)))
    policy_loader.upsert(conn, Policy(
        action_type="tool.send_wire", tier=Tier.CONFIRM,
        bounds=Bounds(numeric={"amount_eur": NumericBound(min=0.01, max=100000)},
                      required=["beneficiary", "amount_eur"], strict_params=True)))


class _ScriptedModel(GenericFakeChatModel):
    """A fake chat model that accepts `bind_tools`.

    `create_agent` binds tools to the model; the stock fake raises
    NotImplementedError. Nothing here needs real tool selection -- the turns are
    scripted -- so binding is a no-op that returns the model unchanged.
    """

    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self


def _model(*turns: AIMessage) -> _ScriptedModel:
    return _ScriptedModel(messages=iter(turns))


def _call(name: str, args: dict, cid: str) -> dict:
    return {"name": name, "args": args, "id": cid, "type": "tool_call"}


@pytest.fixture(autouse=True)
def _clear() -> None:
    PAID.clear()


def test_permitted_call_executes_and_is_reported(agent_conn: Connection) -> None:
    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(content="", tool_calls=[
                _call("pay_invoice", {"invoice_id": "A1", "amount_eur": 90.0}, "c1")]),
            AIMessage(content="done"),
        ),
        tools=[pay_invoice],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    out = agent.invoke({"messages": [("user", "clear A1")]})
    assert PAID == [90.0]
    rows = agent_conn.execute(
        "SELECT kind FROM actions_audit ORDER BY id"
    ).fetchall()
    kinds = [r[0] for r in rows]
    assert "exec_intent" in kinds and "exec_result" in kinds
    assert out["messages"]


def test_cumulative_cap_denies_the_call_that_would_cross_it(agent_conn: Connection) -> None:
    """Three compliant payments, a 250 cap: the third must not execute."""
    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(content="", tool_calls=[
                _call("pay_invoice", {"invoice_id": "A1", "amount_eur": 90.0}, "c1"),
                _call("pay_invoice", {"invoice_id": "A2", "amount_eur": 90.0}, "c2"),
                _call("pay_invoice", {"invoice_id": "A3", "amount_eur": 90.0}, "c3")]),
            AIMessage(content="done"),
        ),
        tools=[pay_invoice],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    result = agent.invoke({"messages": [("user", "clear them")]})
    assert sum(PAID) == 180.0, "270 would breach the 250 cap"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("cap_eur_day" in t for t in texts), "the reason must reach the agent"


def test_denial_is_a_tool_message_not_an_exception(agent_conn: Connection) -> None:
    """A refusal the agent can read and adapt to, rather than a crash."""
    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(content="", tool_calls=[
                _call("pay_invoice", {"invoice_id": "A1", "amount_eur": 500.0}, "c1")]),
            AIMessage(content="ok, that is over the limit"),
        ),
        tools=[pay_invoice],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    result = agent.invoke({"messages": [("user", "pay A1")]})
    assert PAID == []
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("bounds" in t for t in texts)


def test_tier3_proposes_as_a_message_by_default(agent_conn: Connection) -> None:
    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(content="", tool_calls=[
                _call("send_wire", {"beneficiary": "acme", "amount_eur": 2400.0}, "c1")]),
            AIMessage(content="waiting for approval"),
        ),
        tools=[send_wire],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    result = agent.invoke({"messages": [("user", "wire acme")]})
    assert PAID == [], "an irreversible action must not run on the agent's authority"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("requires human approval" in t for t in texts)


def test_tier3_interrupt_pauses_the_graph_and_resume_executes(agent_conn: Connection) -> None:
    """The open question: does a graph interrupt work from inside wrap_tool_call?"""
    from langgraph.types import Command

    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(content="", tool_calls=[
                _call("send_wire", {"beneficiary": "acme", "amount_eur": 2400.0}, "c1")]),
            AIMessage(content="sent"),
        ),
        tools=[send_wire],
        middleware=[OneDoorMiddleware(agent_conn, _config(), on_proposed="interrupt")],
        checkpointer=MemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "t1"}}

    paused = agent.invoke({"messages": [("user", "wire acme")]}, cfg)
    assert "__interrupt__" in paused, "the graph must pause, not proceed"
    payload = paused["__interrupt__"][0].value
    assert payload["action_type"] == "tool.send_wire"
    assert payload["reason"] == "tier_confirm"
    assert PAID == [], "nothing runs while a human is deciding"

    agent.invoke(Command(resume="approved"), cfg)
    assert PAID == [2400.0], "approval releases exactly that action"


def test_interrupt_declined_does_not_execute(agent_conn: Connection) -> None:
    from langgraph.types import Command

    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(content="", tool_calls=[
                _call("send_wire", {"beneficiary": "acme", "amount_eur": 2400.0}, "c1")]),
            AIMessage(content="declined"),
        ),
        tools=[send_wire],
        middleware=[OneDoorMiddleware(agent_conn, _config(), on_proposed="interrupt")],
        checkpointer=MemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "t2"}}
    agent.invoke({"messages": [("user", "wire acme")]}, cfg)
    agent.invoke(Command(resume="declined"), cfg)
    assert PAID == []


@pytest.mark.asyncio
async def test_async_path_reaches_the_same_verdict(agent_conn: Connection) -> None:
    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(content="", tool_calls=[
                _call("pay_invoice", {"invoice_id": "A1", "amount_eur": 500.0}, "c1")]),
            AIMessage(content="over the limit"),
        ),
        tools=[pay_invoice],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    result = await agent.ainvoke({"messages": [("user", "pay A1")]})
    assert PAID == []
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("bounds" in t for t in texts)
