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

Everything except `tools/call` and `onedoor/*` is forwarded verbatim. Without
`--mapping`, every `tools/call` becomes an `ActionRequest` with action type
`mcp.<tool_name>` and the tool's own arguments as params, unchanged since
before the mapping file existed.

## The mapping file

A real tool server rarely names its arguments the way a policy's own `bounds`
and `caps` expect, and a value a policy needs may sit nested inside the call.
`--mapping` bridges that: each entry names the onedoor action type a tool
becomes, a free-text effect label (carried in the decision's rationale, not a
new decision input), and a dotted path per onedoor param name into the tool's
own `arguments` object.

```yaml
tools:
  wire_transfer:
    action_type: mcp.send_payment
    effect: write
    params:
      payee: to
      amount_eur: amount.value   # arguments.amount.value in the tool's own call
```

A tool absent from the mapping is **unmapped**: decided as the synthesized
action type `mcp.unmapped.<tool>` — still audited, exactly like any other
action onedoor ever decides, never a silent short-circuit before the audit
log opens — but never forwarded and always answered `onedoor: '<tool>'
refused: not in the gateway's mapping.`, whatever that decision turns out to
be (even if a policy happens to name `mcp.unmapped.<tool>` directly). A
granted approval presented for an unmapped tool is never consumed either.
This is a gateway guarantee, not contingent on how any policy happens to be
written. `tools_list_filter: true` at the mapping file's top level also
narrows the `tools/list` the host sees to only the tools the mapping names.

A dotted path with nothing at it is simply omitted from the resulting
params — not a second fail-closed path of its own; the engine's own
`bounds.required` already denies a request missing a param it requires,
mapped or not.

### Session tracking for sequence rules

`session: per_connection` at the mapping file's top level (default
`none`) turns on the gateway's own sequence-tracking session id, instead
of relying on a caller-supplied session id in the call's own metadata.
Over stdio, one process is one session. Over the streamable-HTTP
transport, every request carries the same bearer token when only one is
configured, so every caller sharing that token hashes to the same
session — multiple MCP hosts behind one deployment's token are tracked
as a single session, not one each. That merged session's history is
shared: one host's calls can cause another's to be held or denied by a
sequence rule, never the reverse. Multi-tenant session isolation over
HTTP needs one token per host, which this gateway does not yet support.

## Declaring a presented audience

An action type whose policy carries `present_bound` grants a permit meant for
a *different* system to consume, never this proxy (AADP -03 §6) — this proxy
forwards straight to a downstream tool, so it is never that audience, and
refuses to forward such a permit itself, reporting `not_attempted`. A caller
that knows which audience it intends (the same declaration the HTTP
service's own `presented_audience` field accepts) may state it the same way,
in `_meta`:

```json
{"method": "tools/call", "params": {"name": "...", "arguments": {...},
  "_meta": {"onedoor/presented_audience": "https://audience.example/consume"}}}
```

Declaring it lets the engine's own audience check succeed instead of denying
the mismatch outright; it does not make this proxy able to forward the
result — the refusal above still applies.

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
- **Unmapped** → a tool error, always: `onedoor: '<tool>' refused: not in the
  gateway's mapping.` The same wording for every policy outcome — an
  unmapped tool never says "requires approval" or "would have executed", and
  is never forwarded.

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

The proxy then evaluates and forwards the arguments the operator approved,
never the retry's own bytes. The reference is honoured once, and the store has
refused any approval made under the proxy's own identity. A reference to a call
still waiting for approval is answered as such and parks nothing new; anything
else is evaluated as if no reference were sent. The kill switch is operated the same way, from the
operator's side: `killswitch.set_engaged(conn, True)`.

## Marking untrusted arguments

A caller that read a tool argument's value from somewhere it does not vouch
for (a web page, a prior tool's own output, anything an upstream LLM
composed rather than the human) can mark which arguments that applies to, so
a policy's own `untrusted_params` rules see them as such:

```json
{"method": "tools/call", "params": {"name": "wire_transfer",
  "arguments": {"to": "webshop", "amount": {"value": 49.99}},
  "_meta": {"onedoor/untrusted": ["arguments.to"]}}}
```

Each path names a tool argument, exactly as `arguments.<path>` addresses it
in the tool's own call (the leading `arguments.` is optional and stripped
either way). With `--mapping`, a marked path is resolved through the
mapping's own table to the onedoor param name it maps onto; a path the
mapping does not carry resolves to nothing, inert, the same as an
unrecognised policy path. Without `--mapping`, a mark applies to that path
directly, since params are the tool's own arguments verbatim. A mark on an
unmapped tool's own arguments is inert either way — the call is always
refused before any policy reads it.

`_meta["onedoor/untrusted"]` must be a JSON list of strings. Anything else —
not a list, or any entry that is not a string — refuses the call outright
with a JSON-RPC error naming the field, rather than silently dropping the
mark: a malformed mark must never be treated as no mark at all.

## Streamable HTTP

`--transport http --host 127.0.0.1 --port 8765` runs the gateway as an HTTP
server instead of a stdio subprocess, carrying the same JSON-RPC messages on
`POST /mcp`. Deliberately scoped: one message per request, answered with a
single JSON object (valid under the streamable-HTTP transport's own spec for
an exchange needing no server-initiated message mid-call, which this
gateway's synchronous decide-forward-report pipeline always is) — no
`Mcp-Session-Id` negotiation, no server-sent-events stream, no batched array
of messages in one body. `--host` only ever binds `127.0.0.1`; anything else
is refused outright. stdio and HTTP decide identically — both call the one
`Proxy.handle_message`.

### Origin and bearer-token checks (HTTP only)

A browser-origin `POST` carries no `Origin` restriction of its own under the
streamable-HTTP transport's own spec, so this gateway validates it itself:
any request carrying an `Origin` header is refused (`403`) unless that
origin is in `--origin-allow`'s list — empty by default, the safe default
for a non-browser caller, since a request with no `Origin` header at all
(any ordinary HTTP client) is unaffected either way. `--origin-allow` is
repeatable for more than one origin.

Allowing one or more origins requires `--token-file` too: a non-empty
allow-list with no token configured would leave the one real protection a
browser-reachable endpoint needs silently absent. `--token-file` names a
file holding a bearer token, read once at start-up; the gateway refuses to
start if the file is empty/whitespace-only or the token is under 16
characters — a blank file reads back as `""`, which would otherwise turn
the check off for any request sending no `Authorization` header at all,
and a short token is cheap enough to guess that configuring one would give
little real protection. Either way the proxy refuses at start-up, naming
the file, rather than accepting it and failing open at request time.

A token file configured (with or without `--origin-allow`) requires every
request to carry `Authorization: Bearer <token>`, compared in constant
time; a missing or incorrect token is refused (`401`).

## Notes

- Policy tip: give read-only tools a `compensating_command` of a registered
  no-op action; give real actuations a true reversal tool, or leave them
  Tier 3 — the engine will not auto-execute what it cannot undo.
- Demo end to end: `python -m scripts.demo_mcp` (toy downstream included).
