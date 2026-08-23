# `ND-052` / **S2** — the ratification ceremony · decomposition

**Epic:** `ND-052`, the Policy Studio. Pre-launch, demo-grade (R036).
**Ticket:** S2, second in the normative build order, on the spine S1 just proved.
**Baseline:** `6859d71` plus S1's follow-ups; 620 passed / 9 skipped, four gates green.
**GO:** R044 §4.

---

## 1. What is settled before this ticket starts

**The ceremony cites `record_snapshot`'s machinery; it never re-derives it.** Flagged by
delivery, endorsed by R043 §4 and again by R044 §4, and it is the R040 rule arriving in
the Studio — the same rule that keeps `ND-015`'s `sig` and `ND-017`'s `E` citing
`docs/row-preimage.md` rather than growing their own.

Concretely, and checked rather than assumed:

| The ceremony needs | It already exists as |
|---|---|
| The canonical form of a policy set | `policy_loader._normalized_snapshot(conn)` |
| The hash that becomes the active version | `record_snapshot(conn)` → `version_hash` |
| Attribution for a hash that changes | `SNAPSHOT_SCHEMA` (`onedoor/policy-snapshot/2`, R019) |
| The archive of what each version contained | `policy_versions`, append-only by trigger |
| The pointer to what is active | `policy_current` |

S2 writes **none** of that. It reads it, shows it, and calls it.

Two more things it inherits rather than decides:

- **The candidate is not a version.** S1 gave a candidate an identity —
  `backtest.policy_digest`, a digest over the candidate's canonical models — precisely
  because a proposal has not been ratified into a store. **Ratification is the act that
  turns the first into the second**, and that is the whole ticket.
- **Constitution principle 5**: the derivation gets a receipt. The ratification receipt
  is the second Studio artifact, after S1's backtest receipt, and it should look like it.

## 2. The ceremony, as a sequence

1. **Diff** the candidate against the active policy set — rule by rule, in the canonical
   form, so the diff is of *meaning* and not of spelling.
2. **Show the hash it would become**, computed by the same function that will compute it
   for real. Not a preview of a number; *the* number.
3. **Ratify**: write the candidate through `policy_loader.upsert`, which calls
   `record_snapshot`, which produces `version_hash` and stamps `policy_current`.
4. **Issue the ratification receipt** — who ratified, what changed, from which hash to
   which, and the backtest receipt that informed it, cited by digest.

Step 2 is where the demo lives — *the hash shown becoming the new `version_hash`* — and
it is also the step most likely to be faked by a lesser implementation. Which is §3.

## 3. Finding one: showing a hash before ratifying it is a promise the store must keep

The ceremony shows the hash the candidate *will* have. There are two ways to get it:

1. **Compute it the same way `record_snapshot` does, over the candidate**, and show that.
2. Ratify into a scratch store, read the resulting `version_hash`, show that, then ratify
   for real.

(1) is a **second derivation of a value that already has one owner** — exactly what R040
forbade at the preimage and R043/R044 just endorsed forbidding here. It would work, and
it would drift the first time `_normalized_snapshot` changed.

(2) is the S1 pattern reused: a scratch store, discarded. It is slower and it is
**right**, because the number shown is produced by the function that will produce the
real one.

But (2) has a trap worth stating: `_normalized_snapshot` renders the **whole policy
table**, so a scratch store must be seeded with the *complete* resulting policy set — the
candidate merged over the active set — not just the changed rules. Ratifying two rules
into an empty scratch store yields the hash of a two-rule deployment, which is not the
hash anything will have. **The preview must be computed over the same content the
ratification will produce, or it is a different number wearing the right label.**

## 4. Finding two: the ceremony must be refusable, and `version_hash` is not enough to refuse on

*"Diff against the active policy"* presumes the active set has not moved since the
candidate was drafted and backtested. If it has — another operator ratified in between —
the diff on screen is stale, and the operator signs something other than what they read.

`policy_current.version_hash` is exactly the guard: the ceremony records the hash it
diffed **from**, and the ratification refuses if the active hash has changed since.
Compare-and-swap, the same shape as `approvals.cas_approve` and for the same reason —
**a lost race must not silently write.**

This is not hypothetical for a demo-grade feature: the Studio is a UI, and a UI has a
gap between reading and clicking.

## 5. The ratification receipt

Canonical, digested, and citing rather than restating — the S1 shape:

```json
{"schema": "onedoor/ratification/1",
 "from_version": "<64 hex>" | null,
 "to_version": "<64 hex>",
 "snapshot_schema": "onedoor/policy-snapshot/2",
 "candidate_digest": "<the S1 policy_digest>",
 "backtest_digest": "<the backtest that informed this>" | null,
 "changes": {"added": [...], "removed": [...], "modified": [...]},
 "ratified_by": "<session>", "ratified_at": "<RFC3339 UTC>",
 "ratification_digest": "<sha256 of this object with the field absent>"}
```

`from_version: null` is the first ratification on a fresh store — **absent, not empty**,
and distinguishable from a store whose previous version happened to be unrecorded.

`backtest_digest` is nullable **and its absence is meaningful**: ratifying without a
backtest is allowed and is worth being able to see. Principle 4 again — the gap is
stated, not prevented.

## 6. Work order

- **T1** — the diff: canonical, meaning-not-spelling, over the merged resulting set.
- **T2** — the preview via a scratch store (§3), with a test that the previewed hash
  **equals** the hash ratification then produces. That equality is the ticket's central
  claim and the demo's whole credibility.
- **T3** — the compare-and-swap ratification (§4) and its lost-race test.
- **T4** — the receipt, migration `0017`, append-only, and the two-file export.
- **T5** — the viewer line: a ratification rendered with its from/to hashes. As with
  every ticket since `ND-051`, **adding a check should need no page change** — and if it
  needs a new *outcome*, that is the one legitimate reason to touch the renderer.

## 7. The questions this decomposition surfaces

**1. Who is `ratified_by`?** This is `ND-009`'s principal question arriving in the
Studio, and it has the same answer available: onedoor has no authenticated per-caller
identity, so a session string is caller-supplied. Delivery proposes recording
`approvals.decided_by_session`'s existing shape — a **declared** session, honestly
labelled as unauthenticated — rather than a field that looks like an identity.
`principal_mismatch` is already reserved-and-unemitted for exactly this reason; the
ceremony should not imply more than the engine can check.

**2. Does a ratification require a backtest?** The constitution says non-coverage is
stated, never silent — which argues for *allowed but visible* (nullable
`backtest_digest`). But a ratification ceremony whose whole pitch is *"here is what this
will do"* might reasonably refuse to proceed without one. Delivery leans **allowed and
visible**: refusing would make the Studio unusable for the first policy on a fresh store,
where there is nothing to backtest against, and R043 already ruled that case gets the
fixture rather than a block.

**3. Should ratification be blocked while the kill switch is engaged?** The kill switch
stops *actions*; ratifying a policy is not an action the engine governs. But changing the
rules during an incident is exactly when someone would want it blocked — and exactly when
a legitimate operator might need to tighten them. Delivery has no strong view and will
not guess: this is a governance question, not an implementation one.

T1 and T2 are unblocked. T3 is unblocked. T4's receipt waits on Q1 and Q2; T5 follows T4.
