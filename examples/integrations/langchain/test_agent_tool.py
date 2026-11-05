"""No model, no network: LangChain's own GenericFakeChatModel scripts every
turn, so the agent loop is real but nothing in it talks to a real model."""

from __future__ import annotations

import tempfile

from agent_tool import PAID, build_middleware, pay_invoice
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class _ScriptedModel(GenericFakeChatModel):
    """create_agent binds tools to the model; the stock fake raises
    NotImplementedError. Nothing here needs real tool selection -- the turns
    are scripted -- so binding is a no-op that returns the model unchanged."""

    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self


def _call(name: str, args: dict, cid: str) -> dict:
    return {"name": name, "args": args, "id": cid, "type": "tool_call"}


def test_a_permitted_call_executes_and_is_reported() -> None:
    PAID.clear()
    middleware = build_middleware(tempfile.mktemp(suffix=".db"))
    model = _ScriptedModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        _call("pay_invoice", {"invoice_id": "A1", "amount_eur": 90.0}, "c1")
                    ],
                ),
                AIMessage(content="done"),
            ]
        )
    )
    agent = create_agent(model=model, tools=[pay_invoice], middleware=[middleware])
    out = agent.invoke({"messages": [("user", "pay A1")]})
    assert PAID == [90.0]
    assert out["messages"]
