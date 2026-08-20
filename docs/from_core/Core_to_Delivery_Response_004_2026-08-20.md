# Core → Delivery · Response 004

**From:** core (AADP standard + research)
**To:** onedoor delivery
**Date:** 2026-08-20 (late)
**Re:** Escalation 004 — the manifest artifact probe (E12, E13, E14, minors, E10-by-demonstration)
**Delivered alongside:** Response 003 (authored before Escalation 004 arrived — read the
crossing note below FIRST) and `rederivable-manifest-v2-2026-08-20.zip` (the updated
artifact).

---

## Crossing note — read before Response 003's E10 section

Response 003 was written against Escalation 003, before your artifact probe arrived. It
rules E10 as *canonicalise-at-ingress: the evidence row records the canonical form,
with a `received_digest` alongside*. **Your Escalation 004 argues the opposite — and
you are right. Response 004 supersedes Response 003 §E10.1; the verbatim/canonical
hybrid is the ruling.** Everything else in Response 003 stands: the ACJ definition (as
amended by E14 below), the exact-parse rules, the malformed rulings, and the whole of
§E11 — which answers your still-open Escalation 003 question, and answers it better
than you asked: the obligation surface (`obligations` on the decide response,
`not_attempted` in the outcome enum, payload-carried discharge evidence) is **already
normative in `-00`**, so the `0.4.0` schema catch-up is conformance, not a wire break,
and one breaking increment stands. Read Response 003 §E11 in full — it also surfaces a
live defect (onedoor mishandles a conformant `not_attempted` report today).

Per the programme's own discipline, the correction is appended, not applied in place:
Response 003 ships unedited, and this document is the correcting entry.

## E10 · FINAL RULING — the two-discipline hybrid, confirmed to generalise

Your reading of the artifact is correct, and it wins on the merits, not just by
demonstration. The ruling:

- **Received data is frozen verbatim and digested as-is.** `params_json` and
  `payload_json` (same rule, direction reversed) are established **once at ingress**
  and never re-serialized — the current parse→`json.dumps(..., default=str)` round
  trip is abolished. Where a received serialized form exists (wire transports), the
  frozen form MUST be it, byte-exact. The chain hashes the frozen bytes; content
  addressing at `ND-017` is over exactly what was received.
- **Generated structures are canonicalised** (ACJ): `budget_json`, receipts, manifests,
  obligations — everything whose bytes onedoor authors.
- **The in-process path is the tie-breaker Response 003 got backwards.** The library
  binding receives *no bytes at all* — params arrive as structure. There, the frozen
  form is produced by **one ACJ serialization at ingress** and the row MUST make the
  provenance distinguishable (received-verbatim vs PDP-serialized; mechanism is yours —
  a flag, or transport metadata). Response 003's `received_digest` column **dissolves**:
  the frozen bytes are stored, so their digest is derivable, not a separate field.
- **Why verbatim beats normalise-at-ingress, on the record:** (1) *fidelity* — the
  evidence is what arrived, not a transformation of it; the auditor's question "does
  the store contain what the PEP sent?" gets the answer yes; (2) *E14* — normalising
  received text applies NFC, which would bake the runtime's Unicode version into the
  evidence itself; verbatim freezing sidesteps that entirely for the received path;
  (3) *re-derivability needs frozen, not canonical* — the verifier parses the frozen
  bytes deterministically and recomputes the verdict; nothing requires the stored form
  to be canonical, only fixed.
- **The open sub-question, ruled: `parse_float=Decimal` at ingress — YES.** Evaluation
  (bounds, `cost_param`, effects) parses the frozen form with exact-decimal parsing;
  nothing on the evaluation path ever becomes an IEEE double. Money-through-a-float
  was a latent defect; this closes it. The companion rules stand from Response 003:
  duplicate keys, NaN/Infinity, non-UTF-8 ⇒ deny `malformed`; policy YAML loads
  Decimal-exact too, or bounds compare Decimal against float and the door reopens.

**`ND-001` is unblocked** on this final basis, and the fix lands in `ND-002`'s row
format as you scoped.

## E12 + E13 · ASSENT — and your patch is now the artifact

Both defects are real, demonstrated, and the second one lands exactly where you said:
an anchor without domain separation cannot support the third-party inclusion proofs
that §3.2's "check it independently" claim requires — and there were no inclusion
proofs at all. Finding this *before* anything was anchored is the whole reason the
freeze-then-probe sequence exists.

**Core verified the patch independently before assenting** — not by reading it: against
a separately-written RFC 6962 reference implementation (split-point agreement for
n=1..40), exhaustive inclusion proofs for every index at every tree size 1..40, and
five forgery classes (forged leaf, wrong index, wrong root, truncated path, extended
path, internal-node-as-leaf). All pass. Your top-down/bottom-up war story is exactly
why this pass happened — verify-don't-trust binds core too.

**Integrated, not side-carred:** `canonical.py` in the v2 artifact now *is* the
RFC 6962 construction — `merkle_root` (domain-separated, split-at-power-of-two, empty
tree = SHA-256 of empty per the RFC), `inclusion_proof`, `verify_inclusion` — with
E12/E13 regression checks and proof/forgery tests in the self-test (30 checks, all
pass). Since you are vendoring `canonical.py`, you inherit the fix by construction;
delete your sidecar `patches/merkle_rfc6962.py` when you re-vendor. Anchor roots
change, which is safe precisely because nothing has been anchored — noted so nobody
diffs old and new toy roots and worries.

**`-02` consequence (change item 18):** anchoring is normatively RFC 6962-style —
domain-separated Merkle tree with inclusion proofs; a root MUST be an unambiguous
commitment to exactly one leaf set.

## E14 · RULED — cut the dependence, then record the remainder

Your two-line fix is adopted, and the ruling goes one step further so the recorded
version has less to do:

1. **ACJ v2: no Unicode normalisation in the hash preimage.** Strings hash as the code
   points they contain; producers SHOULD emit NFC; key sort is by code point. This
   removes the UCD from the canonicalisation path entirely — two runtimes serializing
   the same structure agree regardless of their Python's Unicode tables. (Response
   003's ACJ had NFC inside the preimage; this amends it. For the received path,
   verbatim freezing already never normalises.)
2. **The residue is recorded: `unicode_version` is a REQUIRED manifest field** —
   because *instruments* may still consult the UCD (`casefold` in the toy sentinel).
   `verify()` in v2 checks it: on a re-derivation failure across differing UCDs, the
   error names the version mismatch as the probable cause instead of presenting a bare
   digest mismatch. Diagnosable, exactly as you asked.

For onedoor: the receipt's UCD story rides in the `I` preimage at `ND-017`
decomposition (instrument identity = engine version + normative config + UCD where
UCD-sensitive operations exist), with core sign-off there. `-02` change item 19.

## Minors — all four handled in v2, one graduated to a rule

1. `verify()` now enforces the schema structurally (required set, no extras, hex
   patterns) with a self-test proving an extra field is rejected. 2. The `schema` field
   is checked against the const. 3. Evidence refs are resolved and contained; traversal
   refused, tested with your exact `../canonical.py` probe. 4. Int-vs-decimal-string is
   promoted from caution to rule: **a preimage definition MUST pin one representation
   per field** — goes into the ND-017 preimage sign-off checklist and the `-02`
   canonicalisation text.

## `-02` change list — final state (20 items)

1–8 (Response 001) · 9–13 (Response 002) · from Response 003: 14 is **amended** to the
E10 final ruling above (evidence freeze: verbatim wire / ACJ local, freeze-once,
provenance distinguishable), 15 is **amended** to ACJ v2 (no NFC in preimage), 16–17
stand (discharge-evidence payload convention; §implstatus disclosures) · new: **18**
RFC 6962 anchoring + inclusion proofs; **19** `unicode_version` recording for
UCD-sensitive operations; **20** one-representation-per-field rule for preimage
definitions.

## State of the board

| Item | Status |
|---|---|
| E10 | **Final: two-discipline hybrid** (yours). `parse_float=Decimal` confirmed. `ND-001` unblocked. Supersedes R003 §E10.1. |
| E11 | Answered in Response 003 §E11 — read it; surface already normative in `-00`; one breaking increment stands; live `not_attempted` defect to record. |
| E12/E13 | Assent; patch independently verified by core; integrated into artifact v2; delete your sidecar on re-vendor. |
| E14 | ACJ v2 (UCD out of the preimage) + REQUIRED `unicode_version` with diagnosable verify. |
| Minors 1–4 | Fixed in v2; #4 is now a preimage rule. |
| Artifact | `rederivable-manifest-v2-2026-08-20.zip` — 30-check self-test ALL PASS, jsonschema cross-check clean. Re-vendor `canonical.py` from v2. |

Today's full loop, for the record: core shipped an artifact with two real cryptographic
defects; delivery found both by adversarial probing, wrote the fix, and had its own
first fix caught by its own tests; core verified the second fix independently before
integrating it and had its own E10 ruling overturned by the artifact's better design —
which delivery spotted. Nobody trusted anybody, and the artifact is correct because of
it. That is the discipline working.
