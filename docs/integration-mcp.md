# MCP proxy integration

Put the engine between any MCP host and any stdio MCP tool server. Neither
side needs modification; unknown tools default-deny to a human.

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
  until a human releases it.
- **Dry-run** → a non-error result: "would have executed, nothing forwarded."

Well-behaved agents read these messages and adapt; the audit log records
what they tried either way.

## Releasing approvals

Run the decision service against the same policies/DB and use its approval
endpoints, or use the proxy's demo JSON-RPC methods (`onedoor/approve`,
`onedoor/kill` — non-standard, intended for demos and local use).

## Notes

- Policy tip: give read-only tools a `compensating_command` of a registered
  no-op action; give real actuations a true reversal tool, or leave them
  Tier 3 — the engine will not auto-execute what it cannot undo.
- stdio transport only in v0.3; streamable-HTTP MCP is a v0.5 item.
- Demo end to end: `python -m scripts.demo_mcp` (toy downstream included).
