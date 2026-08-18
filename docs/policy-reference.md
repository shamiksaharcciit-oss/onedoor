# Policy reference

Policies are data, not code: a YAML file loaded at startup (and re-loadable).
Numeric limits, tiers, undo windows — all live here. Unknown action types are
not configurable: they default-deny to Tier 3 by design.

## Full schema

```yaml
policies:
  - action_type: payments.transfer   # exact match against ActionRequest.action_type
    tier: 3                          # 0 observe | 1 auto | 2 auto-capped | 3 confirm
    dry_run: true                    # default true: new action types rehearse first
    dry_run_until: 2026-09-01T00:00:00Z   # optional: rehearse until this instant
    compensating_command: payments.reverse # REQUIRED for tiers 1 and 2 (loader refuses otherwise)
    undo_window_seconds: 900         # undo availability after execution (tier 1)
    requires_step_up: false          # seam for a second factor on approval
    bounds:
      numeric:
        amount_eur: { min: 0.01, max: 500 }
      enum:
        currency: [EUR]
      required: [payee, amount_eur]
      strict_params: true            # reject params not named above (injection defense)
    caps:
      daily_rate: 20                 # max executions per local day
      eur_day: "50.00"               # tier-2 cumulative budget per day
      eur_month: "500.00"            # tier-2 cumulative budget per month
```

## Field notes

- **tier** — per action type, not per agent. Tier 0 actions are audited reads
  and never reach connectors. Tier 2 uses `cost_eur` on the request against
  the euro caps.
- **dry_run / dry_run_until** — a dry-run is resolved *before* caps: a
  rehearsal never spends budget. Standard practice: every new action type
  ships in dry-run for two weeks. **The two fields are ORed**: `dry_run: true`
  rehearses indefinitely and a `dry_run_until` date will never switch it live.
  To rehearse until a date and then go live, set `dry_run: false` and give the
  date. **Dry-run governs the automatic path only.** A Tier-3 action in dry-run
  still creates a real approval request, and approving it executes for real —
  the approved resumption bypasses the rehearsal, because a human said yes to
  this specific action. Rehearsing a Tier-3 action type means watching what gets
  proposed, not watching nothing happen.
- **compensating_command** — the reversibility rule. Must name another
  registered action type; the undo is submitted through the same pipeline,
  linked to its parent in the audit log. **Every auto-executing tier needs one**
  — tier 1 and tier 2 alike, since a budget does not make an irreversible action
  safe to automate. Entries without one fail at load; an auto action that loses
  its reversal demotes to Tier 3 at runtime.
- **bounds** — validated for *every* tier before proposals are created, so
  approvers only ever see sane requests. `strict_params: true` rejects any
  parameter not mentioned in `numeric`/`enum`/`required`.
- **caps** — `daily_rate` counts executions (reserved at decide time,
  race-free); the euro caps apply to Tier 2 and are reserved the same way.
- **cost_param** — which parameter carries the money. **Any action with a euro
  cap needs one** (or a caller that sets `cost_eur` on the request itself).
  The engine cannot guess which parameter is the amount, and an amount it
  cannot resolve is a denial with reason `cost_unknown`, never an assumed zero.
  Until v0.3.3 an unresolved amount was read as zero, which made every euro cap
  inert for callers that did not set `cost_eur` by hand -- including the
  LangGraph tool wrapper in `examples/`. The parameter must also appear under
  `bounds.required`, since a parameter that may be absent is not a source of
  truth for money.
- **requires_step_up** — recorded on the policy today; enforcement of a
  second factor at approval time is a v0.4 item.

## Effects — aliasing-resistant governance

Policy binds to action *names*, but the same real-world effect is reachable
through many tools (`send_payment` vs a generic `http_request` to the bank).
Effects give the engine a second, name-independent binding:

```yaml
effects:                       # top-level: effect-level governance
  money.egress:
    min_tier: 3                # tier floor: any action carrying this label
                               # is at least propose-and-confirm
    caps:
      daily_rate: 20           # ONE budget shared by every carrier

policies:
  - action_type: billing.charge
    tier: 1
    compensating_command: billing.refund
    effects: [money.egress]    # declared label

  - action_type: net.http      # generic tool: effect depends on params
    tier: 1
    compensating_command: onedoor.noop
    param_effects:             # deterministic rules, no model calls
      - param: url
        pattern: "https://(bank|pay)\\.example\\.com/.*"
        add_effects: [money.egress]
```

Semantics: an action's effects are its declared labels plus every
`param_effects` match (full-match regex on the parameter's string form).
Effect caps are reserved in the same transaction as action caps — all or
nothing, race-free, shared across every carrier. Tier floors escalate with
reason `effect_floor`. Measured coverage of this deterministic layer (and the
honest residue it cannot see — encodings, redirectors, obfuscated shell):
`python -m experiments.aliasing_benchmark`.

## Reason codes you will see in decisions and the audit log

`passed` · `default_deny` · `tier_confirm` · `no_compensating_command` · `bounds` ·
`dry_run` · `cap_daily_rate` · `cap_eur_day` · `cap_eur_month` · `cost_unknown` ·
`kill_switch` · `observe` · `effect_floor` · `malformed`
