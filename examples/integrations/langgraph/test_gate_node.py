"""No model, no network: the graph has one node and runs on fixed state;
nothing here is an agent making choices."""

from __future__ import annotations

import tempfile

from gate_node import PayState, build_engine, make_pay_node
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command


def test_an_auto_tier_payment_executes_directly() -> None:
    conn, config = build_engine(tempfile.mktemp(suffix=".db"), require_approval=False)
    graph = StateGraph(PayState)
    graph.add_node("pay", make_pay_node(conn, config))
    graph.add_edge(START, "pay")
    graph.add_edge("pay", END)
    app = graph.compile()

    out = app.invoke({"payee": "acme", "amount_eur": 50.0, "result": ""})
    assert out["result"] == "paid 50.0 to acme"


def test_a_confirm_tier_payment_holds_the_graph_then_resumes_on_approval() -> None:
    conn, config = build_engine(tempfile.mktemp(suffix=".db"), require_approval=True)
    graph = StateGraph(PayState)
    graph.add_node("pay", make_pay_node(conn, config))
    graph.add_edge(START, "pay")
    graph.add_edge("pay", END)
    app = graph.compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    paused = app.invoke({"payee": "acme", "amount_eur": 120.0, "result": ""}, cfg)
    assert "__interrupt__" in paused
    intr = paused["__interrupt__"][0].value
    assert intr["payee"] == "acme"

    resumed = app.invoke(Command(resume="approved"), cfg)
    assert resumed["result"] == "paid 120.0 to acme (approved)"
