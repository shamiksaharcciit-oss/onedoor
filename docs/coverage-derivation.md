# The coverage map's derivation — normative

**Status:** normative for `onedoor/coverage-citation/1`.
**Purpose:** a third party holding a coverage citation must be able to reproduce every
row on the map **without asking this store**, and without running the engine.

R049 §5 made this document a requirement rather than a courtesy, and attached a test to
it: *if it cannot be written clearly enough for a second implementation, the derivation
is not as pure as the ruling assumes, and that finding comes back to the board.* It was
written; §6 records the finding it exposed **and the ruling that closed it** (R050 §4).

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

would_exercise    = { e  for p in policies
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
| `e ∈ declared_effects` and `e ∉ would_exercise` | `unreached` |
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

## 6. What this derivation projects, and what it does not recall — **ruled**

**`would_exercise` is a projection, and its name now says so** (R050 §4). It was
`exercised_effects`, which claimed history the computation cannot deliver; the ruling was
a rename rather than a migration, and this section records the answer rather than the
deliberation that produced it.

`actions_audit` records `action_type` but **not** the effects that resolved. So
`would_exercise` means exactly: *under the policy set being mapped, the observed traffic
would reach these effects.*

**For a candidate this is the correct question, not a compromise.** The Studio's purpose
is to ask *if I ratify this, what does it reach?* — and a projection is the only kind of
answer that question has. For the **active** set the same number invited a historical
reading it could not support, and the name is what closed that.

**The historical question belongs to a different product.** Establishing which effects
actually resolved for a past row means:

1. take that row's own `policy_version`,
2. load the snapshot in force at the time,
3. resolve effects against **that row's frozen params** —

because `param_effects` makes effects param-dependent, so **no join and no column short
of the engine's own resolution settles it.** That is the engine, run over history,
against sealed inputs. **That is a backtest.**

So there is **no new hashed column, no `onedoor/row-preimage/3`, and no migration.** The
gap is not in the ledger; it is the boundary between two products, and this finding
confirms the boundary rather than challenging it: **the map projects and cites; the
backtest measures and receipts.** A deployer who needs *"which effects did this range
actually exercise"* runs a backtest over that range — the map does not pretend, and
`PROJECTION_NOTE` says so on every rendering, naming the backtest as the thing that does
answer it.

**Action types neither declared nor observed are not rows.** That set is unbounded, and a row
cannot be drawn for something the map has never heard of. It is the map's footer instead:
*this map measures what is declared and what arrived over the cited range* — principle 4
turned on the coverage map itself.
