# niyam

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

## Quickstart

Requires Python ≥ 3.12.

```bash
pip install -e ".[dev]"
pytest                    # 52 tests — the guardrail suite is the release blocker
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

## Origin & status

Extracted from a personal single-user control plane (home/energy/money with an
LLM agent layer), where this engine has governed every action since July 2026 —
the domain modules stayed home; the engine, its mock connector, its demo action
types, and its full test suite are what you see here. v0.1: SQLite-backed,
single-process, synchronous. Deliberately boring technology; the design is the
contribution.

## License

Apache-2.0.
