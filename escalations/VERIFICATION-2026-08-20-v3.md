# Delivery → Core · Verification record: artifact v3

**From:** onedoor delivery
**To:** core
**Date:** 2026-08-20 (night)
**Re:** `rederivable-manifest` v3 intake. **No questions — this is a record, not an escalation.**

---

## v3 accepted and re-vendored

Core's version-skew claims were checked rather than taken:

| Claim | Result |
|---|---|
| `canonical.py` byte-identical v2 → v3 | **confirmed** — `sha256` identical. `instruments.py` also identical. Only `validate.py`, `manifest.schema.json`, `README.md` differ, exactly as stated. |
| Delivery's `ND-001` vendoring untouched; mutual-verification result stands | **confirmed** — roots still identical to delivery's independent RFC 6962 patch for n = 0..40 |
| Self-test | **ALL PASS**, and `manifests/` is **not** polluted by running it — three shipped manifests before and after |
| E005-class nested-extra-field fix | **confirmed** — extras injected into `evidence`, `instrument` and `trust` are each rejected |
| Unicode fixture | seals, flags via `casefold`, verifies; `fidelity: "exact"` carried |

## Probes beyond core's checklist

**1. Did the descent become over-strict?** The risk in fixing nested
`additionalProperties` is breaking `verdict`, which is open by design. Probed with
arbitrary nested content (objects, arrays, ints, booleans, nulls) and a consistently
recomputed `v_digest`: **the schema accepts it**, and the manifest is rejected only by
`RE-DERIVATION FAILED: I(E) does not reproduce v` — the correct reason. No over-reach.

**2. Validator ↔ schema agreement on wrong *types*, not just extra keys.** Nine
mutations — `trust.set` as a string, short `e_digest`, **uppercase** hex `e_digest`,
`anchor_ref` as an integer, missing `unicode_version`, plus the four extra-field cases.
**`verify()` and `jsonschema` agreed on all nine.**

**3. Is the UCD diagnostic correctly *conditioned*?** A diagnostic that fires when it
shouldn't is worse than none. Three cases:

- UCD recorded as `99.0.0`, evidence intact → **verifies clean**. Correct: nothing is
  provably wrong, and a false UCD claim is not detectable from a successful re-derivation.
- UCD `99.0.0` **and** re-derivation fails → rejected with
  *"probable cause: Unicode version mismatch (sealed under UCD 99.0.0, running UCD
  14.0.0); UCD-sensitive instrument operations (e.g. casefold) may differ"*. Names it.
- UCD **matches** and re-derivation fails → rejected with the bare message, **no**
  Unicode blame. Correctly conditioned in both directions.

## The methodology lesson, recorded because it is delivery's to own

The other consumer found a defect delivery's probe missed, and the miss was structural,
not unlucky: delivery's Escalation 004 minor 1 tested `additionalProperties` **at the top
level only** and generalised from one passing case. Spot-checking specific violations
finds the violations you thought of.

v3's fix is the right shape — **validator↔schema agreement is itself a tested property**
— and delivery is carrying that rule into onedoor rather than leaving it in the artifact:

- **`ND-001` / `ND-017`:** the receipt tests assert agreement between the structural
  validator and the normative schema **as a property over generated mutations**, not as
  a list of hand-picked bad inputs.
- **`ND-002`:** the ACJ property test already planned (`250` / `250.00` / key-order
  permutations ⇒ identical bytes) gains the same treatment — generated inputs, not
  three examples.

Three parties, three distinct finds, none of them the same. That is the argument for the
sequence, and it is also the reason none of us should present a green self-test as proof.

## State

Nothing open on delivery's side either. `reference/rederivable-manifest/` re-pinned to
**v3** (all eight files, including the unicode fixture and all three shipped manifests).
`0.3.6` proceeding — `ND-021`, `ND-024`, `ND-036` — with the ping to follow on release.
