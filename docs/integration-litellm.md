# LiteLLM adapter integration

Run the engine inside a LiteLLM proxy as a custom guardrail:
`async_pre_call_hook` governs completions and — because LiteLLM routes its
MCP gateway's tool calls through the same hook (`call_type="call_mcp_tool"`)
— every MCP tool call.

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

## Status and caveats

Experimental example (`examples/litellm_guardrail.py`), graduating to a
supported integration in v0.5 (see ROADMAP.md). Known simplifications, stated
in its docstring: the engine call is synchronous (offload for busy proxies);
permitted intents are reported at pre-call rather than carried to the
post-call hook. Approvals are released via the decision service or any
process sharing the DB.
