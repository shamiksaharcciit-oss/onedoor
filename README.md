# onedoor

[![CI](https://github.com/shamiksaharcciit-oss/onedoor/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/shamiksaharcciit-oss/onedoor/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/onedoor.svg)](https://pypi.org/project/onedoor/)
[![Python](https://img.shields.io/pypi/pyversions/onedoor.svg)](https://pypi.org/project/onedoor/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

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

## Quickstart — four commands, from PyPI

Requires Python ≥ 3.12. Nothing below needs this repository.

```bash
pip install "onedoor[service]"
python -c "import shutil; from onedoor import templates; shutil.copy(templates.PAYMENTS.policies_path, 'policies.yaml')"
export ONEDOOR_DECIDE_KEYS=dev ONEDOOR_ADMIN_KEYS=root ONEDOOR_DB=onedoor.db ONEDOOR_POLICIES=policies.yaml
python -m uvicorn onedoor.service.app:create_app --factory --host 127.0.0.1 --port 8099
```

On Windows PowerShell, replace the `export` line with:
`$env:ONEDOOR_DECIDE_KEYS="dev"; $env:ONEDOOR_ADMIN_KEYS="root"; $env:ONEDOOR_DB="onedoor.db"; $env:ONEDOOR_POLICIES="policies.yaml"`

Step 2 copies the **shipped payments pack** — worked examples, not a compliance
artifact; read `PACK.md` beside it in the installed package. Without a policy file the
service has nothing to enforce and will not start.

Then, in another terminal:

```bash
curl -s localhost:8099/v1/health
curl -s -X POST localhost:8099/v1/decide -H "Authorization: Bearer dev" -H "Content-Type: application/json" -d '{"request_id":"11111111-1111-1111-1111-111111111111","action_type":"payments.transfer","params":{"amount_eur":120.00,"destination_account":"acct-1"},"source":"llm","rationale":"first look"}'
curl -s -X POST localhost:8099/v1/decide -H "Authorization: Bearer dev" -H "Content-Type: application/json" -d '{"request_id":"22222222-2222-2222-2222-222222222222","action_type":"wire.anywhere","params":{},"source":"llm","rationale":"first look"}'
```

What you should see — the three outputs that tell you it works:

```
{"status":"ok","kill_switch":false,"pending_intents":0}
{"decision":"permitted","reason":"passed","effective_tier":2,...,"intent_audit_id":1,...}
{"decision":"proposed","reason":"default_deny","effective_tier":3,...,"approval_id":1,...}
```

The second is a **permit** — capped, reversible, and you now owe a `/v1/report`. The
third is **default-deny**: `wire.anywhere` is in no policy, so it is not refused outright
but escalated to a human, with an approval waiting. Nothing self-promotes.

**Numbers in `params` are JSON numbers** (`120.00`), not strings — see *Known
limitations* for the decimal-string asymmetry.

### Working in this repository instead

```bash
pip install -e ".[dev]"
python -m scripts.gate --all   # the four gates, the documented way
python -m scripts.demo         # one of everything, end to end, zero external deps
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
every decision.

It honours the two-phase contract across two hooks: the pre-call hook decides
and holds the permit without reporting anything, and the post-call success and
failure hooks report what actually happened. `litellm` is not a runtime
dependency of the engine — install the example's own extra,
`pip install "onedoor[litellm]"`.

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
code changes. [BACKLOG.md](BACKLOG.md) is where this is going, ticket by ticket,
and [CONFORMANCE.md](CONFORMANCE.md) is the honest per-requirement status against
the AADP draft — gaps included.

## Origin & status

Extracted from a personal single-user control plane (home/energy/money with an
LLM agent layer), where this engine has governed every action since July 2026 —
the domain modules stayed home; the engine, its mock connector, its demo action
types, and its full test suite are what you see here. v0.2: SQLite-backed,
single-process, synchronous; PDP/PEP split with an MCP proxy as the first
external enforcement point. Deliberately boring technology; the design is the
contribution.

## Signed receipts

```bash
pip install 'onedoor[signed]'
```

Ed25519 signatures over each row's hash, off until a deployer turns them on. **Signing
is an extra, and configuring it without the library installed makes the process refuse
to start** — a deployment that believes it is signing and is not is the failure this
guards, and that belief comes from config, so the check belongs at enable time.

The private key is yours and never enters the repo, the database or a receipt;
`key_id` is a fingerprint *derived* from the public key; rotation grows a keyring that
is never pruned, so receipts signed by a retired key verify forever.

**A receipt system must not be its own witness.** A signature that matches a public key
found in the same store as the row it signs is reported as **`self_consistent`**, never
as verified — an attacker who can write the database supplies both halves. Pass a
trusted `key_id` from outside the store and the same signature reports `verified`.

## Anchoring

Merkle roots over ranges of chained rows, published wherever a deployer chooses — a
file, an endpoint, a commit, a line taped to a wall. **Independence is the metric, not
the medium.** A third party holding the published root and one exported receipt verifies
membership with nothing else of ours; the acceptance test runs the verifier in a
directory containing exactly those two files.

**onedoor never vouches for itself: at the key layer and the anchor layer alike,
`verified` requires something the store does not hold.** A signature that matches the
store's own keyring, or a proof that checks against a root the store itself carries, is
reported as `self_consistent` — real information, and not independence.

Anchoring is periodic, so the newest rows are normally un-anchored. That reads as
**`absent`**, not as a fault: a viewer that showed them red would train an operator to
ignore red.

## The receipt viewer

```bash
python -m onedoor.viewer --demo-store demo.db --out oneview.html   # labelled sample
python -m onedoor.viewer --store onedoor.db --out oneview.html     # a real store
```

One static, read-only page: the decision receipt with the checks that back it, and the
tail of verdicts. Every displayed value is read from a verified artifact — if the
evidence does not check out, the page shows the failure state and **none of the
receipt's values**. Where something is *not yet produced* rather than wrong, it says
so: hash-chained audit entries (`ND-001`) have not landed, so the chain block says the
chain is **not yet in operation**, naming the ticket, instead of showing a digest it
does not have. *Not yet in operation*, never *not yet produced*: absent-by-schedule
must not read as broken.

## Known limitations

**A decimal string in `params` is refused by a `numeric` bound — and that is a
conformance defect, ours.** `{"amount_eur": "120.00"}` is refused as *must be numeric*
while `{"amount_eur": 120.00}` works, and while `cost_eur` and the cap path both already
read the decimal-string form as money.

AADP §5 requires the opposite: *monetary values are decimal strings, never floating-point
numbers*, a rule that applies **inside `params`**, and the draft's own worked decide
request carries `"amount_eur": "40.00"`. Refusing it also pushes integrators toward binary
floats — the representation the draft's Security Considerations names as an attack surface
on budget arithmetic — so the stricter-looking check steers callers toward the hazard.

Found by the first operator to run `0.6.0` from PyPI. The failing direction is closed (a
denial, never a permit). The fix widens a verdict from denied to permitted, so it lands as
the first post-freeze change rather than a hotfix: see `TICKETS-ND-054.md` and
`escalations/ESCALATION-20260827-006.md`.


Stated here rather than left to be discovered. The full list, with the measurement
behind each, is in [CHANGELOG.md](CHANGELOG.md) and
[CONFORMANCE.md](CONFORMANCE.md); these are the ones a deployer should read before
trusting a boundary to this engine:

- **A `param_effects` `pattern:` still matches URL-valued parameters as strings.** A
  redirector, an IP literal or a percent-encoded host defeats a pattern like
  `https://(pay|bank)\.example\.com/.*`. `ND-040` adds a **`url:` block** that matches
  the canonicalized target instead — opt-in, so existing patterns keep their exact
  meaning — and `experiments/aliasing_benchmark.py` measures the difference: evasive
  **0/4 at L2, 3/4 at L3**, `innocent-ok` 3/3 at both. Three qualifications, because
  the number alone would overstate it: an **undeclared** shortener is still missed
  (the opaque-host class is a starter list, not a census); the **IP-literal** case is
  caught only where the deployer can declare the target's network; and the fourth
  evasive case is not a URL problem at all (see the next item). Use effect labels for
  cooperative inputs; put a fail-closed egress control in front of anything that
  matters.
- **Numeric parameters pass through IEEE double precision before any check.**
  **Workaround, available today: send money amounts as JSON *strings* —** `"500.10"`
  is exact end to end. As JSON *numbers*, a value carrying more precision than a
  double holds can be admitted or denied within about half an ulp of the bound
  (~5e-14 at `500.10`, growing with magnitude — negligible for euros, material for
  large counts). Demonstrated: policy max `500.10`, wire amount
  `500.1000000000000000001`, verdict **allowed**. Affects `0.3.6` and earlier; fixed
  in `0.4.0` by parsing with `parse_float=Decimal` at every ingress.
- **Indirect or obfuscated command construction defeats parameter rules entirely**
  (`ND-048`). `bash -c "$(echo <base64> | base64 -d)"` carries no matchable literal:
  the governed effect is real and **no deterministic parameter rule catches it**. This
  is not a URL problem and `ND-040` does not close it; the benchmark asserts it as
  still-failing so the URL fix cannot be read as covering it. Open gap, no ticketed
  fix.
- **No obligation machinery.** An AADP obligation attached to a permit would be
  silently ignored by onedoor's own enforcement points rather than failing closed
  (`ND-038`).

## License

Apache-2.0.

## Links

- Source: <https://github.com/shamiksaharcciit-oss/onedoor>
- Package: <https://pypi.org/project/onedoor/>
- Licence: Apache-2.0
