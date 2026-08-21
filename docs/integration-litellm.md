# LiteLLM adapter integration

Run the engine inside a LiteLLM proxy as a custom guardrail:
`async_pre_call_hook` governs completions and — because LiteLLM routes its
MCP gateway's tool calls through the same hook (`call_type="call_mcp_tool"`)
— every MCP tool call.

Install: `pip install "onedoor[litellm]"`.

## What it adds over LiteLLM's built-in MCP ACLs

| LiteLLM built-in | With onedoor |
|---|---|
| Tool allow/block lists | Default-deny + per-tool policy |
| Allowed parameter *names* | Value-level bounds (`amount_eur <= 500`) |
| Allow / deny | Also **defer** (approval id), **dry-run** |
| Key/team/org hierarchy | (keep it — decides *who may ask*) |
| — | Race-free daily caps per action type |
| — | Kill switch over everything |
| — | Append-only decision audit with reasons |

The two compose: LiteLLM's hierarchy decides who may ask; onedoor decides what
may happen.

## Configure

```yaml
# litellm config.yaml
guardrails:
  - guardrail_name: onedoor
    litellm_params:
      guardrail: examples.litellm_guardrail.OneDoorGuardrail
      mode: pre_call
      policies: /abs/path/policies.yaml
      db_path: /var/lib/onedoor/gateway.db
```

Rejections surface to the caller with the onedoor reason string (bounds detail,
approval id, kill switch). Self-test without a proxy:
`python -m examples.litellm_guardrail`.

## The two-phase flow, across two hooks

AADP separates authorization from execution, so the adapter uses two hooks:

| Hook | What it does |
|---|---|
| `async_pre_call_hook` | Decides. On permit, holds the `PermittedIntent` in a pending map keyed by `data["litellm_call_id"]`. **Reports nothing** — the gateway has not acted yet. |
| `async_post_call_success_hook` | Pops the permit and reports the real outcome (model, token usage). |
| `async_post_call_failure_hook` | Pops the permit and reports the failure with the error. |

The permit is a promise to report, not a report. Until `0.3.6` this example
called `report_result(ok=True)` from the pre-call hook, asserting success before
the gateway had done anything — a violation of the very contract the adapter
demonstrates. `tests/examples/test_litellm_guardrail.py` now holds the line: after
the pre-call hook the audit must contain an intent and **no result**.

**Correlation** is `data["litellm_call_id"]`, which LiteLLM sets on every governed
request before guardrails run, on the completion and `call_mcp_tool` paths alike.
If it is ever absent the adapter refuses the call *before* deciding, so no permit
is issued that it could not report on. It does not fall back to object identity:
the post-call hook receives a dict derived from the pre-call one, not the same
object.

**The pending map is in process memory**, and that is a known limitation rather
than an oversight. A gateway restart between the two hooks strands the permit: the
audit keeps its honest "intended, unconfirmed" row and the reservation reclaimer
releases the budget at the deadline. This mirrors `ND-010` in the decision service.

## Status and caveats

Experimental example (`examples/litellm_guardrail.py`), graduating to a
supported integration (`ND-044` in [BACKLOG.md](../BACKLOG.md)). It is **conformant to the
two-phase contract** as of `0.3.6` (`ND-021`) and covered by tests, but it ships
as an example rather than a packaged enforcement point — unlike the MCP proxy and
the LangChain middleware, which live under `onedoor/`.

Remaining simplifications, stated in its docstring: the engine call is
synchronous (offload for busy proxies), and the pending-intent map is in process
memory. Approvals are released via the decision service or any process sharing
the DB.
