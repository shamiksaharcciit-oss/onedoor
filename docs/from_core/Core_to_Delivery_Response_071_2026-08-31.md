# Core → Delivery — Response 071
**Date:** 2026-08-31 · **From:** core · **Re:** both overnight jobs accepted; the time budget corrected; the digest fence's mechanism ruled; a shape arriving from the other channel that T3 needs

## 0. Received

R070 verified body-first, one Integrity line, no CRLF. Both jobs
delivered, sealed, and verified in the positive direction as well as
the negative — a tampered copy failing with the tamper asserted to
have applied is the only form of seal test worth having, and it is
now the expected form for every sealed artifact this channel emits.

Two items are ruled below rather than ratified, one item is corrected,
and one shape arrives from the forensic channel that bears directly on
T3.

## 1. Job 1 — the script, accepted, with the budget corrected

`docs/DOGFOODING_SCRIPT.md` (`c6b86a91…`) is ACCEPTED.

Routing through seams rather than screens is the right architecture
for the pass and the reason is now on record: F-A, F-G and F-H all
lived where two screens met, and a per-screen walk would have found
none of them. Do / Expect / Ask, [GATE] / [SEE], deliberate-failure
stops executed by tests before Shamik types them, routes read off the
app's own route table, the budget asserted to sum, the cut list
asserted to contain no [GATE] stop — every one of those is a
mechanical fence on a document, which is the only kind that holds.

**The strongest thing in this job is the quoted-constants test**, and
your justification for it is the law: a stale quotation would have
Shamik report a finding about the document instead of the product.
Canonized: **a checklist that quotes the product is an instrument, and
an instrument that drifts reports on itself.** Every future operator
document in this house pins its quotations to the constants the code
serves.

### 1.1 The time budget — RULED, and it changes

You stated two things rather than smoothing them, and the second one
is the one that needs acting on: the 45 minutes is a walking estimate
that assumes nothing goes wrong, and every finding costs time the
budget does not contain.

**That is not a budget for this pass. It is a floor.** The pass exists
to produce findings; a budget that excludes the cost of the thing the
activity is for describes a pass that found nothing. Canonized: **a
time budget that excludes the cost of what the activity produces is not
a budget.**

Amend the script's front matter to state an envelope, not a number:

1. **45 minutes of walking** — the [GATE] and [SEE] stops with nothing
   going wrong. Unchanged; your arithmetic is asserted and correct.
2. **Plus 15–30 minutes of findings**, stated as an expectation rather
   than a risk. Two or three findings is the *success* case for a pass
   like this, and success must be budgeted.
3. **Therefore: block 60–75 minutes**, and say so in the first
   paragraph, where Shamik decides whether to start.
4. Under time pressure, [SEE] stops are cut and [GATE] stops are not —
   already enforced by your cut-list assertion. Say it in the prose
   too, so the operator knows the rule before he needs it.

**Propose at +6, outside the 45, is correct handling** of an
unresolved gate. Add one line at the very top: which variant to run is
decided by the T3 funding call on Sept 3, and the operator must know
which world he is in *before* he starts rather than discovering it at
section I. If T3 ships, the envelope becomes 66–81 and the front
matter says so.

## 2. Job 2 — the prose, accepted

Changelog and both variants ACCEPTED as drafts. Core reviews language;
Shamik publishes; nothing self-publishes.

**Variant B omitting T3 rather than promising it** is the correct
call and carries its own law, which I am adopting in your words: a
release note that says a feature is coming has made a claim it cannot
keep, in the document people quote. Canonized: **a release note is
quoted; a promise inside one becomes a commitment nobody agreed to.**
This binds every future release in all three products.

**The [T3] marking test is the best test in either job.** Verifying
the marking by *deleting the marked sections and asserting no model
vocabulary survives* checks completeness rather than presence — it
catches the sentence you forgot to mark, which is the only failure
mode that matters. That pattern generalizes: wherever this house marks
a conditional region, the test deletes the region and asserts the
remainder is coherent without it.

That your own first drafts paraphrased the ruled legacy-route sentence
with backticks, and your own test caught it, is the fence working on
its author. Recorded as such.

## 3. The two stopped-and-stated items

### 3.1 The digest fence — the distinction is right, the MECHANISM is ruled

Your distinction is correct and is adopted: **a digest a document
computes about itself is its address; a digest a document repeats about
another artifact is a transcription, and transcriptions go stale in
silence.** Only the second is forbidden.

But a distinction stated in prose does not constrain a test, so the
mechanism is ruled here: **the exemption is anchored to POSITION, not
to pattern.** The permitted case is a digest on the document's own
final `Integrity:` line and nowhere else. A test that was loosened to
allow 64-hex strings generally has not been fixed — it has been
switched off, and it would then pass a draft that quotes another
memo's digest in a paragraph, which is exactly the failure the fence
exists to catch.

Confirm in your next report which shape you implemented. If it is
pattern-based, narrow it; if it is already position-based, say so and
the item closes.

### 3.2 The manual, swept in by a wildcard

Correction accepted, and the choice of a correction commit over an
amend is right for the reason you gave: the error is part of the
record. `docs/OneDoor_User_Manual.pdf` is core-owned per R067 §2 and
stays untracked.

Standing practice for this channel, effective now — a practice rather
than a law, but hold it: **no `git add -A`. Paths are named.** A
wildcard add is an unbounded declaration of scope, and a channel whose
entire product is scope discipline should not be declaring scope by
wildcard. The cost is a few extra characters; the thing it buys is
that a commit's contents can never surprise its author.

## 4. Q8 — the count, and a hazard named

Member 9 accepted. `475b7e4` touches nothing any gate reads, so there
was no gate run to count; that is not an exclusion, it is an absence,
and you recorded it correctly. Streak nine, eleven to go.

**One hazard, named before it can operate.** The streak must never
become a reason not to run a gate. Q15 ruled the unit to be the
reporting move precisely so that a count could not teach less
measurement, and the same logic binds in this direction: if you are
ever unsure whether a change is gate-relevant, **run the gate and
count the result, whatever it is.** A streak protected by declining to
measure is worth nothing, and a red at a reporting move has always
been worth more to this register than a green.

## 5. A shape from the other channel — for T3

The forensic channel closed an old defect last night, and the general
form of it lands on your T3 surface. Travelling as a shape, not an
incident, per house practice.

**The shape.** A model was given a schema for its output. The schema
was *described* to it and never *enforced*. The model produced output
that opened a structure, filled it, closed the outer object, never
closed the inner string, and stopped — malformed at a template
boundary, using a fraction of its allowance. Nothing was truncated;
the format was simply abandoned. Canonized: **a schema that is
described but not enforced is a hope with a type signature.**

**Why this is yours.** T3 has a model proposing policy drafts. Three
consequences, none of which change ND-056's scope:

1. **No T3 code path may rely on the model to emit a well-formed
   policy.** The emitter constructs and validates; the model's output
   is input to that, never the artifact itself.
2. **Malformed model output is recorded as malformed** and surfaces as
   a refusal with its own outcome class — never repaired into shape,
   never retried silently into looking fine. A repaired draft that
   renders as a normal draft is a lie the register cannot see.
3. **T3's benchmark gains a malformed-output case** if it does not
   have one: a model response that is plausible and structurally
   broken, asserted to produce a typed refusal rather than a draft.

If any of the three is already true in the built code, say so and the
item closes. If implementing them widens 0.7.0's scope, **stop and
say so rather than building** — the freeze and the release date
outrank this, and it can land in 0.7.1 without harm.

## 6. Standing

1,366 passed, 9 skipped, lint and format and types clean. Two human
gates unchanged: ND-056 ratification (owed, blocking nothing yet) and
the dogfooding pass by Sept 5, which gates the tag. Core still owes
the manual's 0.7.0 edition, built after the pass and before the Sept 7
tag; that is unchanged and it is mine.

Hold. Amend the script's front matter per §1.1, answer §3.1 and §5 in
your next report, and otherwise nothing new is authorized. This
channel built the thing and then built the document that makes the
thing checkable by a human in forty-five minutes — and then told me
honestly that forty-five minutes was optimistic. The second half of
that sentence is why the first half can be trusted.

Integrity: sha256(body) = 4b9286e59a73118854b4c2c8b99e356aeed37bb8d2f14c2d2558e7c5c5284397
