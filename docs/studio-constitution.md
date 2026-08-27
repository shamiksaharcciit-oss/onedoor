# The Policy Studio constitution — living text and change history

**Status:** normative for `ND-052`. This is the **living** text of the five principles.

**Origin:** [`docs/from_core/Policy_Studio_Design_Note_2026-08-22.md`](from_core/Policy_Studio_Design_Note_2026-08-22.md)
§2, delivered by core on 2026-08-22.

**Origin pinned by digest** (R054 §2), so *"this document faithfully descends from that
memo plus the amendments listed in §3"* is **checkable rather than narrated**:

```
sha256(Policy_Studio_Design_Note_2026-08-22.md) = aa8cd7c50043c2ef1768d5658b0197750d3b883190e0ab0f6aa1fd1c9ade022b
```

**That is an OBSERVATION, not the memo's integrity hash — because the memo has none.**
R054 asked for "the memo's integrity hash"; the design note carries no `Integrity:`
footer and is recorded as **ABSENT — no integrity claim** (R030 §2). So what is pinned
here is a whole-file digest **computed by delivery over the copy in this repository**,
true of these bytes and asserting nothing about who sealed them. The same observation,
with the same reasoning, is in
[`docs/from_core/INTEGRITY.md`](from_core/INTEGRITY.md); citing it as an integrity hash
would manufacture a claim nobody made, which is the one thing a provenance document must
never do.

`tests/studio/test_constitution.py` recomputes it, so a drift between this pin and the
archived bytes fails rather than being noticed.

**Why this document exists at all.** R053 §1 amended principle 5 and directed that *"the
amendment is recorded in the constitution's own change history."* The constitution had no
change history — it lives inside an **archived core memo**, and archived memos are
immutable on this programme: an annotation changes `body` and breaks the digest, so
provenance notes go in `INTEGRITY.md` and never into the memo file. Editing the design
note to amend a principle would have been the very thing the archive rule forbids.

So the memo stays exactly as it arrived, and this is the living text. **The memo is the
origin; this document is what is in force.** Where the two differ, the difference is
listed in §3 with the ruling that made it — anything not listed there is unchanged from
the memo, verbatim.

---

## 1. The five principles, as they stand today

1. **The proposer is never the enforcer.** The model emits a candidate document and
   nothing else; it is structurally outside the decision path, permanently. Only a
   human-ratified canonical artifact (hashed into `version_hash`) is ever active. Runtime
   enforcement stays deterministic and model-free.

2. **The explanation derives from the artifact, never the model's memory** (X-11 for
   policies). Plain-English renderings of rules are generated from the compiled canonical
   form. The drafting model does not narrate its own output.

3. **Adjustable parameters are the review surface; defaults are fail-closed.** Proposals
   arrive as named dials (caps, windows, tier floors, effect classes), every default
   conservative. R027's rule binds the generator: it may never emit a rule whose safety
   depends on an optional second declaration.

4. **Non-coverage is stated, never silent** (three-outcome for drafting). Every proposal
   ends with the dark-surface list: what the description mentioned that got no rule, and
   why. A policy set that does not declare its gaps is an E11 violation in product form.

5. **Every derivation gets a record.** *(Amended — R053 §1; see §3.)*

   > Every derivation gets a record. A record that promises re-derivation is a receipt; a
   > record that cannot promise it says so on its face. No derivation goes unrecorded, and
   > no record claims more than its computation delivers.

   In practice, unchanged from the original in everything but the noun: the description is
   frozen as received bytes; model, prompt and template pack are recorded as the
   instrument; proposal, edits and ratification are chained. *"Why does this policy allow
   X?"* is answerable years later by provenance, not memory.

## 2. Acceptance posture

Unchanged from the design note §5, and unusually strong: **principle violations are CI
failures, not review notes.** A proposal whose safety depends on an optional declaration
must **fail a test**, not attract a comment. The generator is benchmarked like every other
instrument on the aliasing-benchmark pattern — published cases, **published misses**.

## 3. Change history

### 2026-08-27 — principle 5, the noun: *receipt* → *record* (R053 §1)

**Was:** *"The derivation gets a receipt."*

**Is:** the amended wording quoted in §1.5 above.

**Why.** The word *receipt* was coined when every derivation in this product was
recomputable, and it carried that promise implicitly because nothing yet existed that
could not keep it. `ND-052`/S6 — the LLM proposer — is the first thing that cannot: run
the same description through the same model twice and the output may differ, and recording
the instrument pins the **conditions**, never the output.

Delivery flagged the contradiction rather than resolving it locally, and core amended the
constitution rather than stretching it, on a law the programme already owned: **a ruling's
own vocabulary is not exempt from the ruling's law** (R051 §1). A constitution whose own
noun outruns the computation is R050 §4's defect installed at the top of the document.

**Effect on existing artifacts: none.** Every receipt already emitted — backtest,
ratification, anchoring — *is* recomputable and satisfies the amended wording unchanged.
What the amendment permits is the new kind: a **derivation record**
(`onedoor/derivation-record/1`), which states on its face that it does not attest
re-derivability, and that **the candidate's authority comes from the checks it passes,
never from the record.**

**Recorded here rather than in the design note** because the design note is an archived
memo and the archive is immutable. This document is the living text; that memo is the
origin.
