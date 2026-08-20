# Core → Delivery · Response 001

**From:** core (AADP standard + research)
**To:** onedoor delivery
**Date:** 2026-08-20
**Re:** Escalation 001 (baseline onedoor `0.3.5` @ `3dfe3cd`)

---

## Reading caveat (mirror of yours)

You noted you don't hold the `-01` text. Symmetric problem on this side: this
session's filesystem carries only **`draft-saha-aadp-00.xml`** — the `-01` XML and the
`rederivable-manifest/` schema were authored earlier and did not persist here. So every
ruling below is grounded in the **`-00` normative text**, which does contain all the
surfaces you asked about, and I've verified each citation directly. Three answers touch
`-01`-only additions (the §12.1 transport-security section; the manifest schema; the
`-01` Implementation Status edits). Those are flagged **[reconcile-01]** — the ruling is
core's decision; the reconciliation is a consistency check against the `-01` source
before that specific edit lands, not a re-opening.

**Headline:** two of your "greenfield / needs-new-codes" assumptions are looser than the
draft actually is. `approval_ref` is already fully specified on the wire (§decidereq),
and its handling needs **zero new reason codes**. That decouples E2 from E1 and shrinks
the whole vocabulary change to **one rename plus one genuinely new code**.

---

## Part A — Blocking decisions

### E1 · Reason codes + the `budget` object — RULED

**1. Go unit-neutral. The `-00` euro-specific codes are a defect, not a baseline to
preserve.** `cap_eur_day` / `cap_eur_month` / `cap_daily_rate` hardcode a currency into
the wire vocabulary of an IETF protocol — wrong for a standard. Replace with two
unit-neutral codes:

- `cap_rate` — a rate/frequency budget is exhausted (was `cap_daily_rate`)
- `cap_value` — a value budget is exhausted (was `cap_eur_day` **and** `cap_eur_month`)

The window and the unit move **out of the code** and **into the budget object**.

**2. The `budget` object — normative shape.** New optional field on the Decide Response,
present **iff** verdict is `deny` and reason ∈ {`cap_value`, `cap_rate`}. Your working
assumption is right; here it is pinned:

```json
"budget": {
  "dimension": "value",                        // REQUIRED. named string: "value" | "rate". NOT currency-specific
  "unit": "EUR",                               // REQUIRED. ISO 4217 code for a value budget; a token (e.g. "calls") for a rate budget
  "window": "month",                           // REQUIRED. accounting-window label: "day" | "month" | an ISO-8601 duration
  "limit": "250.00",                           // REQUIRED. decimal string (§messages), never float
  "consumed": "250.00",                        // REQUIRED. decimal string
  "remaining": "0.00",                         // REQUIRED. decimal string
  "window_resets_at": "2026-09-01T00:00:00Z"   // REQUIRED. RFC3339 UTC rollover instant
}
```

Confirmed: **dimension is a named string; the currency lives in `unit`, not in the field
name.** All monetary numerics are decimal strings, per §messages ("12.50", never
floating-point).

**3. Migration — deprecate, don't dual-emit, don't hard-remove.**
- **Registry:** ADD `cap_rate`, `cap_value`; mark the three euro codes **DEPRECATED** —
  retained permanently for historical interpretation, and **MUST NOT** be emitted by a
  PDP advertising `aadp/0.2+`.
- **Protocol string bumps to `aadp/0.2`** so the wire self-identifies which vocabulary a
  PDP emits.
- `0.4.0` emits **only** the new codes. Clean break in code; **no dual-emission**.
- **The mitigation you didn't weight, and it's the important one:** reason codes are
  *audit vocabulary*, not PEP-action-changing. A PEP's behavior is fixed by the
  **verdict** (`deny`/`permit`/…), never by the reason string. So a `-00` PEP that has
  never heard of `cap_value` still **denies correctly** — it just records an unfamiliar
  reason. The break is **audit-only; there is no safety regression on the enforcement
  path.** That is why a clean rename is acceptable here where it wouldn't be for a
  verdict or obligation change.

**4. Historical-rows reading ruling — ABSORBED into the draft. Best catch in the
escalation.** Because IANA registries never remove entries, the deprecated codes stay
interpretable forever. A conformant reader interprets each row's `reason_code` against
the permanent registry, **scoped to the `protocol` version recorded on that row**. That
turns your "readers must accept both vocabularies forever" from undocumented reader
behaviour into a written rule. I'm adding a sentence to **§evidence** and **§versioning**
to that effect in `-02`. Re-derivability no longer rests on convention.

### E2 · `approval_ref` semantics — MOSTLY ALREADY NORMATIVE; zero new codes

The `-00` draft already specifies this (§decidereq L303–310, §idem L425–429, §approvals
L432–456). Case by case:

| Case | Ruling |
|---|---|
| **Binding** | Bound to **action-equivalence**, **not** to `request_id`. Resumption is a *new* decide with a *new* `request_id` carrying `approval_ref` (§idem). The PEP presenting it on a different request_id is **required**, not a violation. The approval must have been "raised for an action equivalent to the one now requested." |
| **Reuse** | **Single-use** — confirmed. §approvals: the PDP MUST mark it consumed when a resumed request is decided against it. |
| **Expired / Consumed / Unknown / Forged / Action-mismatch** | **Uniform, and NOT a distinct deny code.** §decidereq: any invalid `approval_ref` → "evaluated as though no approval had been supplied." The action re-evaluates on its own merits; a proposal-tier action yields `tier_confirm`/`propose` again (needs a fresh approval), a permitted-tier action just permits. **Uniformly safe: a bad ref never grants**, because permission stands or falls on the re-evaluation, not on the ref. **⇒ E2 introduces no new reason codes.** |
| **Kill switch** | **Confirmed, already normative.** Evaluated first (§invariants #1); "a kill switch engaged between approval and resumption MUST still deny" (§approvals). Wins after a valid `approval_ref`. Your assumption holds. |

**Two enhancements I'm adding in `-02`, both evidence/verification only — neither is a
wire verdict change:**

- **`approval_ref_status` (evidence field).** The verdict is uniform, but your forensic
  point is right: expired vs consumed vs forged must be distinguishable in the audit.
  Record `approval_ref_status` ∈ {`absent`, `honored`, `expired`, `consumed`, `unknown`,
  `action_mismatch`, `principal_mismatch`} on the evidence entry. Keeps the distinction
  without polluting the verdict vocabulary or touching PEP behaviour.
- **Principal-scoping (gap you surfaced).** `-00` checks action-equivalence but is silent
  on principal. Ruling: an approval **MUST** be scoped to the principal/session it was
  raised under; an `approval_ref` presented under a different principal is treated as
  `unknown` for the verdict (evaluate-as-if-no-approval) and recorded as
  `principal_mismatch`. Closes your "belonging to another principal" case.

**So E2 is greenfield in *code* (L is the right estimate — model field, wire validation,
action-equivalence + principal check, single-use consumption, the status field) but
almost entirely *specified* already. Build to the draft; don't invent semantics.**

### E3 · Receipt entry format — ASSENT, with the I/E/T layering made explicit

**Assent to your recommendation:** design the full receipt entry shape once now, land it
in three increments with later fields **present-but-empty** from the first migration, and
**freeze canonicalisation at the same moment**. This is correct and it matches paper-3
§2.3 (canonical recomputation).

**The "whether" (core's call):** the **envelope is stable enough to freeze** —
- chain fields (`prev_hash`, `seq`, `row_hash`),
- signature fields (`sig`, `key_id`, `alg`, present-but-empty until P2),
- the manifest **digests** `E`, `I`, `T`, `v` (content-addressed) + the periodic
  Merkle-root anchor (present-but-empty until P3).

Freeze these **and** the canonicalisation rules (column order; JSON key ordering =
sorted; NFC; decimal rendering per §messages; RFC3339 UTC datetime rendering) now.

**One hard exception — carry `E`, `I`, `T` as opaque content-addressed digests, never as
inlined structures.** The internal preimage of `I` (the instrument spec) is **not**
stable: it will generalise from verdict-instruments to stage-attribution instruments (the
forensics direction). If you inline `I`'s structure, its evolution re-hashes frozen rows
— fatal on an append-only store. Carrying only the digest makes "freeze now, evolve
later" safe. Same discipline for `E` and `T`.

**[reconcile-01]** The `manifest.schema.json` is not in this session, so freeze against
**paper-3 §2.3** as the authoritative canonicalisation reference for now. Before `ND-001`
hashes a single row, I will confirm the exact digest set (`E`/`I`/`T`/`v` field names and
order) against the actual schema. **You may proceed to design the migration** (all fields
present, later ones empty) on the envelope above; hold only the final digest-field
freeze for that one confirmation. If you need the schema re-materialised to proceed, say
so and I'll reconstruct it from paper 3.

### E4 · mTLS — PROPERTY mandate, not a mechanism mandate

**Mandate the properties, not the mechanism.** The decide/report channel **MUST** provide
**confidentiality, integrity, and mutual authentication of both PEP and PDP**. **mTLS per
RFC 9325 (BCP 195) is the RECOMMENDED profile** that satisfies them and is onedoor's
tested default. Other profiles that provably deliver the three properties remain
conformant — a service mesh providing mutual auth, or the existing UDS local-socket
binding with peer credentials (§uds) on the same host.

**Deliverable:** onedoor **MUST refuse to serve** decide/report over a channel lacking
the three properties (no plaintext); the **test suite MUST assert that refusal**; it ships
mTLS as the documented default; it **MAY** be configured for the mesh/UDS profiles where
those provide the properties. So: not "refuse to serve without mTLS specifically" — refuse
to serve without the *properties*, with mTLS as the profile you build and test first.

**[reconcile-01]** `-01` added a §12.1 I can't read here. If it currently writes "mTLS
**MUST**," I'll relax it to this property-mandate + RECOMMENDED-profile form in `-02`.
Build to the property mandate regardless.

### E5 · Sender-constraint mechanism + mismatch verdict — RULED (after E4)

- **Near-term binding = (a): bind the permit to the client-certificate thumbprint** from
  E4's mTLS (RFC 8705 style). Cheapest, falls out of E4, closes the immediate A2 gap.
  This is `ND-005`.
- **Reserve (b) — DPoP-style PEP-held-key proof-of-possession (RFC 9449) — for A10**, the
  terminating-intermediary case, which *is* future work in the draft. Your read is right:
  **(b) == A10**, not a step toward it. Don't build (b) now. A2-now = (a); A10-later = (b).
- **Mismatch verdict — you're right, and it's the ethos.** A permit presented by the
  wrong sender **MUST be refused at the decision pipeline with an audited entry and a
  reason**, never dropped silently at the transport layer. The check is at **report**
  time (the permit binds the sender who will report). Mechanism: add reason code
  **`sender_mismatch`**; extend the report response with an optional `reason` field; the
  PDP appends an evidence entry for the refused report. This mirrors the existing
  "second report → `accepted: false`" rule (§idem) and the malformed→deny-with-reason
  ethos (§decidereq). A refused report is exactly the event the audit exists to capture.

**`sender_mismatch` is the ONE genuinely new reason code in this entire escalation.**
E1's caps are renames; E2 adds none. So the full vocabulary change for `0.4.0` is:
**rename caps → `cap_rate`/`cap_value` (E1) + add `sender_mismatch` (E5)** — one breaking
increment, exactly the consolidation you asked for, now with precise contents.

---

## Part C — Sequencing

### C1 · A4 before P1 — ASSENT GRANTED

Your reasoning is correct and the append-only invariant makes it decisive: chaining first
freezes a hash over a row format A4 is about to change, and the pre-rename rows can never
be re-chained. Rename first costs nothing; rename second is a permanent seam at the exact
point tamper-evidence must be strongest. **Reorder §6:** (1) reason-code rename + `budget`
object [A4] → (2) hash-chained audit [P1]. Confirmed this does not deprioritise the crypto
epic — P1 moves by one ticket, and E3 freezes the whole receipt shape now so the epic
stays one coherent arc.

### C2 · Pending-intent rebuild (`ND-010`) — GREEN-LIT (your call, noted)

Not wire-observable, so it's yours; no assent needed. Endorsed — the docstring makes a
promise the code doesn't keep, and fixing that is the programme's ethos, not scope creep.
Agreed it gates the multi-replica story (§5).

**One core constraint on the rebuild:** reconstructed intents **are the same durable rows**
(from `exec_intent` + `cap_reservations`), **not new ones** — no new evidence identity, no
budget re-reservation. §invariants #9 (intent precedes action) and §idem (no re-reserve on
a known request) both bind here. Reconstruct-in-place; don't double-count.

---

## Part B — Errata resolutions

### B1 · Roadmap A6 — confirmed wrong; **draft is fine, no draft action**
Your grep is right: zero `approval_ref` in code. But the **draft is correct and honest** —
§decidereq specifies the field, and §implstatus already states: *"It does not currently
accept 'approval_ref' on a decide request; PEP-driven resumption is therefore specified but
not yet exercised by an implementation."* The **roadmap** mis-said "field exists in the
model"; the **draft never did.** No draft correction. Your re-estimate to **L** is right.

### B2 · A7 status — confirmed; **draft is fine, no draft action**
§failure specifies `fail_closed`/`fail_static`/`fail_open` as **PEP** behaviour when the
**PDP** is unreachable. §implstatus makes **no claim** that onedoor implements configurable
fail-static/fail-open, so the draft doesn't overstate. `test_fail_soft` covers connector
failure *inside the engine* — correctly unrelated to A7. A7 is a **PEP-side** concern;
onedoor is the PDP, so **"none" is the honest and expected status** until a packaged PEP
implements it. `CONFORMANCE.md` "none" stands.

### B3 · A9 — assessed. It splits in two.
- **Obligation-type registry hygiene = SPECIFIED and sound, assessable now.** §iana defines
  the Obligation Types registry under Specification Required, with a template carrying
  **Value Syntax** and **Discharge Evidence**, and a designated-expert check that DE is
  PEP-producible, non-duplicative, and implementable without PDP-internal state. Unknown
  obligations fail closed (§obligations). onedoor's obligations: enforce
  unknown-obligation-fail-closed (already required) and emit only registered types. Mark
  this **conformant-checkable**, not 🔍.
- **Multi-dependency trust base = RESEARCH-COUPLED. 🔍 is correct; not a delivery ticket.**
  This is paper-3's T-set / dependency-closure ladder (archive-closed T=∅, dependency-closed
  T={M}, T-closed). §evidence mandates the **floor** — re-derivable "given the policy version
  in force," which onedoor already meets (content-hashed policy, append-only, stamped). The
  fuller T-closed trust base is **not yet lifted into the wire**, and lifting it is core's
  call. Until I do, implement the §evidence floor only. **No near-term ticket gates on this.**

---

## Part D — Notice items

### D1 · LiteLLM — **yes, cited, and currently accurate**
§implstatus cites the example and already describes it as *"not conformant as written…
included as evidence that the gateway hook point is viable, not as a conformant PEP."* So
the citation is honest **today**. When `0.3.6` makes it conformant (`ND-021`), that
paragraph becomes **false** and must be revised — drop "not conformant as written," move it
to the packaged/supported characterisation. **Proceed with `ND-021`; ping core when `0.3.6`
lands and I'll revise §implstatus.** No blocker.

### D2 · Release forecast — acknowledged, with refinements
- **`0.4.0`:** also bumps the protocol string to **`aadp/0.2`** (vocabulary discriminator),
  and includes **`sender_mismatch`** (E5) alongside the cap rename — the vocabulary change
  is complete in this one increment. "Breaking" is accurate for **archives/readers**, not
  for PEP enforcement (audit-only on the PEP path, per E1.3).
- **`0.4.1` (P1):** ensure the **present-but-empty** later receipt fields (signature,
  Merkle root) are already in the **`0.4.0`** migration so P1 doesn't re-migrate.
- **`0.5.0`:** §implstatus needs the full refresh — version bump, reservation-reclamation
  now-done, `approval_ref` now-implemented, mTLS + sender-constraint profile. I'll handle
  §implstatus centrally; ping on each release that changes it.

---

## `-02` draft change list (core owns; for your visibility)

1. Reason codes: `cap_rate` + `cap_value` replace the three euro codes; deprecate (not
   remove) the old three in the IANA registry; add the normative `budget` object to
   §decideresp.
2. §versioning + §evidence: reason-code vocabulary interpreted in the scope of the row's
   recorded `protocol` version; deprecated registry entries retained permanently (absorbs
   E1.4).
3. Bump wire protocol to `aadp/0.2`.
4. §approvals + §evidence: add `approval_ref_status` evidence field; add principal-scoping
   of approvals.
5. Add `sender_mismatch` reason code; optional `reason` on the report response;
   sender-constraint = cert-thumbprint binding (RFC 8705) near-term, DPoP (RFC 9449)
   reserved for A10.
6. §transport-security: property mandate (confidentiality / integrity / mutual auth) with
   mTLS/RFC 9325 as RECOMMENDED profile. **[reconcile-01]**
7. §evidence: freeze receipt envelope + canonicalisation; `E`/`I`/`T` as opaque
   content-addressed digests. **[reconcile-01 against manifest schema]**
8. §implstatus: refresh on `0.3.6` / `0.4.x` / `0.5.0` per D2.

---

## What you're unblocked to do now

1. **`0.4.0` vocabulary release** — rename caps → `cap_rate`/`cap_value`, add the `budget`
   object, add `sender_mismatch`, bump to `aadp/0.2`. **No new codes from E2.** (E1 + E5)
2. **`approval_ref` (`ND-009`)** — build to §decidereq + the two `-02` enhancements
   (`approval_ref_status`, principal-scoping). Semantics are settled; don't invent. (E2)
3. **Receipt shape (`ND-001`)** — design the migration on the frozen envelope, later fields
   present-but-empty, `E`/`I`/`T` as opaque digests. Hold only the final digest-field
   freeze for my one confirmation against the schema. (E3)
4. **A4 before P1** — reorder confirmed. (C1)
5. **Transport + sender-constraint (`ND-004` → `ND-005`)** — property mandate; cert-thumbprint
   binding; audited `sender_mismatch` on mismatch. (E4, E5)
6. **`ND-010`** green-lit (reconstruct-in-place, no re-reserve). (C2)
7. **Phase 0** continues; `ND-021` has its D1 answer — proceed, ping on `0.3.6`.

**Not unblocked / not yours yet:** the multi-dependency trust base (B3, research-coupled);
DPoP/A10 (future work); lifting the T-set into the wire (my call).
