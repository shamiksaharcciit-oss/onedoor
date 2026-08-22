# `ND-010` — rebuild pending intents from the audit log · decomposition

**Ticket:** `ND-010`, `0.4.x`, behind `ND-001`. `ND-009` runs in parallel.
**Baseline:** `15fa578`; 470 passed / 9 skipped, four gates green, CI green both jobs.
**GO:** R032 §3.
**Core's binding constraints, cited not rediscovered:** reconstructed intents are **the
same durable rows** (`exec_intent` + `cap_reservations`), never new ones — no new
evidence identity, no budget re-reservation (§invariants #9, §idem). And R032 §3: the
rebuilt state **carries provenance to the rows it derives from**, and a rebuild that
cannot find its evidence **surfaces the gap rather than synthesising an intent**.

---

## 1. The promise, and what is actually missing

`service/app.py` keeps `self.pending: dict[int, PermittedIntent]` in memory and its own
docstring says `0.4` will rebuild from the `exec_intent` row instead. Today a restart
between decide and report strands every in-flight permit: the reservation is held, the
deadline runs, and the reclaimer eventually voids budget for an action that may well
have happened.

The durable evidence is already sufficient **for settlement**: `cap_reservations` holds
`intent_audit_id`, `request_id`, `deadline_utc`, `deltas_json` and `status`. Settling
does not need to re-derive what was reserved — the reservation *is* the record of it.
That is what makes this ticket possible without recomputing cost.

## 2. Finding one: `PermittedIntent` cannot be faithfully rebuilt, and must not pretend

`PermittedIntent` carries `request: ActionRequest`. Three of that model's fields are
**not stored anywhere in `actions_audit`** — checked against a live schema, not assumed:

| Field | Stored? | What a naive rebuild would do |
|---|---|---|
| `rationale` | **no** | pass `""` — inventing a reason the caller never gave |
| `cost_eur` | **no** | pass `Decimal(0)` — asserting a free action |
| `session_id` | **no** | pass `None` — indistinguishable from "there wasn't one" |

`cost_eur = 0` is the dangerous one. It is a *default that looks like a fact*, and any
future code that reads it off a rebuilt intent would read zero and be wrong. This is
precisely R032 §3's line: **surface the gap, do not synthesise.**

`parent_audit_id` is the exception that proves the rule — it *is* recoverable, because
`undo_of` stores it for exactly the source (`UNDO`) that uses it.

**Proposed shape:** a rebuilt permit is a **distinct type** — `RebuiltIntent` — that
carries what the store holds plus **provenance to the rows it came from** (the
`exec_intent` id and the `cap_reservations` row), and that **does not carry an
`ActionRequest` at all**. It cannot then be mistaken for one, and no caller can read a
synthesised zero off it. `report_result` takes `PermittedIntent | RebuiltIntent`.

The alternative — storing the three fields so the rebuild is faithful — is **rejected
for a reason bigger than this ticket**, in §4.

## 3. Finding two: a naive rebuild silently corrupts E10 provenance

`report_result` passes `intent.request` to `audit.append`, which calls
`frozen_params(request)`: it returns `params_raw` verbatim when the ingress received
bytes, and otherwise re-serialises `params`. A rebuilt request would have
`params_raw = None`, because only a live ingress sets it.

So the result row written after a restart would record
`params_provenance = "serialized"` for a request that arrived as **received bytes** —
the evidence quietly changing its story about where it came from, at exactly the moment
the system is least observed. Not a crash, not a test failure: a wrong label on a
receipt.

**The fix already has a precedent in this file.** `append_expiry` copies
`intent_row["params_json"]` verbatim and *inherits* the intent row's provenance rather
than claiming one of its own. A rebuilt intent does the same: the stored bytes and the
stored provenance travel together, and neither is recomputed.

## 4. The constraint `ND-001` just imposed on every future schema change

**Do not add columns to `actions_audit` to make the rebuild easier.** The preimage is
frozen (`docs/row-preimage.md`, R032 §2's single normative source). Every column is
either in `FIELD_ORDER` — where adding one is a **new preimage version**, `/2`, and
every existing digest was computed under `/1` — or in `EXCLUDED` with a reason, where
it is a field an attacker can edit without breaking the chain.

Neither is a price worth paying for a `rationale` string. This is the first ticket to
meet that constraint and it will not be the last, so it is written down here rather
than rediscovered: **after `ND-001`, `actions_audit` is a schema you extend only with a
reason that survives that trade.**

## 5. Work order

- **R1** — `RebuiltIntent`: the type, its provenance fields, and the loader that reads
  an `exec_intent` row plus its `cap_reservations` row. Absent evidence returns the
  absence, never a default.
- **R2** — `report_result` accepts a rebuilt permit, inheriting stored bytes and stored
  provenance (§3), writing the same durable rows and re-reserving nothing.
- **R3** — the service rebuilds on startup instead of holding memory: `state.pending`
  becomes a query, and `/v1/report` looks the intent up rather than popping a dict.
- **R4** — the three-outcome report at recovery time (§6).
- **R5** — the DoD restart test, plus the provenance regression from §3 asserted
  directly.

## 6. Recovery has the same four outcomes as everything else

R032 §3 calls it "the three-outcome rule at recovery time". Applied here:

| Outcome | Condition |
|---|---|
| **rebuilt** | the `exec_intent` row and a `held` reservation are both present and agree |
| **absent** | no such intent — it was never permitted, or already reported. Not an error |
| **unverifiable** | the intent row exists and its reservation does not, or the reservation is `held` with no intent — evidence that disagrees with itself |
| **failed** | the row exists and is unreadable: `params_json` that will not parse, a `deltas_json` that will not load |

**`unverifiable` is the one that matters**, and it is a state this store can genuinely
reach: `cap_reservations` has no foreign key to `actions_audit`. A rebuild that treated
a missing reservation as "nothing to settle" would silently discard a held budget; one
that treated a missing intent as "nothing to do" would leave a reservation held
forever. Both are the two-outcome collapse, and both lose money quietly.

## 7. The question this decomposition surfaces

**When a rebuilt intent is reported, whose `created_at` does the result row carry?**

The stored intent row has the *original* request's `created_at`. The result is being
reported now, possibly days later after a restart. `audit._row_values` stamps
`created_at` from the `now` passed in, so the result row would carry the report time —
which is correct and is what happens today. But the rebuilt intent's own `request`
substitute also has a `created_at`, and if anything ever reads it expecting "when this
row was written" it will get "when the action was first asked for".

Two timestamps, one name, different meanings — X-14's shape, and the ledger is
permanent. Delivery's proposal: `RebuiltIntent` names them apart —
`requested_at` (from the intent row) and no `created_at` at all, so the result row's
stamp can only come from `now`. **Cheap to settle now, and a rename after rows exist is
not a rename.** Core's call; R1 does not start without it, R2–R5 are unblocked.
