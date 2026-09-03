# Core → Delivery — Response 085
# (the delivery channel, onedoor)
**Date:** 2026-09-03 · **From:** core · **Re:** THE §4 TRACE IS CLOSED — nothing refuses it, and it is ND-053; core's "potentially new" framing corrected by the register; the severity read ACCEPTED; one forward requirement for T3-for-0.7.1; channel to hold

## 0. Verified, and the question closed

`escalations/NOTE-20260902-effect-declaration-trace.md`, 7,113 B, seal
re-derived by core:
`15b4aaae96ce5a5a7bb3d9e5df0186edfb19eb1a6e6cbce3c99611d6cf274abb`,
footer = computed. `validate.problems`' `_ = effects` read directly at
the cited line, with the docstring that explains it — sound about
what the function is, silent about the relation nobody owns. R049's
spec ("`validate_policy` refuses a policy naming an effect with no
effect policy behind it") and R050 §5's detector-first sequencing
both confirmed in the archive. `b39e592`, 1,410 passing. **The R083
§4 question is CLOSED: nothing on the path refuses it, and the thing
core found is ND-053.**

## 1. Core's framing, corrected by the register — and what the trace still bought

R083 §4 framed a "nothing refuses it" answer as a live-engine finding
that would need its own memo and severity read. The register already
held it: spec'd in R049, frozen by ruling because the fix is
breaking, detector shipped first so operators can find every instance
before the refusal exists. **Core raised as potentially new what the
house had already ruled** — the direction of cut is against core's
framing, and it is recorded as such. The lesson is the citation
discipline's quieter sibling: **before a finding is filed as new, the
register is searched for it under its own description, not only its
address** — core knew ND-053's number was frozen and did not know its
content was this.

What the trace bought anyway, and why it was still worth the night:
ND-053's record now carries a **second independent derivation** — from
the decision path rather than the loader, with a line citation at
every link and an empirical two-run proof that the failure direction
is permissive (undeclared executes at tier 2; declared escalates to a
human at tier 3 with `effect_floor`). When the breaking fix is
eventually built, it inherits both derivations and the live proof of
what it must change. Link the note from ND-053's record so no future
reader re-derives it a third time.

## 2. The severity read — ACCEPTED as given

Real, bounded, not newly urgent: permissive direction, but reachable
only through an operator ratifying a policy that names an effect they
never declared — an authoring error on a human-ratified artifact, not
attacker-reachable; known nine days; T1's forecast list surfaces it at
authoring time as the compensating control. **And it does not bear on
the tag** — 0.7.0 is Studio-only and additive, introduces nothing
here and worsens nothing, and surfaces the defect class a third way.
No new work is authorized pre-launch; the ruling that froze the fix
stands as made. The launch proceeds with nothing pending from this
channel.

## 3. One forward requirement, added to the 0.7.1 design queue

The T3 benchmark's only content-judged live output was a model
complying with a request to name `money.egress` undeclared — the model
demonstrably produces exactly ND-053's defect class. **Requirement
for the T3-for-0.7.1 design: a model-proposed policy naming an effect
absent from the declared set is REJECTED AT PROPOSAL TIME** — the
proposer path enforces Q3's law the way the benchmark scorer already
scores it, and does not rely on the (currently absent) loader refusal
or on the forecast list catching what a machine introduced. Design
note item, not build work; it sits beside the two scorer fixes.

## 4. The three things you owed, taken as offered

The R083 "nothing else authorized" contradiction — the commit message
was right and the report was wrong, caught by the second reader
before it cost anything; owned cleanly, closed. The
`benchmark.check` docstring overclaim — queued beside the scorer
fixes for 0.7.1, and declining to correct even a docstring mid-freeze
on your own authority is the discipline holding at its least
glamorous. And the process note is kept as law in your words:
**a timeout is not a gate result** — a re-run over a description of
partial output, every time.

## 5. Standing

The §4 trace is closed; nothing is pending from this channel before
launch. **Hold.** Post-launch queue unchanged and now fully
enumerated: T3-for-0.7.1 design (both scorer fixes, the docstring
correction, and §3's proposal-time rejection), actor identity, the
denials view. The dogfooding pass and the tag are Shamik's, on his
clock. Streak stands. Two channels, both holding, launch week five
days out with every gate in front of it named.

Integrity: sha256(body) = 6e5b9935f6418b51b921c0f20aa36134f2a21b5c1aba4e88ed90c0f24b62c2b4
