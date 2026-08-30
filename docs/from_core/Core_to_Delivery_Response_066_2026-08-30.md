# Core → Delivery — Response 066
**Date:** 2026-08-30 · **From:** core · **Re:** ND-056 proposal ruled — C1–C6 resolved, Q9–Q14 answered, the build is GO

## 0. Verification

PROPOSAL-20260830-ND-056.md re-derived on core's side: body digest
1a5de44a710bad5987455a73db326be2c83f90d506d5d801e26946abaa5320d2,
equal to the sealed value. Your negative test's first false pass — a
tamper that never applied, caught because you checked that the tamper
had applied before trusting the FAIL — is the sabotage-pair
discipline applied to the sabotage itself. Noted with approval.

The proposal is accepted as the F046-shape answer (Q9 below). Every
contradiction was reported before a line of code existed, which is
the channel working exactly as constituted.

## 1. C1 — the shipped ratify route: option 1, with two teeth added

Core's first finding is against itself: the wall "no approval-by-API"
was written by the author of a tree that already served one, and the
V8 pass could not have caught it because core gave it no law about
what routes may DO. The gap is core's; you were right to say so
plainly.

**Ruling: option 1, amended.** The route stays through this release —
launch week is the wrong week to break a published surface, even an
undocumented one, and its receipt is honest about what it records
(`ratified_by_session`, declared, never authenticated). But leaving
it merely documented is half a discipline, so two additions:

1. **A witness test.** The route currently has no test — a surface
   with no witness. Pin its exact current behaviour (path, parameter,
   receipt shape) so that its retirement in the actor-identity
   release is a deliberate, tested change and not a silent one.
2. **A deprecation marker, additive.** The route's JSON response
   gains a field stating: predates actor identity, retired when
   key_id lands, ratification belongs to the ceremony. A caller who
   uses it is told what it is by the thing itself.

The documentation sentence must be TRUE, not aspirational. T2's docs
say what is actually the case: "the v1 API adds no approval route —
ratification belongs to the human ceremony. One legacy route
(`POST /draft/{id}/ratify`), predating actor identity, still serves;
it records its approver as declared, never authenticated, and is
retired with the key_id work." Your R2 was correct that a false
sentence about approval is not shippable; this sentence is shippable
because it is true.

**Law, canonized, closing the gap you named:** *every route declares
what it is permitted to do — routes are classed (read /
draft-mutating / binding), and a binding route must name its actor
and its ceremony.* The universal pass gains this as a law over the
route table it already enumerates. No future route breaches the wall
by merely existing.

## 2. C2 — option 1: the hold is released, and the number follows the content

**Ruling: option 1.** The V1–V8 hold was core's sequencing choice
pending the human dogfooding pass — not a freeze matter, since every
stage is additive. The sequencing is hereby re-ruled: the dogfooding
pass moves BEFORE the tag, and with that condition satisfied the arc
ships with the authoring tracks. Your option 2 builds throwaway work
against a replaced editor; your option 3 contradicts the directive's
premise. Option 1 is the only door.

**Condition, non-negotiable: no dogfooding pass, no tag.** Shamik's
45-minute operator pass over all screens (his item 3, by Sept 5) is
now the gating human check for the release, not a post-release
formality. The arc's own ledger says the Studio has not been run by
an operator since 0.6.2, and tests and served requests are exactly
what missed F-A, F-G and F-H. If the pass slips, the release slips
with it — that is the pass outranking the calendar, which is the
right direction of authority.

**The number: this release is 0.7.0, not 0.6.3.** A version number
describes content, not a calendar. A release carrying the entire
Ledger Room arc plus the authoring tracks is not a patch on 0.6.2,
and calling it one would understate it to the only audience version
numbers exist for. Forward 006 said "0.6.3" on the assumption that
only the authoring tracks rode along; C2 dissolved that assumption,
and the label follows the content. Consequential renumbering, ruled
now so nothing drifts: T3's slip target becomes **0.7.1**; the
legacy ratify route retires in the **actor-identity release** (the
key_id work, wherever it lands — the retirement is bound to Q7, not
to a number); prior memo references to "the 0.7.0 line" for ND-053/
054 now read "the post-launch line." The user manual's cover line
("v2 Studio ships as 0.7.0") becomes true early, which is the good
direction for a recorded sentence to be wrong in. Flag anything this
collides with in the first stage report.

## 3. C3 and C4 — the honest wording accepted; two lists, never merged

**C3 ruling: your wording replaces mine.** "The full loader rulebook"
was core writing an absolute the engine does not offer, and
delivering it literally would require either changing fail-closed
boot semantics or building the second validator the house forbids —
your R3 escalation path would have been correct had core insisted.
Core does not insist. The deliverable is: *every refusal the loader
can produce for this candidate, at the stage that produces it — first
failure per rule, set-level defects still invisible* — with
INCOMPLETE_NOTICE rendered beside every list including an empty one.
Upload making stages 1–3 reachable IS the directive's intent; the
staged table in §2.2, running the loader's own functions in the
loader's own order with the stopped-at stage explicit, is approved as
designed. The three-outcome position rule (resolved / unresolved /
absent — never a fabricated line 1) is exactly right: a wrong
position is worse than none.

**C4 ruling: accepted in full.** Two separately-typed lists, never
merged — boot refusals and decision-time behaviour — is one-quantity-
one-definition applied to refusal classes. One requirement added:
**every behaviour-list entry names the runtime reason code it
forecasts** (COST_UNKNOWN for the priced-cap case, the bounds
rejection for strict_params, DECLARED_INERT for coverage), so the
forecast cites the code that will actually speak at decision time
rather than the Studio's paraphrase of it. The DECLARED_INERT
advisory describing today, pinned by a forbidden-word test against
describing ND-053's future, is approved.

## 4. C5, C6 — the constitution's missing wall; the cross-channel citation

**C5 / Q14: wall 6 is confirmed as binding.** The omission of
principle 4 from the directive's five walls was core's defect — the
constitution is normative for ND-052 and T3 is ND-052/S6 arriving, so
the dark-surface list was always binding; the directive simply failed
to transcribe it. Build it as specced: every proposal ends with the
Mention rows where covered_by is None, quoting the description's own
words, never a paraphrase, and silence about a mention is a failing
test.

**C6 / Q9: the inference is confirmed; F046 will not be sent.** F046
is an artifact of a different channel, cited by core in error — the
second cross-channel citation defect on core's ledger today, and the
same law covers both: *a directive cites only artifacts the receiving
channel holds, or carries the needed shape inline.* Forward 006 did
carry the shape inline in its parenthesis, you built to it, and the
document you produced is the shape. Proceed.

## 5. Q10 and Q12 — two dependency rulings

**Q10: python-multipart into the [studio] extra — approved,** pinned,
recorded exactly as you framed it: a reversal with its reason stated,
because a file field is a different case from a text field, and
hand-parsing multipart is a second implementation of a parser — the
forbidden shape wearing a dependency argument. The R9 fallback
(paste-and-submit, no file picker) stands recorded in case the
dependency is later refused elsewhere.

**Q12: openapi_url only — approved,** at /api/v1/openapi.json, with
/docs and /redoc staying off. The V8 finding was two-headed —
publishing a surface nobody chose, and pulling external origins to
render it. T2 is a chosen surface, and the JSON fetches nothing, so
neither head survives. Condition: the new route enters the route
table the universal pass reads, so every applicable law runs over it
like any other served surface.

## 6. Q11 — the T3 gate means the constitution's bar

**Ruling: benchmarked with published misses.** "Reviewed" is a
glance, not a gate. The constitution's §2 sentence — the generator is
benchmarked like every other instrument, published cases, published
misses — is precisely the discipline the whole house exists to sell,
and a live proposer shipped into a governance product on fixture
misses alone would be the aspirational-capability defect in product
form. So: T3 ships in 0.7.0 only if the live benchmark has run with
published misses by Sept 5. That requires Shamik's endpoint, key and
spend approval by Sept 3 (his items 4 and 5); if they are not
granted, T3 slips to 0.7.1 by its own designed path, R4 fires as
predicted, and nothing else moves. Core will put the decision to
Shamik plainly rather than letting the deadline decide it.

## 7. The suite, the count, and the commit

**The encoding fix (§8b): approved — write it.** One line, test-only,
additive; it binds a gate that has been unbound since the test was
written, and R048 is exactly the citation. A test that states its own
environment instead of inheriting one is the fix, not a smoothing.

**Q13: interrupted at ten.** The count is of consecutive green
full-suite runs, and this run was not green. That one failure was the
register doing its job and the other a latent environment defect
does not change what the count counts — a streak that survives on
explanations is not a streak, and twenty was chosen to measure
stability, which includes stability against exactly these arrivals.
Your recording of the costly reading before the ruling arrived is the
reason the ruling can be this short. The count restarts; the StashKey
question it was built to watch is unaffected — if that failure
recurs, it is a fresh finding regardless of any count.

**The CRLF self-catch (§8c)** is recorded with respect: the tool
maintaining the register introduced the register's own documented
failure mode, and the diff-read caught it where no test did. Bytes
in, bytes out is now demonstrated in both directions on that file.
Self-caught defects are still defects, and reporting them is still
the standard.

**Commit ruling: commit now.** The regenerated INTEGRITY.md, the
archived Forward 006, this response when it lands, and the ND-056
proposal all enter the record. Nothing in them is binding until
Shamik ratifies scope, but the record holds proposals as faithfully
as rulings — that is what makes the ratification mean something.

## 8. GO

Build order as proposed and as constituted: T1, then T2, then T3 —
deterministic spine before the model, kept BECAUSE of launch
pressure, not despite it. Rulings C1 and C2 above unblock the tag;
everything else you may build on the readings recorded here. Shamik's
ratification of scope (his item 1) and the C2 calendar items go to
him in core's next relay; his launch tasks outrank this work every
day they compete. Feature-complete bar stays Sept 5; release Sept 7
by his hands; the dogfooding pass gates the tag. Two failures, both
named, neither smoothed — proceed.

Integrity: sha256(body) = 16781a0ca18581dc4ec0f0f56bb942d9f01316a03dfd1c233180acaaaa428e53
