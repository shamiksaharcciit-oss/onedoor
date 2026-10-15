# onedoor as LangChain agent middleware

LangChain v1 middleware exposes `wrap_tool_call`, which receives the model's
proposed tool call *before* it executes and may return its own `ToolMessage`
instead of running it. That is the shape of a decision point.

```python
from langchain.agents import create_agent
from onedoor.integrations.langchain_middleware import OneDoorMiddleware, open_engine

conn, config = open_engine("agent.db", "policies.yaml")

agent = create_agent(
    model,
    tools,
    middleware=[OneDoorMiddleware(conn, config)],
)
```

`pip install "onedoor[langchain]"`.

## Middleware or the tool wrapper?

Both, for different graphs. They call the same engine and read the same policy
file, so an action type governs a tool whichever route it arrives by.

| | middleware | `governed()` wrapper |
|---|---|---|
| attaches to | `create_agent` agents | any graph, incl. a bare `ToolNode` |
| coverage | every tool the agent has, including ones added later | each tool you remember to wrap |
| async | native `awrap_tool_call` | wrap the call in `asyncio.to_thread` |

The middleware is the better default when you use the agent harness: a tool
added next month is governed without anyone remembering to wrap it. The wrapper
is what you need in a hand-built `StateGraph`, where there is no harness for
middleware to attach to.

## The three outcomes

```
permit   the handler runs, the result is reported, the ToolMessage passes back
deny     the handler never runs; the reason returns as the tool's output
propose  a human decides
```

A denial is a message, not an exception. The agent reads `onedoor:
'pay_invoice' denied (budget_exhausted: €/day cap 500 reached)` and can adapt --
tell the user, try something smaller, stop. An exception would give it nothing to
work with.

## Human approval

Two modes. The default returns the approval notice as the tool's output and lets
the agent carry on:

```python
OneDoorMiddleware(conn, config)  # on_proposed="message"
```

With a checkpointer, `interrupt` pauses the graph instead:

```python
agent = create_agent(
    model,
    tools,
    middleware=[
        OneDoorMiddleware(
            conn, config, on_proposed="interrupt", allow_same_process_approval=True
        )
    ],
    checkpointer=MemorySaver(),
)

paused = agent.invoke({"messages": [...]}, cfg)
paused["__interrupt__"][0].value
# {'approval_id': 7, 'action_type': 'tool.send_wire', 'reason': 'tier_confirm'}

agent.invoke(
    Command(resume={"decision": "approved", "approval_id": "7"}),
    cfg,
)
```

**The agent's own process never grants an approval.** A human (or whatever
process actually faces one) grants the proposal through the decision
service's `POST /v1/approvals/{id}/grant` -- over HTTP, with an admin key the
agent's process never holds. The resume value's `approval_id` is a bare
*reference* to that id, not a credential: presenting it grants nothing by
itself. `decide_and_reserve` resolves it against the same checks every
presented reference gets -- the row must already be `approved`, the action
and arguments must match what was actually proposed, the principal
presenting it must match the principal that proposed it (never the agent's
own `agent_principal`, by construction), and it is consumed once. A
reference to someone else's approval, to one for different arguments, to
one not yet granted, or a missing/malformed `approval_id` all fail closed
with a message naming the refusal; every other key in the resume value
(a former credential, a claimed decision) is ignored.

**`allow_same_process_approval=True` is required for `"interrupt"` mode.**
This middleware holds a direct database connection, so by default there is
no real boundary between the agent proposing and whatever calls `/grant` if
they share this process and connection -- resuming refuses unless a
deployer explicitly accepts that. Wiring the agent through the HTTP decision
service with only a decide key, instead of a direct connection, would give a
real boundary; that wiring does not exist yet.

Resuming does not trust the approval blindly either way. The approval is
consumed atomically and the request is evaluated again -- the kill switch,
default-deny, dry-run, the caps and the bounds all still apply. An approval
is permission to ask a second time, not a permit.

**A stop does not use up a grant here.** Resuming re-proposes before
presenting the reference (see the known limitation below), so if the kill
switch is on, it is that fresh, ref-less proposal the switch denies -- the
reference is never presented, so the grant is never consumed. The refusal
says so: nothing ran, and the approval was not used. This differs from the
MCP integration, which presents a granted reference in the same call the
kill switch denies, consuming it there -- an MCP operator must grant again
after a stop; a LangChain one does not. Once the switch is lifted, resuming
with the same `approval_id` runs the action exactly once, unless an
approver denies or withdraws the grant first -- and today there is no route
that does that (`/deny` only refuses an approval still `pending`; see the
known limitations list).

**Known limitations:**

- Resuming re-executes `wrap_tool_call` from the top (a LangGraph property),
  including the proposal call above `_proposed` -- so every resume attempt
  also creates a second, never-granted pending approval, left behind
  regardless of outcome. Harmless (it is never the one presented or
  consumed) but visible via `GET /v1/approvals`. Tracked for a future
  release.
- No route withdraws an already-granted approval. Once granted through
  `/grant`, an operator who changes their mind cannot deny or revoke it
  before it is resumed (`/deny` requires `state='pending'`); it can only
  expire on its original TTL. Tracked for a future release.

## Why `open_engine` exists

LangGraph runs the tools node on a worker thread. A SQLite connection opened
with the default `check_same_thread=True` raises `sqlite3.ProgrammingError` the
moment it is touched there -- and not in a unit test that calls the middleware
directly, only in a real agent run.

`open_engine` opens the connection correctly, runs migrations and loads policy.
Build your own connection if you prefer, but pass `check_same_thread=False`.

One connection is shared behind a lock. For multi-process agents, run the HTTP
decision service instead and consult it over the network --
see `integration-service.md`.

## Action naming

A tool named `pay_invoice` becomes the action type `tool.pay_invoice`, matching
the wrapper. Change it with `action_prefix=` if your policy file uses another
convention.
