# The coverage map's derivation — normative

**Status:** normative for `onedoor/coverage-citation/1`.
**Purpose:** a third party holding a coverage citation must be able to reproduce every
row on the map **without asking this store**, and without running the engine.

R049 §5 made this document a requirement rather than a courtesy, and attached a test to
it: *if it cannot be written clearly enough for a second implementation, the derivation
is not as pure as the ruling assumes, and that finding comes back to the board.* It was
written, and §6 records what writing it exposed.

---

## 1. Why this is a derivation and not a receipt

A backtest gets a receipt because **its result cannot be re-derived without running the
engine** — replaying traffic is the instrument. A coverage map's result *can* be
re-derived: it is a pure function of two values that already have addresses.

```
coverage_map = f(policy_snapshot, ledger_range)
```

So minting a `coverage_digest` would be a **second address for facts that already have
one** — forbidden at the preimage (R040) and sustained at the ratification preview
(R045). **The citation pair is the receipt.**

## 2. The citation

```json
{"schema": "onedoor/coverage-citation/1",
 "version_hash": "<64 hex>" | null,
 "range": {"state": "cited" | "uncitable" | "empty",
           "first_seq": <int|null>, "last_seq": <int|null>,
           "row_hash_at_last_seq": "<64 hex>|null", "rows": <int>}}
```

`version_hash` names the policy snapshot in `policy_versions`, whose `snapshot_json` is
the exact input. `null` means the map was built over a **candidate** rather than the set
in force, and a candidate has no `version_hash` — that is what ratification produces.

`range.state` is three-valued and the three do not collapse:

- **`cited`** — a sealed span exists; `row_hash_at_last_seq` pins it.
- **`uncitable`** — rows exist and none is chained. The counts are real and **cannot be
  checked by a third party**. Stated, never quietly rendered as a plain count.
- **`empty`** — no decisions. Every observed-side column is a non-measurement, not a zero.

## 3. Inputs, exactly

1. **`policies`** and **`effect_policies`**, as carried in `policy_versions.snapshot_json`
   for `version_hash` (see [row-preimage.md](row-preimage.md) for the snapshot's canonical
   form and `policy_loader.SNAPSHOT_SCHEMA` for which renderer produced it).
2. **`DISTINCT action_type` from `actions_audit`** over the cited range.

Nothing else. In particular the map reads **no** `reason_code`, no verdict, and no
timestamp: it asks *what arrived*, not *what happened to it*.

## 4. Derived sets

```
declared_actions  = { p.action_type              for p in policies }
observed_actions  = { distinct action_type       in the ledger range }

named_by_rules    = { e -> [p.action_type ...] } for every e in p.effects
                    UNION  every e in r.add_effects for r in p.param_effects
declared_effects  = { ep.effect                  for ep in effect_policies }

exercised_effects = { e  for p in policies
                         if p.action_type in observed_actions
                         for e in p.effects }
```

## 5. The four states

**Action rows**, over `declared_actions ∪ observed_actions`:

| condition | state |
|---|---|
| `a ∈ declared_actions` | `covered` |
| `a ∈ observed_actions` and `a ∉ declared_actions` | `uncovered_observed` |

**Effect rows**, over `named_by_rules.keys() ∪ declared_effects`:

| condition | state |
|---|---|
| `e ∉ declared_effects` | `declared_inert` |
| `e ∈ declared_effects` and `e ∉ exercised_effects` | `unobserved` |
| otherwise | `covered` |

### What `declared_inert` means at decision time

`decision.py` resolves effect policies as:

```python
effect_policies = [ep for e in effects if (ep := store.get_effect(conn, e)) is not None]
```

An effect a rule **labels** with no `effect_policies` row behind it is **silently
dropped**: no tier floor, no effect caps. Measured on `0.5.0` — the same request returns
`PERMITTED, effective_tier 1` with the label alone and `proposed, effective_tier 3` once
the effect policy exists.

That is why `declared_inert` outranks every other state in `PROMINENCE`: it is a **silent
permit** inside a rule its author believes is governing, while `uncovered_observed` is a
**loud denial** the engine already handles safely. **Rank by what a state does at
decision time, not by how alarming its name sounds** (R049 §3).

## 6. What this derivation does not measure — and one impurity it exposed

**`actions_audit` records `action_type` but not the effects that resolved.** So
`exercised_effects` is **derived, not recorded**: an effect counts as exercised when an
observed action type is declared *by the policy set being mapped* to carry it.

That is **today's rules applied to past traffic**. A row decided under an earlier
`policy_version` may have carried different effects, and this derivation cannot see that.
A second implementation will reproduce the map exactly — the function is pure — but both
implementations inherit the same limitation, so it is stated on every rendering rather
than left in this file.

**This is the finding R049 §5 asked for if the document could not be written cleanly.**
The derivation *is* pure over its declared inputs, so the ruling holds and the map stays
a view that cites. But its inputs are weaker than they look: `exercised_effects` is a
statement about the current policy set, not a historical record, and no citation can make
it one. Making it a measurement would require the ledger to record resolved effects per
row — a new hashed column, a preimage version, and a migration. **Delivery is not
proposing that here**; it is recorded so the board decides whether the gap matters.

**Unobserved-and-undeclared action types are not rows.** That set is unbounded, and a row
cannot be drawn for something the map has never heard of. It is the map's footer instead:
*this map measures what is declared and what arrived over the cited range* — principle 4
turned on the coverage map itself.
