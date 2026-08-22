# `ND-001` — hash-chained audit entries · decomposition

**Ticket:** `ND-001`, `0.4.x`, opens the crypto epic (`ND-001` → `ND-015` → `ND-017`).
**Baseline:** `0.4.1` @ `77167c3`, published; 437 passed / 9 skipped, four gates green.
**GO:** R030 §4 — decomposition first, `ND-010` behind it, `ND-009` in parallel.
**Settled surface to build to, cited not rediscovered:** the frozen envelope
(`CONFORMANCE.md` §6), the **ruled genesis sentinel** (R016: 64 ASCII zeros), **E8** at
every digest, **E10** at `params_json`/`payload_json`, **X-8** at any anchor, **N2** on
group commit, and the append-only triggers re-verified after any migration that touches
the table.

---

## 1. What is already done, and it is more than it looks

**No migration is needed for the chain columns.** `prev_hash`, `seq` and `row_hash`
landed in migration `0007`, dark, precisely so P1 would not re-migrate an append-only
table. Checked in a live store, not assumed: all three exist and are NULL on every row.
`0.4.0`'s decision to land the whole envelope at once pays for itself here.

**The serialization point the chain needs already exists.** A hash chain requires that
two appends cannot interleave between reading the tip and writing the next row.
`db.tx()` is `BEGIN IMMEDIATE`, which takes the write lock at entry — chosen for
cap check-and-reserve, and it happens to be exactly what chaining needs. Every one of
the nine `audit.append` sites is inside one; verified by walking each call site's
enclosing block rather than by trusting the pattern.

**The verifier already exists and already reports this check.**
`onedoor/guardrail/receipt.py::_check_chain` returns `ABSENT — "chain not yet in
operation (ND-001)"` today. `ND-001` flips that one function from `absent` to
`verified`/`failed`, and **the viewer needs no change at all**: it renders whatever the
checker says. That is the single-verification rule paying out one ticket after it was
written.

## 2. The preimage — the part that must be right first, because it is frozen forever

Every later verifier, `ND-015`'s signature and `ND-017`'s `E` digest all address these
bytes. Get it wrong and the fix is a re-hash of an append-only table, which is to say
there is no fix.

**Two disciplines in one preimage (E10).** Generated columns are canonicalised — E8
decimals, RFC3339 datetimes, sorted-key NFC JSON. `params_json` and `payload_json` are
**received** bytes and enter **verbatim**, byte for byte, never re-serialised. The
preimage is therefore *not* "canonicalise the row"; it is "canonicalise what we made,
and pass through what we were given", with the boundary declared field by field.

**`id` cannot be in the preimage.** The triggers forbid `UPDATE`, so `row_hash` must be
computed *before* the `INSERT`, and `id` is assigned *by* the insert. This is not a
detail to discover during implementation — it decides the ordinal.

### The ordinal question, and an X-14 hazard to resolve deliberately

`seq` is ours to assign, so the chain's ordinal is `seq`, and `seq` is in the preimage.
That leaves two orderings over the same table — `id` and `seq` — and **X-14 says two
fields that must agree are a disagreement waiting for its first bug.** They are not
collapsible: `id` must exist (it is the primary key and every `parent_id` points at
one), and `seq` must exist (the envelope is frozen and the preimage needs an ordinal
that predates the insert).

**Proposed resolution, for core's confirmation:** `seq` is *authoritative for the
chain* and `id` is a storage detail. A verifier walks `seq`. Their agreement is
asserted by a test rather than assumed, and a disagreement is a **verification
failure**, never a silent re-order — because the two disagreeing is exactly what a
tampered store looks like. A `UNIQUE` index on `seq` makes the database refuse the
ambiguity rather than leaving it to the walker (migration `0012`, index only).

### NULL versus empty, inside the preimage — R015 arriving where it bites hardest

`detail` is `""` on most rows and NULL on none today; `error`, `payload_json`,
`budget_json`, `opaque_class` and eight envelope columns are routinely NULL. **If the
preimage renders NULL as the empty string, a row that produced nothing and a row that
produced an empty thing hash identically** — R015's null-versus-empty collapse, welded
into an append-only table forever.

So the preimage needs a declared, distinct encoding for absent versus empty, and it
needs it before the first chained row, not after. **This is the decomposition's
question for core** (§7).

## 3. Group commit (N2) — decided, not deferred

`append_buffered` queues rows in memory; `flush` writes them with one `executemany`
inside its own `tx`. A chain is sequential; an `executemany` is not.

**Decision: chain inside `flush`, before the `executemany`.** Refusing group commit
when chaining is on would be the easier choice and the wrong one — it would make a
performance feature and an integrity feature mutually exclusive, and every deployer who
wanted both would quietly turn off the one that is harder to notice missing. The
buffered rows' preimages do not depend on chain fields, so `flush` can stitch the chain
in row order inside the transaction it already opens: read the tip once, compute each
row's `prev_hash`/`seq`/`row_hash` in order, then insert.

**Both paths tested against each other — and the first formulation of that test was
wrong, which is recorded here rather than quietly fixed.** This section originally said
the two paths must produce **identical `row_hash` values** for the same sequence of
actions. They cannot, and the test asserting it failed against a correct
implementation.

Group commit *defers result rows*, so the same four actions land in a different **row
order**: immediate writes `intent, result, intent, result`; buffered writes
`intent, intent, intent, result, result, result`. `seq` and `prev_hash` are in the
preimage, so different positions mean different hashes — and `parent_id` joins them,
because a result row names its intent by row id and ids follow write order. That is
what group commit *is*. Measured, not argued: `test_group_commit_reorders_the_ledger`
asserts both orders explicitly.

The invariant that **does** hold is the one N2's decision actually needs: *the preimage
does not depend on which path wrote the row.* Same content at the same position hashes
the same either way. If that failed, a store's receipts would depend on a performance
setting and two operators running identical actions would hold different evidence —
the real risk group commit introduced. Row order differing is fine; the function
differing is not.

## 4. Genesis and the mixed archive — a fourth outcome, again

Existing rows have no hash and cannot be given one (triggers forbid `UPDATE`). The
chain therefore starts at a **genesis row** carrying `prev_hash` = 64 ASCII zeros
(R016's ruled sentinel: an affirmative in-band statement that no predecessor exists,
leaving NULL exactly one meaning) and recording the `id` of the last unchained row.

**Verification of a mixed archive must state which prefix is unchained**, and the
vocabulary for that is already settled and already rendered:

| Region | Outcome | Meaning |
|---|---|---|
| rows before genesis | **absent** | never chained; `ND-001` had not run |
| rows from genesis, chain intact | **verified** | each row hashes to its successor's `prev_hash` |
| a row whose hash does not match | **failed** | localised to that row (DoD's tamper test) |
| chain fields partly written | **unverifiable** | a chain that ran and did not finish |

Reporting the whole log as "verified" because the chained part verifies would be the
two-outcome collapse this programme keeps catching — and reporting it as "failed"
because an old prefix is unchained would punish the archive for its own history,
exactly as R030 §2 said of an unfootered artifact. The same ruling, one layer down.

## 5. Work order

- **C1 — the preimage.** Defined once, documented as a table of columns with their
  discipline (canonical / verbatim / absent-encoding), frozen. Property-tested over
  **generated** rows: equal-value/different-spelling decimals, key-order permutations,
  NULL-versus-empty pairs, and the round trip `hash(canon(row)) == hash(canon(canon(row)))`.
  **A second implementation reads the preimage spec and reproduces the digests** — the
  only test that proves the definition is a definition rather than a description of one
  function's behaviour.
- **C2 — the chain writer.** `seq`/`prev_hash`/`row_hash` computed inside the existing
  `BEGIN IMMEDIATE`, both paths, plus migration `0012` (a `UNIQUE` index on `seq`, and
  the append-only triggers re-verified after it — a migration that touches this table
  is a migration that can drop a trigger).
- **C3 — genesis.** The sentinel row, the last-unchained-id record, and the
  enable-chaining path being an audited, once-only event.
- **C4 — `verify_chain()`**, landing as `receipt.py::_check_chain`'s new body plus a
  whole-log walker. Four outcomes, prefix stated honestly. The viewer changes not at
  all, which is the acceptance test for the single-verification rule.
- **C5 — the tamper test** (DoD): mutate a row by direct SQLite write with triggers
  bypassed, assert `verify_chain()` **localises the break to that row** rather than
  reporting a broken log. Both directions: an untampered log verifies.

## 6. What this ticket does NOT do

`ND-015`'s signature, `ND-017`'s four digests and any anchoring. **X-8 is noted now
because it binds the next ticket, not this one:** anchor only what you have
re-verified, so `ND-017` may not anchor a chain whose verification it has not run.
Concurrency beyond SQLite's single-writer model is `ND-019`'s (Postgres), and a chain
under multi-writer linearizability is a different design — flagged so it is not
discovered there.

## 7. The question this decomposition surfaces

**How does the preimage distinguish an absent column from an empty one?**

Not a style question. `budget_json` NULL means *no budget was owed*; `budget_json` `""`
would mean *a budget was produced and it was empty*. Under R015 those are different
facts, and once a row is chained the distinction is frozen into a digest that a third
party will recompute years later. Three shapes delivery can see:

1. **A type tag per field** — `n` for NULL, `s:` before a string — so absent and empty
   are unambiguously different byte sequences.
2. **A sentinel that cannot occur in the data** — clean until a value legitimately
   contains it, which for `params_json` (arbitrary received bytes) is a matter of time.
3. **Length-prefixed fields** — `-1` for absent, `0` for empty. Unambiguous, and the
   one that survives a field whose contents are attacker-chosen.

Delivery leans to **(3)**, because `params_json` is *received* data and the preimage
must stay unambiguous even when a caller is actively trying to make two different rows
hash the same. But this is the preimage, it is frozen forever, and `ND-017`'s `E`
digest inherits it — **so it is core's to rule, and delivery is not starting C1 without
that ruling.** Everything else in the work order is unblocked.
