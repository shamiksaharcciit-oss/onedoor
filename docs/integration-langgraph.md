# LangGraph integration

Wrap LangChain tools so every invocation in a LangGraph workflow goes through
the door — and let Tier 3 meet LangGraph's native `interrupt()` for a
*governed* human-in-the-loop. Working example: `examples/langgraph_tools.py`
(self-tests with no LLM and no API keys: `python -m examples.langgraph_tools`).

## The division of labor

LangGraph owns orchestration: state, edges, retries, checkpointing, which
node calls what. onedoor owns actuation policy: default-deny for tools the
policy table doesn't know (including tools an agent discovers mid-run), value
bounds on arguments, caps shared across the whole graph per action type,
dry-run for new tools, the kill switch over the entire workflow, and the
decide → enforce → report audit trail. Neither reaches into the other.

## Wrapping tools

```python
from examples.langgraph_tools import governed, make_engine

conn, config = make_engine("guardrail.db", Path("policies.yaml"))
weather = governed(get_weather, conn, config)          # a @tool from langchain
pay     = governed(send_payment, conn, config)
```

A wrapped tool keeps its name, description and args schema, so agents and
`ToolNode` see it unchanged. Outcomes surface as the tool's output:

```
Weather in Utrecht: 19°C, light rain (of course).            # permitted + audited
onedoor: 'set_thermostat' denied (bounds: param
    'temperature'=30.0 above max 23.0)                        # never executed
onedoor: 'send_payment' requires human approval
    (reason: tier_confirm, approval_id=1).                    # parked
```

Returning the reason as tool output is deliberate: the agent reads it and
adapts — retries within bounds, explains to the user, or moves on — while the
audit log records what it tried.

## Tier 3 meets `interrupt()` — the governed human-in-the-loop

Pass `on_proposed="interrupt"` and a proposed action pauses the graph at that
node (checkpointed, resumable), carrying the approval id:

```python
pay = governed(send_payment, conn, config, on_proposed="interrupt")
# ... build graph with a checkpointer ...
paused = app.invoke({"result": ""}, cfg)
paused["__interrupt__"][0].value
# {'approval_id': 1, 'action_type': 'tool.send_payment',
#  'params': {'payee': 'acme', 'amount_eur': 120.0}, 'reason': 'tier_confirm'}

app.invoke(Command(resume="approved"), cfg)   # human said yes -> executes + reports
```

What each layer contributes: LangGraph provides the pause/resume machinery;
onedoor provides the policy about *what* pauses; bounds guarantee the human
only ever sees in-limits requests; and the audit log records the full arc —
proposal, approval, execution, receipt — as linked rows. Resuming with
anything other than `"approved"` leaves the action unexecuted and the
refusal recorded.

## Notes

- **Caps are per action type, graph-wide**: twenty nodes calling
  `payments.transfer` share one daily budget — a property no per-node logic
  gives you.
- **Async graphs**: the engine call is synchronous; wrap it in
  `asyncio.to_thread` and keep the module lock.
- **Multi-process / distributed graphs**: point the wrapper at the HTTP
  decision service instead of an embedded connection
  ([decision service guide](integration-service.md)).
- **Sessions**: LangGraph's `thread_id` is a natural session identity — the
  session-aware-trust research track (ROADMAP.md) would let a thread with a
  history of denials find its autonomy degraded.
