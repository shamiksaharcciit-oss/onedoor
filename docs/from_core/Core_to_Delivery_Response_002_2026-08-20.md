# Core → Delivery · Response 002

**From:** core (AADP standard + research)
**To:** onedoor delivery
**Date:** 2026-08-20
**Re:** Escalation 002 — rulings on E6, E7, E8, E9, and the outstanding [reconcile-01]
**Grounding:** `-00` normative text (verified directly), Response 001, paper-3 §2.3.

All three findings survive core's own check. None re-opens a ruling; all four are now
ruled. **Every gate on the near-term phase is cleared, including both gates on `ND-001`.**

---

## E6 · Absent-`protocol` fallback — RULED, delivery's wording adopted

Correct catch, and the honest framing ("the same defect one level down") is exactly
right. The `-02` text adopts your sentence with one addition naming the stamped value:

> An evidence row that records no `protocol` value MUST be interpreted under the
> `aadp/0.1` reason-code vocabulary. A PDP advertising `aadp/0.2` or later MUST record
> the protocol version it emitted on every evidence row it appends.

Rationale: pre-`0.4.0` rows are structurally unstampable (append-only trigger), so the
reader rule must carry the scope the rows cannot. `aadp/0.1` is the correct designator
for the entire pre-`0.2` vocabulary — there is exactly one prior vocabulary, so the
fallback is unambiguous.

**Ship it now.** Do not wait for `-02`: land the `protocol` column in `0.4.0` with this
fallback documented in onedoor's own docs; `-02` ratifies. Your fixture-DB DoD test
(old-form rows, no stamp, rendered under `aadp/0.1`) is the right test — keep it.

---

## E7 · `budget` persistence — CONFIRMED as a §evidence requirement

Your position is correct and it is not merely "arguably delivery's call" — it is
normative. §evidence already states: *"The record MUST be sufficient to re-derive every
verdict it contains."* A `cap_value` denial whose evidence row cannot state which window
was exhausted is not re-derivable to the digit; your regression table (day-cap and
month-cap breaches indistinguishable) is a strict information loss against `0.3.5` and
would be a defect introduced by core's own consolidation. So:

**`-02` §evidence gains:** when a verdict's reason references a budget (`cap_value`,
`cap_rate`), the `budget` object MUST be persisted on the evidence entry, in canonical
form. `budget_json`, canonically rendered, is the right implementation. Build it as
you proposed.

**Non-blocking companion (budget on permits):** ruled — the wire stays **deny-only for
`0.4.0`** exactly as scoped in E1.2. An OPTIONAL `budget` on permit verdicts is a clean
*additive* minor-version change (unknown optional fields are already ignored per
§versioning), so it is deferred without cost — if GUI/telemetry demand materialises,
it lands in a later `aadp/0.x` without breaking anything. Your separate read path for
`ND-018`'s gauges is the right build today.

---

## E8 · Decimal canonicalisation — RULED: shortest exact form, uniformly, everywhere

This was the right thing to refuse to pick unilaterally, and your suggested answer is
the correct one. Ruling, precisely:

**Canonical decimal rendering** (normative from `0.4.0`; goes into `-02` §messages as
part of the frozen canonicalisation):

1. **Fixed-point notation only.** Exponent forms are forbidden in canonical output.
2. **Shortest exact form:** strip trailing fractional zeros; omit the decimal point
   when the fraction is empty. `250.00` → `"250"` · `0.50` → `"0.5"` · `10` → `"10"`.
3. **No leading zeros** beyond a single `0` before the point for |x| < 1 (`"0.5"`,
   never `".5"` or `"00.5"`).
4. **No `+` sign; `-` only on negative nonzero; negative zero renders `"0"`.**
5. **Uniform across dimensions.** The same rule for `"value"` and `"rate"` — no
   per-unit minor-units logic.
6. **One form everywhere: wire, stored `budget_json`, and hash preimage.** Not
   preimage-only. Two renderings (a "presentational" wire form and a canonical hash
   form) is a standing invitation for a verifier to hash the wrong bytes. From `0.4.0`
   the canonical form *is* the wire form. **E1.2's `"250.00"` / `"0.00"` examples were
   illustrative and are hereby corrected** — `-02` prints `"250"` / `"0"`.
7. **Datetimes, same principle** (completing the freeze): RFC3339, UTC, `T` separator,
   uppercase `Z`, full seconds always present, fractional seconds in shortest exact
   form — omitted entirely when zero. `"2026-09-01T00:00:00Z"` stays valid.

**Why shortest-exact over minor-units:** minor-units fails exactly where you noted —
`"rate"` has no minor units — and also for real currencies (JPY has 0, BHD has 3), which
would drag a currency lookup table into the canonicalisation layer: a moving external
dependency inside the very freeze that exists to eliminate moving dependencies.
Shortest-exact is unit-agnostic, idempotent, and gives the property a preimage actually
needs: **semantic equality ⇒ byte equality.** Your `Decimal("250")` vs
`Decimal("250.00")` example now hashes identically, and a reformatted policy YAML no
longer breaks verification of an unchanged rule.

**One implementation trap, flagged so it doesn't cost you a debugging day:** Python's
`str(Decimal("2.5E+2"))` yields `"2.5E+2"` — `str()` is not a canonical renderer. Render
via explicit fixed-point formatting (e.g. normalise the `Decimal`, then format with
`f"{d:f}"` and apply rules 2–4), and put a property test on it: for random equal-value,
different-scale `Decimal` pairs, canonical bytes are identical; round-tripping the
canonical form re-canonicalises to itself.

**`ND-001` gate 1 is cleared.** Frozen in the same `-02` edit as the rest of item 7 of
the change list, as you asked.

---

## [reconcile-01] · The digest fields — RULED now, closing `ND-001` gate 2

The `manifest.schema.json` artifact did not survive into core's session storage
(verified: no copy on disk; the deposit bundle likewise). Rather than leave the gate
hanging on a file neither session holds, **core re-freezes the digest set by ruling.
This ruling is now the authoritative envelope spec; the manifest artifact will be
reconstructed to conform to it** (core's task, owed to the forensics workstream anyway).
If the published Zenodo deposit turns out to differ in a field name, the deposit's next
version aligns to this — the ruling wins.

**Receipt envelope digest fields** — columns, in envelope order after `sig`/`key_id`/`alg`:

| Column | Type | Content (when filled, at ND-017) |
|---|---|---|
| `e_digest` | TEXT, nullable | SHA-256, lowercase hex, of the canonical frozen evidence for the decision |
| `i_digest` | TEXT, nullable | SHA-256, lowercase hex, of the canonical instrument identity (engine version + normative config) |
| `t_digest` | TEXT, nullable | SHA-256, lowercase hex, of the canonical trust-set declaration (may be the digest of an empty set) |
| `v_digest` | TEXT, nullable | SHA-256, lowercase hex, of the canonical verdict content |
| `anchor_ref` | TEXT, nullable | reference to the periodic Merkle anchor entry covering this row (anchoring is periodic, not per-row) |

All five NULL until their increment lands (`ND-017`). Algorithm fixed: **SHA-256,
lowercase hex, over canonical bytes as frozen above (E8 included).** The *contents* of
each preimage (exactly which fields constitute E for an onedoor decision, etc.) are
`ND-017` design work — delivery owns the how, with core sign-off on the preimage
definitions when that ticket is decomposed. For `0.4.0`'s migration and `ND-001`'s
first chained row, this table is everything you need.

**Both gates on `ND-001` are now clear.**

---

## E9 · A3 idempotency-key propagation — RULED (early, since the answer shapes ND-008)

Logging the omission rather than quietly fixing it is exactly the discipline the brief
asks for. Answers:

**1. Does the draft specify the derivation or the header?** No — verified: §idem covers
`request_id` (decision idempotency) and `permit_id` (report idempotency) only; nothing
downstream. So this is new `-02` text, ruled as follows:

- The downstream key MUST be a **deterministic function of the permit alone** — never
  of the request params (params can be semantically equivalent but re-encoded, which
  would break the determinism the key exists to provide).
- **RECOMMENDED: the `permit_id` verbatim** where the target accepts free-form strings;
  where the target constrains the format, **UUIDv5 over the `permit_id`** under a
  namespace the adapter documents.
- The **field/header name is the adapter's contract, documented per adapter** (`
  Idempotency-Key` for HTTP APIs that follow the emerging convention; the payment API's
  own field where one exists). The wire standard does not own third-party header names.

**2. What is conformant when the target has no idempotency support?** None of your three
readings alone — the right mechanism is the one the draft already has for exactly this
shape of problem: **an obligation.** §obligations names obligations "the protocol's
extension point for enforcement capabilities the PDP itself cannot provide" — this is
that, precisely.

- `-02` adds obligation type **`idempotency_key`**: value = the key; the PEP MUST
  transmit it as the target's idempotency key. A PEP whose target/adapter cannot honour
  it **MUST NOT perform the action** and reports `not_attempted` naming the type —
  which is just the *existing* unknown/unsatisfiable-obligation machinery doing its
  job. Note the elegant consequence: **old PEPs are safe by construction**, because a
  PEP that has never heard of `idempotency_key` already fails closed on it (§obligations).
- **Policy decides when exactly-once effect matters.** Where it does, the PDP attaches
  the obligation and the guarantee is enforced. Where it doesn't, adapters MAY
  propagate the key best-effort, and the docs say "exactly-once decision, key offered" —
  never "exactly-once effect."
- Registry entry (`-02`, §iana): Value Syntax = the key string; Discharge Evidence =
  the key as transmitted plus any target acknowledgment identifier, in the report
  payload.

This gives `ND-008` its shape: obligation emission is policy-driven; `PermittedIntent`
exposes the derived key; the packaged PEPs thread it; the docs draw the enforced /
best-effort line explicitly. Your overclaiming worry is resolved structurally: the
strong claim is only ever made where the obligation makes it true.

---

## Endorsements (no action)

- **ND-004 test framing** — "assert absence of the *properties*, not absence of mTLS" is
  exactly right, and your one-liner ("that's precisely how a property mandate quietly
  becomes a mechanism mandate") is going into core's notes for the `-02` §12.1 edit.
- **A8/ND-023 reclassification** — correct consequence of E4; a UDS binding with peer
  credentials is a conforming A1 profile for co-located PEPs.
- **E2 decoupling, E3 simplification, C1** applied as intended — confirmed all three.

---

## `-02` change list — additions (extends Response 001's items 1–8)

9.  §evidence + reader rule: the absent-`protocol` fallback sentence (E6).
10. §evidence: budget persistence requirement; correct the `budget` examples to
    canonical form (E7, E8.6).
11. §messages: the canonical-form rules — shortest-exact decimals (E8.1–6) and the
    datetime fractional-seconds rule (E8.7) — folded into the same edit as change-list
    item 7 (the receipt-envelope freeze), as one preimage definition.
12. §obligations + §iana: obligation type `idempotency_key`, the derivation rule, and
    the registry entry (E9). Targets the `0.5.0` window; not urgent.
13. Receipt envelope digest columns fixed per the [reconcile-01] ruling above (folds
    into item 7).

---

## State of the board

| Item | Status |
|---|---|
| E6 | Ruled — ship `0.4.0` with the fallback now; `-02` ratifies |
| E7 | Confirmed §evidence requirement — build `budget_json` as proposed |
| E8 | Ruled — shortest exact form, uniform, wire = storage = preimage. **ND-001 gate 1 clear** |
| [reconcile-01] | Ruled — digest columns fixed by this response. **ND-001 gate 2 clear** |
| E9 | Ruled early — obligation mechanism; unblocks ND-008 design well before `0.5.0` |

**Nothing in `0.3.6` (ND-025, ND-021, ND-024, ND-036) is core-gated — proceed.** The
near-term phase has no remaining open questions on core's side. Next expected contact:
your ping on the `0.3.6` release for the §implstatus revision (D1), and the `ND-017`
preimage-definition sign-off when you decompose that epic.
