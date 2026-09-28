# MCP proxy integration

Put the engine between any MCP host and any stdio MCP tool server. Neither
side needs modification; unknown tools are denied by default.

## Run

```bash
python -m onedoor.mcp.proxy \
  --downstream "python -m your_real_mcp_server" \
  --policies mcp_policies.yaml \
  --db /var/lib/onedoor/mcp.db
```

The proxy speaks MCP's stdio transport (newline-delimited JSON-RPC) on both
sides. Everything except `tools/call` is forwarded verbatim; every
`tools/call` becomes an `ActionRequest` with action type `mcp.<tool_name>`
and the tool arguments as params.

## Pointing a host at the proxy (Claude Desktop example)

```jsonc
// claude_desktop_config.json
{
  "mcpServers": {
    "governed-tools": {
      "command": "python",
      "args": ["-m", "onedoor.mcp.proxy",
               "--downstream", "python -m your_real_mcp_server",
               "--policies", "/abs/path/mcp_policies.yaml",
               "--db", "/abs/path/mcp.db"]
    }
  }
}
```

## What the agent sees

- **Permitted** → the call is forwarded; the downstream result returns
  unchanged; the audit log records intent + outcome.
- **Denied** → a tool error naming the reason: `onedoor: 'set_thermostat'
  denied (reason: bounds — param 'temperature'=30 above max 23.0)`. The call
  never reached the tool.
- **Proposed** → a tool error carrying the `approval_id`. The call is parked
  until an operator approves it (see below).
- **Dry-run** → a non-error result: "would have executed, nothing forwarded."

Well-behaved agents read these messages and adapt; the audit log records
what they tried either way.

## Releasing approvals

The proxy's host side is the agent, so approving and operating the kill switch
are not available there: every `onedoor/*` method is refused by the proxy
itself, and never forwarded.

An operator approves outside the agent's channel, on their own connection to
the proxy's store:

```python
from onedoor.guardrail import approvals
from onedoor.store.clock import now_utc
from onedoor.store.db import Database, tx

conn = Database("onedoor-mcp.db").connect()
with tx(conn):
    approvals.cas_approve(conn, approval_id, "operator-name", now_utc())
```

The agent then sends the same call again with the approval reference in the
request's `_meta`:

```json
{"method": "tools/call", "params": {"name": "send_payment",
  "arguments": {"payee": "webshop", "amount_eur": 49.99},
  "_meta": {"onedoor/approval_ref": 1}}}
```

The reference is honoured once, for exactly the approved action, and only if
someone other than the proxy approved it; anything else is evaluated as if no
reference were sent. The kill switch is operated the same way, from the
operator's side: `killswitch.set_engaged(conn, True)`.

## Notes

- Policy tip: give read-only tools a `compensating_command` of a registered
  no-op action; give real actuations a true reversal tool, or leave them
  Tier 3 — the engine will not auto-execute what it cannot undo.
- stdio transport only in v0.3; streamable-HTTP MCP is a v0.5 item.
- Demo end to end: `python -m scripts.demo_mcp` (toy downstream included).
