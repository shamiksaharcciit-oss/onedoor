# `ND-052` / **S1** — the backtest engine · decomposition

**Epic:** `ND-052`, the Policy Studio. Pre-launch, demo-grade (R036).
**Ticket:** S1, **first in the normative build order** — the deterministic spine before
the model, and launch pressure is why that order exists rather than a reason to skip it.
**Baseline:** `04cccf7`; 592 passed / 9 skipped, four gates green, CI green both jobs.
**GO:** R042 §5.

**Settled before a line was written, and not reopened here:**

- **A backtest writes nothing to the decision ledger. Ever** (R042 §3) — not a decision
  row, not a marker, not a breadcrumb. `actions_audit` is the enforcer's record; the
  Studio is a proposer, and constitution principle 1 does not bend for evidence's sake.
- **It borrows the ledger's witness instead of adding to it**: a **backtest receipt**
  that binds to real data by quoting what only the real ledger can produce — the sealed
  chain. *A backtest proves it saw real data by citation, not by writing — the ledger
  vouches for the backtest, never the reverse.*
- **`ledger_provenance: live | fixture`**, hashed with the rest, and the label survives
  into every rendering (R042 §4).
- **The Studio never gates the launch** (R036), and **S6 demos only real, receipted,
  limit-stated output**.

---

## 1. What already exists, checked rather than assumed

S1 is the flourish that needs no model, and it is cheap for a specific reason: **every
part of it is already built and tested.**

| S1 needs | Exists as |
|---|---|
| Replay a policy without executing | `Policy` `dry_run`, and `decide_and_reserve` returning a terminal `ActionResult` |
| A candidate policy separate from the active one | `policy_loader.upsert` writes to a store; a **second store** is the isolation |
| The real actions to replay | `actions_audit`'s frozen `params_json` — received bytes, verbatim |
| Proof the range is real | `row_hash`, `seq`, and `anchoring.anchor_for` |
| A canonical digest for the receipt | the vendored `digest_obj`, and `docs/receipt-digests.md`'s discipline |
| A fixture ledger that is mechanically real | `chain.enable` + the engine; nothing special needed |

So S1 is **composition, not construction** — which is exactly what R036 meant by *the
model lands on a proven spine*.

## 2. Finding one: replay cannot use the live store, and dry-run is not the isolation

The obvious implementation — load the candidate policy, replay, read the verdicts —
**writes to `actions_audit` on every replayed action**, because `decide_and_reserve`
audits every decision it makes. That is precisely what R042 §3 forbids, and `dry_run`
does not help: a dry-run *is* a decision and it writes a `dry_run` row.

Worse, it would **reserve budget**: `decide_and_reserve` is check-and-reserve, so a
replay of yesterday's 214 actions would consume today's caps.

**The isolation is a separate store**, not a flag. S1 opens a scratch database, loads
the candidate policy into it, replays each historical request against *that*, and reads
the verdicts from *its* audit log — which is then discarded. The real ledger is opened
**read-only** and never written.

This is worth stating in the ticket because the natural first implementation is wrong in
a way that passes every obvious test: the backtest would work, produce right answers, and
quietly pollute the enforcer's record and the day's budget.

## 3. Finding two: replaying a request requires fields the ledger does not store

`ND-010` already established this, and it lands again here. `actions_audit` holds
`params_json`, `action_type`, `source`, `created_at`, `request_id` — and **not**
`rationale`, `cost_eur` or `session_id`.

`cost_eur` is the one that bites: it drives cap accounting, so a replay that defaults it
to zero **silently under-reports every cap denial the candidate policy would have
produced** — a backtest that says "3 sent to approval" when the truth is 30, in the
direction of reassurance.

Two honest options, and §6 asks which:

1. **Replay only what the ledger can reconstruct**, and declare the limitation on the
   receipt: cap-driven divergence is **not covered** by a backtest (constitution
   principle 4, non-coverage stated). Honest, and it removes the most persuasive column
   of the demo.
2. **Derive `cost_eur` from `cost_param`** where the policy declares one — the amount is
   in `params_json`, which is exactly where the live engine reads it from
   (`policy.cost_param`). Faithful where a `cost_param` exists, and **explicitly
   uncovered where it does not**.

Delivery leans to **(2) with (1)'s disclosure attached**: it is faithful by the same
mechanism the engine uses rather than by a guess, and where it cannot be faithful the
receipt says so rather than averaging.

## 4. The backtest receipt

Per R042 §3, and canonical throughout — same discipline as `docs/receipt-digests.md`:

```json
{"schema": "onedoor/backtest/1",
 "policy_digest": "<sha256 of the candidate policy's canonical snapshot>",
 "ledger_provenance": "live" | "fixture",
 "range": {"first_seq": A, "last_seq": B, "row_hash_at_last_seq": "<64 hex>"},
 "anchor": {…the anchor object…} | null,
 "instrument": {"engine": "<version>",
                "preimage_version": "onedoor/row-preimage/2",
                "snapshot_schema": "onedoor/policy-snapshot/2"},
 "coverage": {"replayed": N, "skipped": {"<reason>": N}},
 "divergence": {"allowed": N, "to_approval": N, "denied": N,
                "flips": {"<from>→<to>": N}, "tier_changes": {…}},
 "backtest_digest": "<sha256 of this object with the field absent>"}
```

**`row_hash_at_last_seq` is the citation that does the work.** Quoting it means a forged
"we tested against production" claim requires forging the chain — the thing the epic
just made hard. The anchor, when one covers the range, raises that to *independently*
hard.

`coverage.skipped` is principle 4 in the receipt itself: an action the backtest could
not replay is **counted and named**, never dropped.

**Determinism:** same run twice ⇒ same `backtest_digest`. That makes re-runs comparable
for free, and it is a testable property rather than an aspiration — asserted by running
one twice.

## 5. Work order

- **B1** — the scratch-store replay harness: candidate policy in, historical requests
  replayed, real ledger opened read-only, **an assertion that `actions_audit` gained no
  rows and no cap counter moved** (§2's finding, as a test rather than a promise).
- **B2** — the receipt: shape, canonical digest, determinism, migration `0016`
  (append-only, Studio's own), plus the two-file export under ND-017's discipline.
- **B3** — the fixture ledger: built by the real engine, chained, sealable, anchorable,
  **and declaring `fixture` on its face**. Doubles as demo content and sabotage bed.
- **B4** — the divergence summary and `coverage.skipped`.
- **B5** — the label's survival: a test that `fixture` reaches **every** rendering, and
  a sabotage that strips it and fails exactly the labelling tests. *A fixture-backed
  number presented without its label is the overclaim this programme exists to make
  impossible.*

## 6. The questions this decomposition surfaces

**1. How does a backtest obtain `cost_eur`?** (§3.) Delivery proposes deriving it from
`policy.cost_param` where declared and declaring the gap where not. The alternative —
defaulting to zero — is a *default that looks like a fact*, the phrase R032 already put
in the record, and here it would understate cap denials in the direction of reassurance.

**2. Does `ledger_provenance` have a third value?** A store that *has* a sealed chain
but whose rows are unchained before genesis is neither cleanly `live` nor `fixture`.
Delivery proposes **`live` with `coverage.skipped` counting the unchained prefix** — the
range is what was cited, and a range that cannot be cited is not replayed. Raised because
the alternative is a third label, and two labels that must be told apart by a footnote
are worse than a counted skip.

**3. Is the fixture ledger shipped in the wheel?** It is demo content, sabotage bed and
test fixture at once. In the package it travels with the product and can be pointed at
on day one; outside it, the demo needs a build step. Delivery leans **in the package**,
under `onedoor/studio/_fixture/`, generated by a script and byte-pinned the way
`docs/oneview/` is — but it adds weight to every install, so it is worth one line of
confirmation rather than a discovery at packaging time.

B1's harness shape is unblocked. B2's receipt waits on Q2, B3 on Q3, and B4's cap
columns on Q1.
