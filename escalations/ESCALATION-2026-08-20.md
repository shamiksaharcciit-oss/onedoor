# Delivery → Core · Escalation 001

**From:** onedoor delivery
**To:** core (AADP standard + research)
**Date:** 2026-08-20
**Baseline:** onedoor `0.3.5` @ `3dfe3cd`, 135 tests passing, verified by direct
source inspection today.
**Companion artifacts:** `CONFORMANCE.md` (status map), `BACKLOG.md` (tickets).

---

## Why this note exists

Delivery surveyed the source against roadmap §1–§2 before writing a line of code.
The survey found three points where the roadmap misdescribes the implementation,
two gaps the roadmap does not list, and five decisions that are wire-observable
and therefore core's to make. Per the brief, none of these get resolved in code
on delivery's authority.

**One caveat that shapes everything below.** Delivery does not hold the text of
`draft-saha-aadp-01` in this session. Every §-reference in `CONFORMANCE.md` is
carried over from the roadmap of 2026-08-20, unverified. Where a question below
cites a section, please confirm the citation is still current for `-01` as part of
answering.

**What is blocked right now:** the entire near-term phase. Items 1 and 2 below gate
the first two releases (`0.4.0`, `0.4.1`). Nothing in phase 0 is blocked, and
delivery will proceed there in the meantime.

---

## Part A — Blocking decisions

Ordered by how much they unblock.

### E1 · A4 — the normative reason-code strings and the `budget` object shape
**Blocks:** `ND-002`, `ND-003` → release `0.4.0` → transitively `ND-001`.

Current state at `3dfe3cd`: `CheckId` in `guardrail/models.py` emits
`cap_daily_rate`, `cap_eur_day`, `cap_eur_month`. Budget state is formatted into a
free-text `detail` string — `guardrail/caps.py:136–149` produces e.g.
`"€/day cap 250 reached"`. `PolicyDecision` has no `budget` field at all.

Delivery needs:

1. **The exact unit-neutral reason-code strings** the draft specifies. Not
   paraphrases — the literal values that go on the wire and into
   `actions_audit.reason_code`.
2. **The `budget` object's normative field names and types.** Delivery's working
   assumption is dimension, limit, consumed, remaining, window key, and window
   rollover instant, but this is wire-observable and delivery will not invent it.
   Unit-neutrality implies the dimension is a named string rather than a
   euro-specific field; confirm.
3. **A migration ruling.** May `0.4.0` break the old codes outright, or must the
   PDP emit both forms for a deprecation window? This is a genuine standards
   question, not a packaging one — a PEP written against `-00` will not recognise
   the new codes.
4. **A reading ruling for historical rows.** `actions_audit` is append-only and
   structurally enforced by triggers (`0001_init.sql`). Rows written before the
   rename keep the old codes **permanently** — they cannot be rewritten, by design.
   Any conformant reader of an onedoor archive must therefore accept both
   vocabularies forever. Delivery suggests the draft say so explicitly; otherwise
   the re-derivability guarantee quietly depends on undocumented reader behaviour.

Point 4 is the one delivery would most like the draft to absorb. It is a
consequence of the append-only invariant that only shows up when you try to rename
something.

### E2 · A6 — `approval_ref` semantics
**Blocks:** `ND-009`.

See Part B/B1 first: the field does not exist in the codebase, so this is
greenfield and every semantic below has to be specified rather than inferred from
existing behaviour.

Delivery needs a verdict for each case:

| Case | Question |
|---|---|
| Binding | Is `approval_ref` bound to the `request_id` that produced the approval, or may a PEP present it for a different request? |
| Reuse | Single-use, as the PDP-driven path already enforces? Delivery assumes yes — confirm. |
| Expired | The referenced approval has passed `expires_at`. Deny with which reason code? |
| Consumed | Already used for a prior resumption. Deny with which reason code — the same one as expired, or distinct? |
| Unknown / forged | No such approval, or one belonging to another principal. Deny with which reason code? |
| Kill switch | Delivery's assumption: the kill switch still wins after a valid `approval_ref`, exactly as it does on the PDP-driven path. Confirm. |

Three of those rows are potentially **new reason codes**, which loops straight back
into E1. If E1 and E2 are answered together, `0.4.0` can carry the full reason-code
vocabulary in one breaking change instead of two.

### E3 · The receipt entry format — one shape, or three migrations?
**Blocks:** `ND-001` (and, if answered late, forces rework in `ND-015`/`ND-017`).

Roadmap §6 places hash-chained audit (P1) in the near term and signed +
content-addressed receipts (P2/P3) in the mid term. Delivery has no objection to
that *pacing*. The concern is structural:

`actions_audit` forbids `UPDATE` and `DELETE` at the trigger level. Once a row is
chained, its hashed byte representation is frozen. If P1 ships a chain over one row
format and P2 later adds signature fields to that format, the archive splits into
two incompatible verification regimes with a discontinuity between them — and no
way to repair the earlier half.

**Delivery's recommendation:** design the full receipt entry shape once now —
chain fields, signature fields, and paper-3 manifest fields (`E`, `I`, `T`, `v`) —
and land it in three increments, with later fields present-but-empty from the
first migration. The canonicalisation rules (column order, JSON key ordering,
decimal and datetime rendering) must be frozen at the same moment, because they
define the bytes that P1 hashes *and* P2 signs *and* P3 addresses.

Delivery owns the how and when of building this. The *whether* — specifically
whether the manifest shape in `rederivable-manifest/` is stable enough to design
against today — is core's. If it is not yet stable, say so and delivery will hold
`ND-001` rather than chain a format that is about to move.

### E4 · A1 — is mTLS normative, or one satisfying profile?
**Blocks:** `ND-004`, and transitively `ND-005`.

There is no TLS surface in the codebase at all — no `ssl_`, `mtls`, or
`client_cert` identifier anywhere at `3dfe3cd`. Authentication today is a static
bearer key with a decide/admin role split (`service/app.py`).

Does §12.1 mandate **mTLS specifically**, or mandate the **properties**
(confidentiality, integrity, mutual authentication) with mTLS as one way to satisfy
them? The answer changes the deliverable: a normative mandate means onedoor must
refuse to serve without it and the test suite must assert that refusal; a property
mandate means onedoor ships a documented, tested deployment profile and other
profiles remain conformant.

### E5 · A2 — the sender-constraint mechanism, and the verdict on mismatch
**Blocks:** `ND-005`. Do not answer before E4.

Permits are pure bearer today: `PermittedIntent` carries `intent_audit_id`, and
possession alone suffices to report. Two candidate bindings:

- **(a)** bind to the client-certificate thumbprint established by E4's transport;
- **(b)** a PEP-held key with a proof-of-possession presented at report time.

(a) is cheaper and falls out of E4. (b) survives a terminating intermediary, which
is precisely the A10 case the draft lists as future work — so (b) may be the same
build as A10 rather than a step toward it.

Delivery needs: which binding the draft intends, and **what happens when a permit
is presented by the wrong sender** — a denial with a new reason code (E1 again), or
a transport-layer refusal that never reaches the decision pipeline. These produce
materially different audit trails, and delivery would argue for the former on the
grounds that a refused report is exactly the kind of event the audit exists to
record.

---

## Part B — Errata

The brief names the feedback loop explicitly: reservation reclamation was born
from probing the code and it changed both the draft and the implementation. These
are three more of the same shape, though smaller.

### B1 · Roadmap §2 A6 is factually wrong
The roadmap records: *"Field exists in the model; the decide path does not yet
accept/verify it (only PDP-driven resumption works)."*

`approval_ref` appears **zero times** in the repository at `3dfe3cd`:

```
grep -rn "approval_ref" --include=*.py --include=*.md --include=*.yaml .   # no matches
```

`ActionRequest` in `guardrail/models.py` has no such field. A6 is greenfield —
model field, wire schema, verification, atomic single-use enforcement — and has
been re-estimated from a wiring task to **L** in `BACKLOG.md`.

**Action requested:** if the draft's Implementation Status section carries the same
"field exists" characterisation, it needs correcting. Delivery has not read that
section and cannot check.

### B2 · A7's status reads as partial and is actually zero
`tests/guardrail/test_fail_soft.py` exists and passes. It covers **connector**
failure inside the engine — an execution error is not an authorization failure.
It has nothing to do with A7, which is about PEP behaviour when the **PDP itself**
is unreachable. No packaged PEP implements configurable `fail_static` / `fail_open`.

Flagging because anyone auditing the suite for A7 coverage will find a file whose
name suggests it and whose content does not. `CONFORMANCE.md` now states this
explicitly. If the draft's Implementation Status implies partial coverage, correct
it to none.

### B3 · A9 cannot be assessed by delivery
Multi-dependency trust base and obligation-type registry hygiene cannot be judged
from the code without the draft's registry text. Marked 🔍 in `CONFORMANCE.md`
rather than guessed at. Core will need to assess this one directly, or send
delivery the relevant section.

---

## Part C — Sequencing changes requiring assent

Per the brief, delivery confirms §6 phasing with core before reordering anything
standard-coupled. Two changes:

### C1 · A4 must precede P1 — standard-coupled, needs assent
Roadmap §6 orders: (1) hash-chained audit, (2) reason-code rename + `budget`
object. Delivery proposes reversing these.

Reason: chaining first freezes a hash over a row format that A4 is about to change,
and `actions_audit` is append-only — the pre-rename rows can never be re-chained.
The archive would carry a format discontinuity at the exact point where its
tamper-evidence guarantee is supposed to be strongest. Renaming first costs
nothing; renaming second costs a permanent seam.

This does not deprioritise the crypto epic — P1 moves by one ticket, not one
phase, and E3 asks core to freeze the whole receipt shape now precisely so the epic
stays a single coherent arc.

### C2 · Pull the pending-intent rebuild into the near term — delivery's call, noted for visibility
Not a roadmap item. `service/app.py`'s module docstring states:

> *"The service keeps the pending-intent state in memory (single-process,
> self-hosted v0.3); a restart between decide and report leaves the honest
> 'intended, unconfirmed' row in the audit log, and v0.4 rebuilds intents from that
> row instead of memory."*

That rebuild has not landed. Today a PDP restart between decide and report strands
every in-flight permit. The `exec_intent` row and `cap_reservations` already hold
everything needed to reconstruct them.

Delivery treats this as its own call — it is implementation, not wire-observable —
but raises it because (a) it is a promise the shipped code makes to its reader and
does not keep, which is the kind of thing this programme's ethos says to fix rather
than let sit, and (b) in-memory intent state blocks the multi-replica goal of
roadmap §5 outright, so it gates the scale story too. Tracked as `ND-010`.

---

## Part D — Notice, no action needed yet

### D1 · The LiteLLM example is a published non-conformance
`examples/litellm_guardrail.py:92` calls `report_result` immediately after
`decide_and_reserve`, before the gateway acts — a violation of the two-phase
contract, shipped and documented at `docs/integration-litellm.md`. The file's own
comment concedes it is a simplification and that production should report from
`async_post_call_success_hook`.

Delivery has pulled the fix to phase 0 (`ND-021`) rather than leaving it in the
long-term bucket where roadmap §5 placed it. **One question for core:** does the
draft or any paper cite this example? If so, the citation needs revisiting when
`0.3.6` lands.

### D2 · Forecast of releases that will change what the papers say
So core can anticipate rather than be pinged cold:

| Release | Conformance change | Papers / draft affected |
|---|---|---|
| `0.3.6` | None. LiteLLM example becomes conformant. | Only if the example is cited (D1). |
| `0.4.0` | **A4 closed.** Reason codes renamed, `budget` object added. Breaking. | Any text quoting reason-code strings. |
| `0.4.1` | **P1 landed.** Tamper-evidence becomes a true claim, not just append-only. | Veto-comparison framing; paper-3 authenticity groundwork. |
| `0.5.0` | **A1, A2, A3, A6 closed.** | Implementation Status section substantially; "reference implementation, version X" claims. |

---

## What delivery needs back

To unblock the near-term phase, in priority order:

1. **E1** — the reason-code strings, the `budget` object shape, the migration
   ruling, and the historical-rows reading ruling.
2. **E2** — `approval_ref` semantics, ideally answered alongside E1 so the whole
   reason-code vocabulary lands in one breaking release.
3. **E3** — assent to freezing the full receipt entry shape now, or notice that
   the manifest is not yet stable enough to design against.
4. **C1** — assent to A4 before P1.
5. **E4**, then **E5** — the transport and sender-constraint questions.

**B1** and **B2** need no reply beyond a correction to the draft's Implementation
Status if it carries the same characterisations.

Phase 0 (`ND-025` CI, `ND-021` LiteLLM fix, `ND-024` vestigial schema, `ND-036`
roadmap reconciliation) has no standard coupling and delivery will proceed there
while waiting — except that `ND-021` would benefit from the D1 answer before
release.
