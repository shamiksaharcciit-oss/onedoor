# Design note: hash `evaluation_trace` into the row preimage (`/2` → `/3`)

Walks every item of R035 §1's consequence chain — the ruling that bumped
`/1` → `/2` for `approval_ref_status` — against this bump, then verdicts the four
build constraints below. **Verdict: build.** All four constraints hold, and the mechanism
R035 §1 put in place for exactly this case (the per-row `preimage_version` hint) needs
no new engineering — only the version bump itself.

## R035 §1, walked item by item

Quoting `docs/from_core/Core_to_Delivery_Response_035_2026-08-22.md` (verified,
`sha256(body) = 7e9e952...`), §1, against this bump:

> **"`approval_ref_status` must be hashed; your §2 argument is complete (flipping
> `expired` to `honored` is precisely the edit a chain exists to catch)."**

The same argument applies to `evaluation_trace_json`, more directly: it is not
adjacent evidence, it is the **stated justification** for the verdict's reason code —
"the verdict's reason must be checkable from the trace alone" is the standing MUST.
Editing a `fail` entry to `pass` after the fact — flipping `cap_value` to `caps: pass`
in a denied row's trace — would rewrite the *reason the row gives for itself* while
the reason code and the trace both still read as internally consistent, exactly the
edit a chain exists to catch. Unhashed, it was strictly weaker evidence than the
reason code sitting beside it; hashing it in closes that gap.

> **"The epic survey confirms the fold-in list: ND-015's `sig`/`key_id`/`alg` —
> EXCLUDED, by construction... ND-017's `anchor_ref` — EXCLUDED, necessarily..."**

Re-surveyed against the current schema (`PRAGMA table_info(actions_audit)`, 41
columns): `sig`, `key_id`, `alg` (ND-015) and `anchor_ref` (ND-017) are unchanged and
their exclusion reasons are unchanged — a signature still cannot precede the hash it
signs, and an anchor is still assigned after re-verification. `e_digest`/`i_digest`/
`t_digest`/`v_digest` (ND-017) are likewise unchanged: still computed *from* the row.
`preimage_version` remains excluded for the same self-authentication reason. **No
column needs reclassifying except `evaluation_trace_json` itself** — it is the only
column left in `EXCLUDED` rather than `FIELD_ORDER` from its own introduction, and it says so in its own
exclusion entry (`preimage.py`'s `EXCLUDED["evaluation_trace_json"]`).

> **"ND-050 is NOT pre-folded — its row shape is undesigned, and guessing it now to
> save a bump would be designing a ticket in a hurry inside another ticket."**

The direct analogue here: **`external_authorization` and `present_bound` are NOT
pre-folded into `/3` either**, for the identical reason. Their evidence
shape (a `mandate_status` column, a ratification reference, an audience-match
outcome — whatever step 3's own design settles on) does not exist yet at the point
this note is written; step 2 runs before step 3 in this same work order. Guessing
their columns now to save a future bump would be exactly the mistake R035 §1 named.
They get their own version (`/4`) when their own design is built and their columns
exist to survey.

> **"Add to `/2` a `preimage_version` hint column, EXCLUDED from the hash... a chain
> whose rows transition `/2 → /3` at a recorded point re-derives end to end... This
> removes the 'impossible after the first deployer enables chaining' cliff
> permanently: future columns get future versions on live chains, and today's bump
> is the last one that needs the everything-off window."**

This is the one already built, unused until now. `preimage_version` (migration
`0013`), `preimage.VERSION_1`/`VERSION_2`, `FIELD_ORDERS` keyed by version string,
`version_of(row)` reading the row's own hint, `values_from_row(row, version)` picking
the right field order, and `row_hash_of(row)` composing the two — every piece
`chain.py`'s `_walk()` needs to verify a row under *whatever version sealed it* is
already in place and already generic over the version string. **No code in `chain.py`,
`audit.py`, or `decision.py` needs to change for this bump.** The only edits are in
`preimage.py` itself (new constants, one new `FIELD_ORDER_V3` tuple, one dict entry,
one line removed from `EXCLUDED`) and in `docs/row-preimage.md` (the normative
document `FIELD_ORDER` must keep agreeing with, per
`test_the_document_and_the_module_declare_the_same_field_order`).

`docs/from_core/Core_to_Delivery_Response_035_2026-08-22.md` already names the exact
transition this bump performs as its own worked example: *"a ledger whose rows
transition `/2 → /3` at a recorded point re-derives end to end."* R035 §1 anticipated
this bump by name before there was a `/3` to bump to.

> **"Verify the transition case with a test — a chain crossing a version boundary
> re-derives end to end."**

Already done once, for `/1 → /2`:
`tests/guardrail/test_chain.py::test_a_chain_verifies_across_a_preimage_version_boundary`.
This bump adds the `/2 → /3` sibling, built the identical way (force-reseal an early
row under the older version within a chain whose later rows are natively sealed under
the new `CURRENT_VERSION`) — see "Tests" below.

## The four build constraints

**1. Old rows are never rewritten or rehashed; they still verify as `/2`.**

Holds structurally, not by discipline. `actions_audit` forbids `UPDATE`
(`actions_audit_no_update` trigger); nothing in this bump touches a stored row.
`version_of(row)` reads each row's own `preimage_version` hint (absent → `/1`,
present → whatever it names), and `row_hash_of(row)` looks up `FIELD_ORDERS[that
version]` — a `/2` row's hint still resolves to `FIELD_ORDER_V2`, which is unchanged
by adding `FIELD_ORDER_V3`. **Verdict: holds.**

**2. New rows are `/3`, with `evaluation_trace_json` in `FIELD_ORDER`, at a justified
position.**

`FIELD_ORDER_V3 = (*FIELD_ORDER_V2, "evaluation_trace_json")` — appended, row 31,
following the exact precedent `/1 → /2` set (`FIELD_ORDER_V2 = (*FIELD_ORDER_V1,
"approval_ref_status")`, also appended). `docs/row-preimage.md` states in §3:
"Order is fixed. Reordering is a new preimage version, not a refactor" — appending is
the only move this document permits without inventing a fifth reason to justify an
insertion point. `CURRENT_VERSION` becomes `VERSION_3`, so every new write
(`audit._stamp_chain`, already generic over `CURRENT_VERSION`) seals under it and
stamps the hint accordingly, with no change to `audit.py`. **Verdict: holds.**

**3. The chain check verifies a chain that changes from `/2` to `/3` partway through;
the switch point is recorded in the chain itself, not inferred from a date.**

`chain._walk()` calls `row_hash_of(full)` per row, and `row_hash_of` derives the
version from that row's *own* `preimage_version` column — never from `created_at`,
never from a global "chaining enabled at" timestamp. Two adjacent rows with different
hints already verify independently today (that is exactly what the existing `/1→/2`
test proves); nothing about that mechanism is `/2`-specific. **Verdict: holds**,
demonstrated by the new `/2 → /3` test alongside the existing `/1 → /2` one.

**4. The export states each row's preimage version, so a reader outside onedoor can
recompute any row's hash.**

Already true and already shipped: `preimage_version` is an ordinary column,
`onedoor/export.py`'s `export_rows` is generic over every column, and
`docs/EXPORT.md`'s field table already documents `preimage_version` ("Which
row-preimage version this row's hash was computed under, or `null`"). No change
needed here — the export was built generic enough that this constraint was satisfied
before this ticket existed. **Verdict: holds, already shipped.**

**All four hold. Building.**

## What changes

- `onedoor/guardrail/preimage.py`: `VERSION_3` constant, `CURRENT_VERSION =
  VERSION_3`, `FIELD_ORDER_V3` (appends `evaluation_trace_json`), `FIELD_ORDER =
  FIELD_ORDER_V3`, `FIELD_ORDERS[VERSION_3] = FIELD_ORDER_V3`,
  `evaluation_trace_json` removed from `EXCLUDED`.
- `docs/row-preimage.md`: title → `/3`; §3 gains row 31; §4 loses the
  `evaluation_trace_json` row; §7's version table gains a `/3` row and the "last bump
  that needs the everything-off window" sentence is corrected — `/2` was not, in
  fact, the last one; that claim aged out the moment a live chain needed a third
  version, which is precisely what the hint mechanism was built to allow.
- `tests/guardrail/test_chain.py`: the `/2 → /3` sibling of the existing `/1 → /2`
  transition test, a tamper test isolating `evaluation_trace_json` specifically (to
  prove it is now load-bearing, not merely present), and a direct byte-for-byte
  re-hash assertion on a simulated pre-bump `/2` row.
- `tests/guardrail/test_row_preimage.py`: unchanged in substance — every test in it
  is already generic over `FIELD_ORDER`/`EXCLUDED` rather than hardcoding a version,
  so it exercises `/3` automatically once `preimage.py` and the doc agree.

## Not done here, and why

`digests.py`'s four ND-017 receipt digests (`E`/`I`/`T`/`v`) are untouched.
`verdict()` does not read `evaluation_trace_json`, and this note does not add it: the
receipt digests are a separate, already-shipped forensic layer over the row (ND-017),
and this note asks specifically to hash the trace into the **row preimage**, not
to redesign what a receipt discloses. Whether a receipt should also attest to the
trace is a question for whoever next touches `docs/receipt-digests.md`, not answered
by silence here.

## Addendum: what a mandate ratification binds to

A live question about `mandate.core_digest` (request_id + action_type +
params_digest): should it instead bind to the `propose` row's own `/3` `row_hash` —
the exact sealed verdict record, rather than the logical inputs that produced it?
**Considered and declined: `core_digest` stays as built.**

Binding to `row_hash` would be strictly stronger — it ties a ratification to the
verdict as actually sealed (reason code, tier, trace, chain position), not merely to
the request that led to it, closing the (structurally unlikely, since every decide
mints a fresh `request_id`, but not structurally forbidden) case of two evaluations
of an identical logical request producing the same `core_digest` from different
verdicts. **Declined because of what it would cost**: `row_hash` is populated only
`if chaining_on(conn)` (`audit.py::append`) — binding to it would make mandate-layer
deferral **hard-depend on chaining being enabled**, and chaining is opt-in. The cost
would fall on every deployment that does not chain, which is not a cost mandate-layer
deferral should impose by itself.

**Reconsider if chaining becomes the default** — at that point the dependency this
note declines to take on stops being a cost most deployments would not have paid for
anyway.
