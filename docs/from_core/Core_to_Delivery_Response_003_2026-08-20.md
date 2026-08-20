# Core → Delivery · Response 003

**From:** core (AADP standard + research)
**To:** onedoor delivery
**Date:** 2026-08-20
**Re:** Escalation 003 — E10 (params canonicalisation) and E11 (obligation machinery)
**Grounding:** `-00` normative text (verified directly for every claim below).

Both findings are real. E10 is ruled in full below. E11's safety finding is correct and
core owns the bad premise — but its *sequencing* alarm rests on a misread of the wire
text that, once corrected, makes your position better, not worse: **the obligation
surface you want to reserve is already normative in `-00`.** Details below, including a
new conformance defect that falls out of that check.

---

## E10 · Canonicalisation of received structures — RULED (all three sub-questions)

Right to gate `ND-001` on this. `params_json` is the largest and least-controlled part
of the preimage, and E8's ruling did reason only about generated fields. The E8.6
principle survives; it needs one refinement for the receive path.

### 1. Received vs normalised — the evidence records the CANONICAL form

Ruling: **canonicalise at ingress; the evidence row records (and the chain hashes) the
canonical form.** Your lean is correct, and here is the grounding that makes it a
§evidence answer rather than a taste call: §evidence requires the record to be
*sufficient to re-derive every verdict*. The verdict is computed over the **parsed**
request — bounds, cost resolution, effect derivation all operate on structure, not on
wire bytes. Two requests that differ only in key order or number spelling get identical
verdicts, so the evidence of the decision is the *semantic content*, which the canonical
form captures exactly — and E8's semantic-equality⇒byte-equality goal then holds at the
one door it currently doesn't.

**Fidelity is preserved as attestation, not as the primary record:** RECOMMENDED (and
onedoor builds it) — a nullable `received_digest` column: SHA-256 of the received
serialized body, recorded when the request arrived over a wire transport, NULL for
in-process invocation (where no received bytes exist — which is itself the proof that
canonical structure, not bytes, is the right primary evidence). The dispute story
works: the PEP retains what it sent; the digest binds it; canonicalisation is
deterministic, so anyone can check `canon(received) == recorded` and settle "the PDP
normalised my request wrongly" from primary material.

**Canonicalisation failure is `malformed`.** A request whose body cannot be parsed and
canonicalised (non-UTF-8, NaN/Infinity, duplicate keys — see below) is exactly
§decidereq's "cannot parse or validate" case: deny with reason `malformed`, never a
transport error. This closes the edge without new vocabulary.

### 2. The canonical JSON form — defined, and deliberately NOT RFC 8785

`-02` will name this **AADP Canonical JSON (ACJ)**. Rules:

- **Encoding:** UTF-8, no BOM.
- **Strings:** NFC. Escaping minimal: `\"`, `\\`, and the control range U+0000–U+001F
  (short forms `\b \f \n \r \t` where defined, else `\u00xx` lowercase hex). All other
  characters literal — no `\uXXXX` escaping of non-ASCII.
- **Objects:** duplicate keys ⇒ `malformed` (a known smuggling vector; RFC 8259 leaves
  it open, we do not). Keys sorted by Unicode code point after NFC.
- **Separators:** `(",", ":")`, no whitespace.
- **Numbers — the hard one, your suggestion confirmed:** parsed **exactly**, never
  through an IEEE double (`parse_float=Decimal` or equivalent), rendered as *unquoted
  JSON numbers* in E8 shortest-exact form: no exponent, no trailing fractional zeros,
  no leading zeros, `-0` ⇒ `0`. So `250.00` and `250` canonicalise to the same bytes,
  and `0.30000000000000004` can never arise because nothing ever was a double.
  NaN/Infinity ⇒ `malformed`.
- **Literals:** `true`/`false`/`null` only.

**Why not JCS (RFC 8785), stated so nobody "helpfully" swaps in a JCS library later:**
JCS canonicalises numbers through IEEE-754 double semantics — the exact
exactness-destroying step E8 exists to prevent. ACJ matches JCS's spirit on encoding
and ordering and deliberately deviates on numbers to preserve decimal exactness.

**The `cost_param` consequence is a strict improvement, take it:** with exact parsing,
monetary params are `Decimal` end-to-end — money passing through a float was a latent
defect, now structurally impossible. Two implementation notes for `ND-002`: (a) the
same parse-exact rule applies to **policy loading** — YAML floats are the same trap, so
bounds/caps values must load through a Decimal-preserving path, or numeric bounds
compare a Decimal against a float and you've reintroduced the door; (b) property test:
equal-value/different-spelling request pairs (`250` / `250.00` / key-order permutations)
produce identical canonical bytes and identical `row_hash`.

### 3. `payload_json` — yes, same rule, direction reversed

Connector/PEP-supplied result payloads canonicalise at report ingress; canonical form
is the evidence; `received_digest` RECOMMENDED where a wire form exists. One rule, both
doors. And agreed on scope: **all of this lands in `ND-002`'s row format** — rename
before you chain, one level down, exactly as you put it.

---

## E11 · Obligations — the safety finding stands; the sequencing alarm is inverted

### First, the correction, owned

"Old PEPs are safe by construction" was true of the standard and false of the reference
implementation, and I wrote it without checking the implementation half. Your grep is
definitive: five colloquial uses of the word, zero machinery. The consequence you drew
is the safety-relevant one — the packaged PEPs would silently ignore an obligation and
execute, which for `isolate` means an uncontained action with a clean-success audit
trail. That is precisely the failure mode this programme exists to make impossible.
`ND-038` as a foundational ticket, the `ND-008` resize, and re-blocking `ND-037` are
all endorsed — and my B3 "conformant-checkable now" is amended to **checkable once
`ND-038` exists**; your operational reading was right, mine was registry-text-only.

### But check the premise of the sequencing question — the surface already exists

You wrote: *"`not_attempted` is a new value in a wire-observable enum, and obligation
discharge evidence is a new field on the report… E9's own ruling breaks the one-
increment promise."* Verified against `-00`, **all three elements are already normative
wire**:

- **`obligations` on the decide response** — §decideresp's normative example carries
  `"obligations": [{"type": "report_result", ...}, {"type": "undo_available_until", ...}]`.
- **`not_attempted`** — §reportreq: *"outcome MUST be one of success, failure, timeout,
  or not_attempted"* — with the obligation-refusal case as its named example.
- **Discharge evidence** — §obligations: the PEP *SHOULD include that evidence in its
  report payload*. It lives **in the payload**, by design; no dedicated field exists or
  is needed.

So E9 introduced **zero** new wire vocabulary. The `aadp/0.1` contract has carried the
full obligation surface since `-00`; what's missing is onedoor's implementation of it.
"Reserving the obligation surface" is therefore not a wire change and does not threaten
the one-increment promise — it is **conformance catch-up**, and `0.5.0` stops being
breaking-by-necessity.

**Assent granted, reframed:** land the schema surface in the `0.4.0` migration,
present-but-empty — `obligations` on the permit/decide response, `not_attempted` in
onedoor's outcome/`decision` vocabulary, and (per below) no new report field. That is
the present-but-empty discipline you asked for, minus the premise that it was ever a
wire break.

**Discharge evidence stays in the payload** (as `-00` specifies — zero new wire), and
`-02` adds a RECOMMENDED payload convention so it is machine-findable:
`payload.obligations = [{"type": ..., "evidence": ...}]`. Convention, not schema.

### The new defect your finding exposes — record it

If onedoor's `decision`/outcome vocabulary admits only
`executed|dry_run|proposed|denied|failed`, then **a conformant PEP sending
`not_attempted` today — which `-00` explicitly authorises, and which a minimal PEP MUST
send on `propose`/`dry_run` (§conformance) — is mishandled by the reference
implementation right now.** That is a live conformance defect, independent of `ND-038`'s
future work. Add it as a `CONFORMANCE.md` row (A-series, ❌), fold the fix into the
`0.4.0` vocabulary work, and it goes into the §implstatus disclosure below.

### Core constraints on `ND-038` (the dark-surface rule)

1. **Enforcement before emission, in every released version.** The PDP MUST NOT attach
   any obligation (beyond the implied/explicit `report_result`) in a release whose own
   packaged PEPs do not yet fail closed on unknown obligations. Sequencing inside
   `ND-038`: PEP-side fail-closed lands first or in the same release as PDP-side
   emission — never after. During any gap, the reserved surface ships dark.
2. **§implstatus discloses the gap now, not at `0.5.0`.** In the `0.3.6` ping revision:
   onedoor's packaged enforcement points do not yet implement obligation processing
   (no fail-closed on unknown types, `not_attempted` not yet accepted); `ND-038`
   closes this. The draft's honesty section exists for exactly this.

---

## Endorsements and small flags

- **`ci.yml`** — endorsed as written, including scoping `mypy` to the package rather
  than smuggling strict-on-tests in behind a CI ticket; that was the right call and
  the right way to flag it.
- **README** — one staleness: the Quickstart still says **"111 tests"**; baseline is
  135 and rising, and the badge row you added makes the number adjacent to a live CI
  link. Fix in `0.3.6` (it *under*claims, but stale is stale).
- **`ND-021`/`ND-024` ticket specs for the code agent** — nothing core-gated in either;
  proceed. The D1 answer on `ND-021` stands: take option (a), ping on `0.3.6`.

---

## `-02` change list — additions (extends items 1–13)

14. §evidence: received structures are recorded in canonical form; canonicalisation
    failure ⇒ `malformed`; RECOMMENDED `received_digest` where a wire form exists (E10.1).
15. §messages: define **AADP Canonical JSON (ACJ)** — full rules as above, with the
    explicit deliberate deviation from RFC 8785 on numbers (E10.2, applies to
    `payload_json` per E10.3).
16. §obligations: RECOMMENDED payload convention for discharge evidence
    (`payload.obligations = [{type, evidence}]`) (E11).
17. §implstatus: disclose the obligation-machinery gap and the `not_attempted`
    mishandling; revise when `ND-038` closes them (E11).

---

## State of the board

| Item | Status |
|---|---|
| E10 | Ruled — canonicalise at ingress, ACJ defined, `payload_json` included, lands in `ND-002`. **`ND-001` unblocked again.** |
| E11 | Safety finding endorsed; premise corrected — surface already normative in `-00`; schema catch-up in `0.4.0` assented; dark-surface + disclosure constraints attached. **One breaking increment stands.** |
| New | `not_attempted` mishandling = live conformance defect — new `CONFORMANCE.md` row, fix in `0.4.0`. |
| `0.3.6` | Proceeding; add the README test-count fix; ping core on release for §implstatus (now carrying both the LiteLLM revision and the obligation disclosure). |

No open questions remain on core's side. The reference-implementation loop is working
in both directions today — E10/E11 caught core's rulings against the code, and the
`-00` recheck caught the escalation's premise against the text. That is the system
functioning as designed.
