# onedoor

**A tiered guardrail engine for agentic systems.**
The model proposes; the policy layer disposes.

Every action in an agentic system — scheduled, rule-fired, LLM-proposed, or
human-clicked — is a structured `ActionRequest` evaluated by one executor
against a policy table before anything touches the world. There is one door.
Nothing else is allowed to call a connector.

```
kill switch → policy lookup / default-deny → tier-1 integrity (no undo, no
autonomy) → bounds → dry-run → caps → two-phase execute → append-only audit
```

## Why another guardrail project?

Most "guardrails" govern what a model may *say*. This engine governs what an
agent may *do* — and it takes positions most frameworks leave as wishes:

- **Default-deny.** An unlisted action type is not an error and not a pass:
  it resolves to propose-and-confirm, with the reason recorded.
- **Reversibility is a precondition for autonomy.** An auto-tier action whose
  policy declares no compensating command is demoted to human approval at
  runtime — and the policy loader refuses to boot if a Tier-1 entry lacks one.
  Undo is not a feature; it is the admission ticket to auto-execution.
- **The kill switch outranks everything, including prior consent.** Checked
  before policy lookup; an already-approved action arriving while the switch
  is engaged is blocked (without spawning an approval loop). Reads stay exempt
  — you want visibility *during* the incident.
- **Bounds are validated before a human ever sees a proposal**, so the
  approval screen can only contain physically sane requests. The human decides
  *whether*, never has to catch *whether it's insane*.
- **Rehearsal must not spend a real budget.** Dry-run is resolved before cap
  accounting; new action types start in dry-run and log "would have executed".
- **Caps are reserved race-free** inside the deciding transaction
  (`BEGIN IMMEDIATE`), so two concurrent requests cannot share the last slot.
- **Two-phase execution.** Tx A decides, reserves caps, and records intent;
  the connector call runs outside any DB lock under a hard timeout; Tx B
  appends the result. A hung smart-plug API cannot hold the engine hostage,
  and a crash leaves an honest "intended, unconfirmed" trail.
- **The audit log is append-only** — decisions, results, denials, dry-runs,
  and kill-switch blocks, all with typed reason codes, never updated in place.
- **Effects, not just names.** The same real-world effect through
  differently-named tools shares one budget and one tier floor
  (`effects: [money.egress]` + deterministic `param_effects` rules for
  generic tools) — measured coverage and honest residue in
  `experiments/aliasing_benchmark.py`.
- **Policies are data, not code** (`config/policies.yaml`): tiers, bounds,
  caps, undo windows, dry-run flags. Changing what's allowed never means
  changing the engine.

## Tiers

| Tier | Meaning | Example policy |
|------|---------|----------------|
| 0 | observe only | reads (exempt from the kill switch) |
| 1 | auto-execute, reversible, in-bounds | toggle with `compensating_command` + 15-min undo |
| 2 | auto-execute under cumulative caps | rate + €/day + €/month budgets |
| 3 | propose-and-confirm (TTL'd approval) | anything irreversible, unlisted, or over cap |

## Documentation

Developer guides live in [`docs/`](docs/index.md): the three-minute mental
model, an integration guide per surface — [library](docs/integration-library.md),
[HTTP decision service](docs/integration-service.md),
[MCP proxy](docs/integration-mcp.md),
[LiteLLM adapter](docs/integration-litellm.md),
[LangGraph](docs/integration-langgraph.md) — and the full
[policy reference](docs/policy-reference.md).

## Quickstart

Requires Python ≥ 3.12.

```bash
pip install -e ".[dev]"
pytest                    # 111 tests — the guardrail suite is the release blocker
python -m scripts.demo    # one of everything, end to end, zero external deps
```

The demo walks the whole surface: auto-execution and undo, default-deny into a
real approval that then executes, a bounds rejection, cap exhaustion, dry-run,
and the kill switch clamping an auto action to propose-and-confirm.

## A policy, concretely

```yaml
- action_type: ha.set_climate
  tier: 1
  dry_run: true                      # new action types rehearse first
  compensating_command: ha.restore_climate
  bounds:
    numeric:
      temperature: { min: 17, max: 23 }
    required: [entity_id, temperature]
    strict_params: true
```

## v0.2 — the decision/enforcement split, and the engine on other people's doors

v0.2 separates the engine into the classic authorization pair — a **Policy
Decision Point** and **Policy Enforcement Points** — without changing a single
decision's semantics (the v0.1 suite passes unchanged):

- `decision.decide_and_reserve(request, ...)` — Tx A: the full ordered check
  pipeline, cap reservation, and the intent row in the audit log. Returns
  either a terminal result (denied / proposed / dry-run) or a
  `PermittedIntent`: an obligation the caller must enforce.
- `decision.report_result(intent, ok, ...)` — Tx B: the linked, append-only
  execution receipt, whatever happened.

The in-process executor is now literally these two phases composed around a
connector call. Any other enforcement point — a gateway filter, a tool
wrapper — composes them around its own act.

**The first external enforcement point ships with it: an MCP proxy.**
`onedoor.mcp.proxy` speaks MCP's stdio transport on both sides: an agent host
connects to it as if it were the tool server; it spawns the real server as a
subprocess and forwards everything except `tools/call`, which becomes an
`ActionRequest` (`mcp.<tool>`) through the full pipeline — unknown tools
default-deny to a human, bounds are checked before the tool ever sees the
call, money waits for approval, and the kill switch clamps everything at once.

```bash
python -m scripts.demo_mcp   # an agent's-eye view: 7 calls, every mechanism
```

This makes the engine usable with agents you don't control: point any MCP
host at the proxy instead of the tool server, write a policy file, done.
(The proxy's `onedoor/approve` and `onedoor/kill` JSON-RPC methods are demo
conveniences, not part of MCP.)

## Using it from an AI gateway (LiteLLM example)

`examples/litellm_guardrail.py` is an experimental adapter showing the engine
as a LiteLLM custom guardrail: `async_pre_call_hook` governs completions
(model allow-list as *value* bounds, daily caps) and — because LiteLLM routes
its MCP gateway's tool calls through the same hook (`call_type="call_mcp_tool"`)
— every MCP tool call, with default-deny, bounds, tier-3 approval and the kill
switch. Run `python -m examples.litellm_guardrail` for a proxy-free self-test.
What this adds over the gateway's built-in MCP ACLs: decisions beyond
allow/deny (defer with an approval id, dry-run), value-level bounds rather
than parameter-name lists, race-free caps, and an audit row with a reason for
every decision. `litellm` is not a dependency of this package — the example
imports it only if you have it.

## The decision service (v0.3)

The PDP over HTTP, so any enforcement point in any language can consult the
engine:

```bash
pip install "onedoor[service]"
ONEDOOR_DECIDE_KEYS=dev ONEDOOR_ADMIN_KEYS=root \
ONEDOOR_POLICIES=config/policies.yaml \
uvicorn onedoor.service.app:create_app --factory --port 8470
```

`POST /v1/decide` returns the decision; a permitted one carries an
`intent_audit_id` — enforce, then `POST /v1/report` the outcome. Approvals,
denial and the kill switch live under admin-role keys (`ONEDOOR_ADMIN_KEYS`),
separate from decide-role keys by design: the process that asks for permission
should not be the process that grants it. Tier-3 proposals can notify a
webhook (`ONEDOOR_APPROVAL_WEBHOOK`, Slack-compatible payload), and installing
`onedoor[otel]` lights up OpenTelemetry spans and decision counters with no
code changes. See `ROADMAP.md` for where this is going (tenancy, Postgres,
OIDC, audit hardening).

## Origin & status

Extracted from a personal single-user control plane (home/energy/money with an
LLM agent layer), where this engine has governed every action since July 2026 —
the domain modules stayed home; the engine, its mock connector, its demo action
types, and its full test suite are what you see here. v0.2: SQLite-backed,
single-process, synchronous; PDP/PEP split with an MCP proxy as the first
external enforcement point. Deliberately boring technology; the design is the
contribution.

## License

Apache-2.0.

## Links

- Source: <https://github.com/shamiksaharcciit-oss/onedoor>
- Package: <https://pypi.org/project/onedoor/>
- Licence: Apache-2.0
