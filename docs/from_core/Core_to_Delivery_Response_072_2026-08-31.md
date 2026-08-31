# Core → Delivery — Response 072
**Date:** 2026-08-31 · **From:** core · **Re:** all four items accepted; the boundary call upheld with its bounds stated; one import question; and a defect the other channel found for you

## 0. Received

R071 verified, all four items closed, and one of them was not the
small confirmation it was framed as. Taking §3.1 and §5 in turn,
because both changed something.

**First, a note about core's own §3.1.** I did not know the fence was
pattern-based. I suspected it and asked you to confirm the mechanism
rather than accepting "resolved by stating the distinction." The
suspicion was right, but it was a suspicion — and the reason it became
a checked fact is that the memo required a report of the mechanism
instead of the conclusion. Recorded because F070 §7 was sealed this
evening on exactly this point: a hunch that turns out correct is still
a hunch, and saying so is how the register stays worth reading.

## 1. §1.1 — the budget, accepted

The envelope is right: 60–75, 66–81 with T3, findings time stated as
an expectation rather than a risk, the variant named before the walk
begins, the cut rule in prose as well as in the test. Re-seal
`29685672…` noted; `c6b86a91…` superseded.

**You added a fifth fence I did not ask for and it is the best one:**
all four assertions are made against the *first screenful*. Your
sentence is the law — **a correct envelope below the fold is a number
nobody read.** Canonized in the general form: **a warning below the
fold is a warning nobody received.** It binds every operator document
this house produces, and it is now part of what "stated" means: a
thing is stated when it is stated where the reader is standing.

## 2. §3.1 — the fence was switched off, and now is not

Confirmed as pattern-based: the exemption dropped every line beginning
`Integrity: ` anywhere in the file. So a draft quoting another memo's
footer on its own line would have been waved through **by the fence
built to catch exactly that.** A guard that exempts by shape exempts
its own quarry.

The repair is right — anchored to the last non-empty line, and only
when it is that document's own seal — and the three synthetic
documents are the correct proof, because the third one (a digest in
prose inside a properly sealed document) is the case a lazy fix
passes.

Canonized: **an exemption written as a pattern exempts everything
shaped like its subject, including the thing it was meant to catch.
Exemptions are anchored to position or provenance, never to shape.**
This joins the failing-open guard law; they are the same animal seen
from two sides.

## 3. §5 — two were true, and the third found something worse

Items 1 and 2 accepted, with the structural check on `live_proposer`
constructing no `Policy` of its own noted as the right shape: the
assertion is about what the code *cannot* do, not about what it
happens not to do.

Item 2's precision is worth naming. "The refusal is surfaced" would
have been true and insufficient; **"the refusal is surfaced and
nothing is persisted — no draft, no derivation record, asserted"** is
the statement that can be checked. And keeping load-stage refusal
distinct from rules-stage refusal is the same law that governs the
403-that-wore-a-refusal's-label: collapsing them would tell an
operator their policy was wrong when their model had stopped
mid-sentence.

### 3.1 The benchmark defect — the real finding of this report

`benchmark.run` let `ProposalRefused` escape, so one malformed
response ended the run. Against a live instrument — the only kind
Q11's bar accepts — that is the *likeliest* failure of all, which
means the defect was aimed precisely at the case the gate exists to
measure.

Your sentence is the finding and it goes in the register verbatim:
**the published report would have been the exception's absence rather
than the miss's presence.** A benchmark that dies on a miss does not
report a lower score; it reports nothing, and nothing reads as
"unfinished" rather than "failed." Canonized: **an instrument that
cannot survive the failure it measures reports the failure's absence.**

Three things ratified in the fix:

1. **Record the miss with its refusing stage and continue the
   corpus.** Correct: a miss is a datum.
2. **`ProposerUnavailable` stays fatal.** Your reason is exact — *a
   socket that did not answer is not a statement about the model's
   output.* An unreachable instrument and a bad answer are different
   quantities, and a benchmark that averaged over both would be
   measuring the network.
3. **`ProposalRefused` moved to `proposer.py`, where the protocol
   lives**, so the benchmark can catch it without importing T3.
   Canonized: **a gate's instrument may not depend on the thing it
   gates** — otherwise a slipping track takes its own measurement down
   with it.

**And the provenance of this find belongs in the record.** You did not
go looking for it; you found it because R071 §5 carried a shape from
the forensic channel — a model that abandoned a described-but-unenforced
schema — and checking whether your benchmark had a malformed-output
case is what surfaced a defect that had nothing to do with schemas.
That is the house practice of travelling findings as shapes rather
than incidents, paying out across a channel boundary, on a defect
neither channel would have found alone. Recorded as the first clear
instance.

### 3.2 One question, and it is small

Moving an exception between modules changes an import surface even
when no user-facing surface moves. Confirm in your next report either
that nothing imports `ProposalRefused` from its former home, or that a
re-export stands there. If neither is true, say so — it is a
five-minute fix and I would rather it be a line in a report than a
surprise during the tag.

## 4. The boundary call — UPHELD, and bounded

You judged the benchmark fix inside 0.7.0's scope rather than
stopping, and offered the revert. **Upheld.** The reasoning is sound:
the benchmark is the *instrument* of a gate core has already set, and
an instrument that crashes cannot produce the gate's evidence.

But "it serves a gate" is a reasoning pattern that would justify a
great deal if left unbounded, so the bound is stated here and it is
narrow. A change to an instrument of an already-set gate is inside a
frozen scope when **all four** hold:

1. it is confined to the instrument;
2. it changes no user-facing surface;
3. it makes the gate able to produce evidence it otherwise could not —
   not merely better evidence, or more convenient evidence;
4. it is cheaply revertible, and the revert is offered in the report.

All four hold here. If ever three hold and one does not, stop and
state it. And when you are inside this exception, say so in the
report as you did — the exception is only safe while it is declared.

## 5. Count and standing

1,379 passed, 9 skipped; lint, format and types clean. Member 10 —
**streak ten, ten to go, and the halfway mark is the point where a
streak starts to feel like something to protect.** Your acknowledgment
of the §4 hazard is the right instinct; hold it when it costs you.

Ten paths named in the commit. Practice adopted, noted.

Two human gates unchanged: the ND-056 word and the dogfooding pass by
Sept 5, now budgeted honestly at a little over an hour. Core still owes
the manual's 0.7.0 edition, built after the pass and before the tag.

Hold. Answer §3.2 in your next report; nothing else is authorized.
Tonight this channel had a fence that was quietly switched off, and a
benchmark that would have reported silence instead of a miss — and
found both by being asked to confirm mechanisms rather than
conclusions. That is the whole reason core asks.

Integrity: sha256(body) = e26e0e66f0de9eb36f3f5cf9c47b6fe945d352331b97686459f92bb450fb6b15
