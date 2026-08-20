# onedoor as LangChain agent middleware

LangChain v1 middleware exposes `wrap_tool_call`, which receives the model's
proposed tool call *before* it executes and may return its own `ToolMessage`
instead of running it. That is the shape of a decision point.

```python
from langchain.agents import create_agent
from onedoor.integrations.langchain_middleware import OneDoorMiddleware, open_engine

conn, config = open_engine("agent.db", "policies.yaml")

agent = create_agent(
    model, tools,
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
'pay_invoice' denied (cap_eur_day: EUR/day cap 500.00 reached)` and can adapt --
tell the user, try something smaller, stop. An exception would give it nothing to
work with.

## Human approval

Two modes. The default returns the approval notice as the tool's output and lets
the agent carry on:

```python
OneDoorMiddleware(conn, config)                      # on_proposed="message"
```

With a checkpointer, `interrupt` pauses the graph instead:

```python
agent = create_agent(
    model, tools,
    middleware=[OneDoorMiddleware(conn, config, on_proposed="interrupt")],
    checkpointer=MemorySaver(),
)

paused = agent.invoke({"messages": [...]}, cfg)
paused["__interrupt__"][0].value
# {'approval_id': 7, 'action_type': 'tool.send_wire', 'reason': 'tier_confirm'}

agent.invoke(Command(resume="approved"), cfg)
```

Resuming does not trust the approval blindly. The approval is consumed
atomically and the request is evaluated again -- the kill switch, the caps and
the bounds all still apply. An approval is permission to ask a second time, not
a permit.

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
