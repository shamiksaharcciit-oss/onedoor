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
    dry_run_until: 2026-09-01T00:00:00Z   # optional: dry-run until a timestamp
    compensating_command: payments.reverse # REQUIRED for tier 1 (loader refuses otherwise)
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
  ships in dry-run for two weeks.
- **compensating_command** — the reversibility rule. Must name another
  registered action type; the undo is submitted through the same pipeline,
  linked to its parent in the audit log. Tier-1 entries without one fail at
  load; an auto action that loses its reversal demotes to Tier 3 at runtime.
- **bounds** — validated for *every* tier before proposals are created, so
  approvers only ever see sane requests. `strict_params: true` rejects any
  parameter not mentioned in `numeric`/`enum`/`required`.
- **caps** — `daily_rate` counts executions (reserved at decide time,
  race-free); the euro caps apply to Tier 2 and are reserved the same way.
- **requires_step_up** — recorded on the policy today; enforcement of a
  second factor at approval time is a v0.4 item.

## Reason codes you will see in decisions and the audit log

`passed` · `default_deny` · `tier_confirm` · `no_compensating_command` · `bounds` ·
`dry_run` · `cap_daily_rate` · `cap_eur_day` · `cap_eur_month` ·
`kill_switch` · `observe`
