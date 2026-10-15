"""The middleware must reach the same verdicts as the tool wrapper.

These run a real `create_agent` loop against a scripted fake model, so the
assertions are about what LangChain actually does with what the middleware
returns -- not about what the middleware would like to happen.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4
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

from onedoor.guardrail import approvals, killswitch, policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    NumericBound,
    Policy,
    Source,
    Tier,
)
from onedoor.integrations.langchain_middleware import OneDoorMiddleware, _canonical_args
from onedoor.store.clock import now_utc
from onedoor.store.db import Connection, Database, tx

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
    policy_loader.upsert(
        conn,
        Policy(
            action_type="tool.refund",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="tool.refund",
            bounds=Bounds(strict_params=False),
        ),
    )
    policy_loader.upsert(
        conn,
        Policy(
            action_type="tool.pay_invoice",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="tool.refund",
            cost_param="amount_eur",
            caps=Caps(eur_day=Decimal("250.00")),
            bounds=Bounds(
                numeric={"amount_eur": NumericBound(min=0.01, max=100)},
                required=["invoice_id", "amount_eur"],
                strict_params=True,
            ),
        ),
    )
    policy_loader.upsert(
        conn,
        Policy(
            action_type="tool.send_wire",
            tier=Tier.CONFIRM,
            dry_run=False,  # live: an approval releases it; a dry-run policy would rehearse
            bounds=Bounds(
                numeric={"amount_eur": NumericBound(min=0.01, max=100000)},
                required=["beneficiary", "amount_eur"],
                strict_params=True,
            ),
        ),
    )


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


def _granted(
    conn: Connection,
    action_type: str,
    params: dict,
    *,
    proposed_by: str | None,
    state: str = "approved",
) -> int:
    """A pre-existing approval, created and (unless `state="pending"`) granted
    directly -- the shape `/v1/approvals/{id}/grant` leaves behind, without
    going through the HTTP service none of these tests run."""
    with tx(conn):
        approval_id = approvals.create(
            conn,
            ActionRequest(
                request_id=uuid4(),
                action_type=action_type,
                params=_canonical_args(params),
                source=Source.LLM,
                rationale="test fixture",
                created_at=now_utc(),
            ),
            3600,
            now_utc(),
            proposed_by=proposed_by,
        )
        if state == "approved":
            approvals.cas_approve(conn, approval_id, "operator", now_utc())
    return approval_id


@pytest.fixture(autouse=True)
def _clear() -> None:
    PAID.clear()


def test_permitted_call_executes_and_is_reported(agent_conn: Connection) -> None:
    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(
                content="",
                tool_calls=[_call("pay_invoice", {"invoice_id": "A1", "amount_eur": 90.0}, "c1")],
            ),
            AIMessage(content="done"),
        ),
        tools=[pay_invoice],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    out = agent.invoke({"messages": [("user", "clear A1")]})
    assert PAID == [90.0]
    rows = agent_conn.execute("SELECT kind FROM actions_audit ORDER BY id").fetchall()
    kinds = [r[0] for r in rows]
    assert "exec_intent" in kinds and "exec_result" in kinds
    assert out["messages"]


def test_cumulative_cap_denies_the_call_that_would_cross_it(agent_conn: Connection) -> None:
    """Three compliant payments, a 250 cap: the third must not execute."""
    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(
                content="",
                tool_calls=[
                    _call("pay_invoice", {"invoice_id": "A1", "amount_eur": 90.0}, "c1"),
                    _call("pay_invoice", {"invoice_id": "A2", "amount_eur": 90.0}, "c2"),
                    _call("pay_invoice", {"invoice_id": "A3", "amount_eur": 90.0}, "c3"),
                ],
            ),
            AIMessage(content="done"),
        ),
        tools=[pay_invoice],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    result = agent.invoke({"messages": [("user", "clear them")]})
    assert sum(PAID) == 180.0, "270 would breach the 250 cap"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("budget_exhausted" in t for t in texts), "the reason must reach the agent"


def test_denial_is_a_tool_message_not_an_exception(agent_conn: Connection) -> None:
    """A refusal the agent can read and adapt to, rather than a crash."""
    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(
                content="",
                tool_calls=[_call("pay_invoice", {"invoice_id": "A1", "amount_eur": 500.0}, "c1")],
            ),
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
            AIMessage(
                content="",
                tool_calls=[
                    _call("send_wire", {"beneficiary": "acme", "amount_eur": 2400.0}, "c1")
                ],
            ),
            AIMessage(content="waiting for approval"),
        ),
        tools=[send_wire],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    result = agent.invoke({"messages": [("user", "wire acme")]})
    assert PAID == [], "an irreversible action must not run on the agent's authority"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("requires human approval" in t for t in texts)


def _wire_agent(agent_conn: Connection, **middleware_kwargs: object) -> object:
    return create_agent(
        model=_model(
            AIMessage(
                content="",
                tool_calls=[
                    _call("send_wire", {"beneficiary": "acme", "amount_eur": 2400.0}, "c1")
                ],
            ),
            AIMessage(content="done"),
        ),
        tools=[send_wire],
        middleware=[
            OneDoorMiddleware(agent_conn, _config(), on_proposed="interrupt", **middleware_kwargs)
        ],
        checkpointer=MemorySaver(),
    )


def test_tier3_interrupt_pauses_the_graph_and_resume_executes(agent_conn: Connection) -> None:
    """The open question: does a graph interrupt work from inside wrap_tool_call?"""
    from langgraph.types import Command

    _seed(agent_conn)
    agent = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg = {"configurable": {"thread_id": "t1"}}

    paused = agent.invoke({"messages": [("user", "wire acme")]}, cfg)
    assert "__interrupt__" in paused, "the graph must pause, not proceed"
    payload = paused["__interrupt__"][0].value
    assert payload["action_type"] == "tool.send_wire"
    assert payload["reason"] == "tier_confirm"
    assert PAID == [], "nothing runs while a human is deciding"

    with tx(agent_conn):
        approvals.cas_approve(agent_conn, payload["approval_id"], "operator", now_utc())
    agent.invoke(
        Command(resume={"decision": "approved", "approval_id": str(payload["approval_id"])}), cfg
    )
    assert PAID == [2400.0], "a granted reference releases exactly that action"


def test_resuming_an_ungranted_reference_is_refused(agent_conn: Connection) -> None:
    """The id shown in the interrupt payload, presented before anyone granted it
    (still `pending`) -- and a made-up id that names nothing -- both refuse."""
    from langgraph.types import Command

    _seed(agent_conn)
    for cid, ref in [("t-pending", None), ("t-unknown", "999999")]:
        agent = _wire_agent(agent_conn, allow_same_process_approval=True)
        cfg = {"configurable": {"thread_id": cid}}
        paused = agent.invoke({"messages": [("user", "wire acme")]}, cfg)
        pending_id = paused["__interrupt__"][0].value["approval_id"]
        reference = ref or str(pending_id)  # the real, still-pending id when ref is None

        result = agent.invoke(
            Command(resume={"decision": "approved", "approval_id": reference}), cfg
        )
        texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
        assert any("not resumed" in t for t in texts), texts
    assert PAID == [], "neither an unapproved nor an unknown reference may execute anything"


def test_resuming_a_different_principals_granted_approval_is_refused(
    agent_conn: Connection,
) -> None:
    """A real, granted approval for the identical action -- but proposed by
    someone else. The principal binding refuses it, and must not consume it:
    the approval is still good for its real proposer."""
    from langgraph.types import Command

    _seed(agent_conn)
    foreign = _granted(
        agent_conn,
        "tool.send_wire",
        {"beneficiary": "acme", "amount_eur": 2400.0},
        proposed_by="someone-elses-agent",
    )
    agent = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg = {"configurable": {"thread_id": "t-foreign-principal"}}
    agent.invoke({"messages": [("user", "wire acme")]}, cfg)

    result = agent.invoke(
        Command(resume={"decision": "approved", "approval_id": str(foreign)}), cfg
    )
    assert PAID == [], "an approval proposed by a different principal must not execute"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("different agent" in t for t in texts), texts
    state = agent_conn.execute("SELECT state FROM approvals WHERE id=?", (foreign,)).fetchone()[0]
    assert state == "approved", "a principal mismatch must not consume the approval"


def test_resuming_a_granted_approval_for_different_arguments_is_refused(
    agent_conn: Connection,
) -> None:
    """Granted, same proposer, same action_type -- a smaller amount. The human
    saw different params; this reference must not authorise the real call."""
    from langgraph.types import Command

    _seed(agent_conn)
    mismatched = _granted(
        agent_conn,
        "tool.send_wire",
        {"beneficiary": "acme", "amount_eur": 1.0},
        proposed_by="onedoor-langchain-agent",
    )
    agent = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg = {"configurable": {"thread_id": "t-arg-mismatch"}}
    agent.invoke({"messages": [("user", "wire acme")]}, cfg)

    result = agent.invoke(
        Command(resume={"decision": "approved", "approval_id": str(mismatched)}), cfg
    )
    assert PAID == [], "an approval for different arguments must not release this call"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("does not match" in t for t in texts), texts
    state = agent_conn.execute("SELECT state FROM approvals WHERE id=?", (mismatched,)).fetchone()[
        0
    ]
    assert state == "approved", "an action mismatch must not consume the approval"


def test_a_resume_values_extra_keys_are_ignored(agent_conn: Connection) -> None:
    """A former credential shape, a claimed decision name -- anything beside
    `approval_id` is noise. The result depends only on the id."""
    from langgraph.types import Command

    _seed(agent_conn)
    agent = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg = {"configurable": {"thread_id": "t-extra-keys"}}
    paused = agent.invoke({"messages": [("user", "wire acme")]}, cfg)
    aid = paused["__interrupt__"][0].value["approval_id"]
    with tx(agent_conn):
        approvals.cas_approve(agent_conn, aid, "operator", now_utc())

    agent.invoke(
        Command(
            resume={
                "decision": "approved",
                "approval_id": str(aid),
                "approver_key": "ops-key",
                "approver": "head-of-finance",
            }
        ),
        cfg,
    )
    assert PAID == [2400.0], "extra keys must not change the outcome of a valid reference"


@pytest.mark.parametrize(
    "resume_value",
    [
        "declined",
        {"decision": "approved"},
        {"decision": "approved", "approval_id": 123},
        {"decision": "approved", "approval_id": "not-a-number"},
        {"decision": "approved", "approval_id": "12.5"},
        {"decision": "approved", "approval_id": "-1"},
    ],
    ids=["bare-string", "no-id", "int-not-str", "non-digit", "decimal", "signed"],
)
def test_a_missing_or_malformed_reference_is_refused(
    agent_conn: Connection, resume_value: object
) -> None:
    from langgraph.types import Command

    _seed(agent_conn)
    agent = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg = {"configurable": {"thread_id": "t-malformed"}}
    paused = agent.invoke({"messages": [("user", "wire acme")]}, cfg)
    aid = paused["__interrupt__"][0].value["approval_id"]
    with tx(agent_conn):
        approvals.cas_approve(agent_conn, aid, "operator", now_utc())

    result = agent.invoke(Command(resume=resume_value), cfg)
    assert PAID == [], f"a malformed reference ({resume_value!r}) must not execute anything"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("no approval reference was given" in t for t in texts), texts


def test_a_second_resume_with_the_same_reference_is_refused(agent_conn: Connection) -> None:
    """Single-use, demonstrated across two separate graph threads presenting
    the identical granted reference -- exactly one of them may execute."""
    from langgraph.types import Command

    _seed(agent_conn)
    granted = _granted(
        agent_conn,
        "tool.send_wire",
        {"beneficiary": "acme", "amount_eur": 2400.0},
        proposed_by="onedoor-langchain-agent",
    )

    first = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg_a = {"configurable": {"thread_id": "t-use-1"}}
    first.invoke({"messages": [("user", "wire acme")]}, cfg_a)
    first.invoke(Command(resume={"decision": "approved", "approval_id": str(granted)}), cfg_a)
    assert PAID == [2400.0], "the first presentation must execute"

    second = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg_b = {"configurable": {"thread_id": "t-use-2"}}
    second.invoke({"messages": [("user", "wire acme")]}, cfg_b)
    result = second.invoke(
        Command(resume={"decision": "approved", "approval_id": str(granted)}), cfg_b
    )
    assert PAID == [2400.0], "a second presentation of the same reference must not execute again"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("already been used" in t for t in texts), texts


def test_the_kill_switch_at_resume_leaves_the_grant_unused(agent_conn: Connection) -> None:
    """Resuming re-runs `wrap_tool_call` from the top (a known, documented
    limitation): the fresh, ref-less `_decide()` call there is itself a
    Tier-3 proposal attempt, which the kill-switch-first check denies
    outright (`decision.py:859-866`) before `_proposed()` -- and so before
    `interrupt()` and the approval_ref-based call -- is ever reached. Unlike
    the MCP path (which presents a granted reference in the same call the
    switch denies, consuming it), the grant here is never presented while
    the switch is on, so it stays `approved`, not consumed."""
    from langgraph.types import Command

    _seed(agent_conn)
    agent = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg = {"configurable": {"thread_id": "t-denied"}}
    paused = agent.invoke({"messages": [("user", "wire acme")]}, cfg)
    aid = paused["__interrupt__"][0].value["approval_id"]
    with tx(agent_conn):
        approvals.cas_approve(agent_conn, aid, "operator", now_utc())
        killswitch.set_engaged(agent_conn, True, origin="operator")

    result = agent.invoke(Command(resume={"decision": "approved", "approval_id": str(aid)}), cfg)
    assert PAID == [], "a resumption the engine denies runs nothing"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any(
        "kill switch is on" in t and "nothing ran" in t and "not used" in t for t in texts
    ), texts
    state = agent_conn.execute("SELECT state FROM approvals WHERE id=?", (aid,)).fetchone()[0]
    assert state == "approved", "a stop must leave the grant usable, not consume it"


def test_lifting_the_kill_switch_lets_the_same_grant_run_once(agent_conn: Connection) -> None:
    """The switch lifted, the same id runs the action exactly once.

    Each `agent.invoke(Command(resume=...), cfg)` resolves that thread's one
    pending interrupt for good, whatever the outcome -- a second resume on
    the SAME thread has nothing left to resume. So the grant's continued
    usability (the actual property under test) is shown across separate
    threads presenting the identical id, exactly as the single-use test
    does: a deny-while-engaged thread, a run-once-after-lifted thread, and a
    refused-second-use thread."""
    from langgraph.types import Command

    _seed(agent_conn)
    denying = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg_deny = {"configurable": {"thread_id": "t-lifted-deny"}}
    paused = denying.invoke({"messages": [("user", "wire acme")]}, cfg_deny)
    aid = paused["__interrupt__"][0].value["approval_id"]
    with tx(agent_conn):
        approvals.cas_approve(agent_conn, aid, "operator", now_utc())
        killswitch.set_engaged(agent_conn, True, origin="operator")
    denying.invoke(Command(resume={"decision": "approved", "approval_id": str(aid)}), cfg_deny)
    assert PAID == [], "still denied while the switch is on"
    state = agent_conn.execute("SELECT state FROM approvals WHERE id=?", (aid,)).fetchone()[0]
    assert state == "approved", "the grant survives the denial untouched"

    with tx(agent_conn):
        killswitch.set_engaged(agent_conn, False, origin="operator")
    running = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg_run = {"configurable": {"thread_id": "t-lifted-run"}}
    running.invoke({"messages": [("user", "wire acme")]}, cfg_run)
    running.invoke(Command(resume={"decision": "approved", "approval_id": str(aid)}), cfg_run)
    assert PAID == [2400.0], "the same grant runs once the switch is lifted"

    reusing = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg_reuse = {"configurable": {"thread_id": "t-lifted-reuse"}}
    reusing.invoke({"messages": [("user", "wire acme")]}, cfg_reuse)
    again = reusing.invoke(
        Command(resume={"decision": "approved", "approval_id": str(aid)}), cfg_reuse
    )
    assert PAID == [2400.0], "a second presentation after it already ran must not run it twice"
    texts = [m.content for m in again["messages"] if isinstance(m.content, str)]
    assert any("already been used" in t for t in texts), texts


def test_the_race_window_where_the_switch_consumes_the_reference(
    agent_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The narrow window between the fresh, ref-less re-propose and the
    approval_ref-based call is timing-dependent in real deployment, not
    reachable by a plain sequential test -- so it is forced here
    deterministically: a second operator engages the switch from inside the
    second `_decide` call itself (the exact moment the reference is about to
    be presented), simulating that race without relying on actual thread
    timing. There, unlike the common case, the reference genuinely is
    presented, honored and consumed before the kill switch denies it --
    the "used up by a stop" message, distinct from the common "not used"
    one, and accurate for this path specifically."""
    from langgraph.types import Command

    import onedoor.integrations.langchain_middleware as mw

    _seed(agent_conn)
    agent = _wire_agent(agent_conn, allow_same_process_approval=True)
    cfg = {"configurable": {"thread_id": "t-race"}}
    paused = agent.invoke({"messages": [("user", "wire acme")]}, cfg)
    aid = paused["__interrupt__"][0].value["approval_id"]
    with tx(agent_conn):
        approvals.cas_approve(agent_conn, aid, "operator", now_utc())

    real_decide = mw.OneDoorMiddleware._decide

    def _decide_racing_the_switch(self, request, *, approval_ref=None):
        if approval_ref is not None:
            with tx(agent_conn):
                killswitch.set_engaged(agent_conn, True, origin="race-window")
        return real_decide(self, request, approval_ref=approval_ref)

    monkeypatch.setattr(mw.OneDoorMiddleware, "_decide", _decide_racing_the_switch)

    result = agent.invoke(Command(resume={"decision": "approved", "approval_id": str(aid)}), cfg)
    assert PAID == [], "still denied -- the switch wins even after a valid ref"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("used up by a stop" in t for t in texts), texts
    state = agent_conn.execute("SELECT state FROM approvals WHERE id=?", (aid,)).fetchone()[0]
    assert state == "consumed", "this path, unlike the common one, does consume the reference"


def test_same_process_mode_refuses_resume_without_the_opt_in(agent_conn: Connection) -> None:
    """This middleware holds a direct database connection, so there is
    no real boundary between proposing and granting unless a deployer says so
    explicitly. The default refuses resume even for a genuinely granted id."""
    from langgraph.types import Command

    _seed(agent_conn)
    agent = _wire_agent(agent_conn)  # allow_same_process_approval defaults to False
    cfg = {"configurable": {"thread_id": "t-same-process"}}
    paused = agent.invoke({"messages": [("user", "wire acme")]}, cfg)
    aid = paused["__interrupt__"][0].value["approval_id"]
    with tx(agent_conn):
        approvals.cas_approve(agent_conn, aid, "operator", now_utc())

    result = agent.invoke(Command(resume={"decision": "approved", "approval_id": str(aid)}), cfg)
    assert PAID == [], "same-process mode must refuse even a genuinely granted reference"
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("process boundary" in t for t in texts), texts
    state = agent_conn.execute("SELECT state FROM approvals WHERE id=?", (aid,)).fetchone()[0]
    assert state == "approved", "the same-process refusal must not even touch the approval"


def test_interrupt_declined_does_not_execute(agent_conn: Connection) -> None:
    from langgraph.types import Command

    _seed(agent_conn)
    agent = create_agent(
        model=_model(
            AIMessage(
                content="",
                tool_calls=[
                    _call("send_wire", {"beneficiary": "acme", "amount_eur": 2400.0}, "c1")
                ],
            ),
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
            AIMessage(
                content="",
                tool_calls=[_call("pay_invoice", {"invoice_id": "A1", "amount_eur": 500.0}, "c1")],
            ),
            AIMessage(content="over the limit"),
        ),
        tools=[pay_invoice],
        middleware=[OneDoorMiddleware(agent_conn, _config())],
    )
    result = await agent.ainvoke({"messages": [("user", "pay A1")]})
    assert PAID == []
    texts = [m.content for m in result["messages"] if isinstance(m.content, str)]
    assert any("bounds" in t for t in texts)
