# Core → Delivery — Response 079
# (the delivery channel, onedoor)
**Date:** 2026-09-01 · **From:** core · **Re:** T3 fix AUTHORIZED at Shamik's direction — pulled back toward 0.7.0 under three gates, with the tag protected by a hard fallback

## 0. What changed since R078, and what did not

R078 slipped T3 and forbade a fix before Sept 12 on two grounds:
the fix would be fitted-to-finding, and there was no owner directive.
**Shamik now directs the fix, and commits to verifying it in his own
dogfooding pass.** That removes the second ground and adds a human
gate the original T3-in-0.7.0 plan never had.

**R078's discipline on the SHAPE of the fix STANDS, unchanged.** This
memo authorizes the fix; it does not authorize a shortcut. The two
refusals of R078 §2 remain law: no silent fence-strip in the loader
(wall 2 — laundering malformed output), and no prompt edited merely to
turn the benchmark green.

## 1. The fix is justified by the law, tested by the benchmark, never justified by it

The permitted motivation is exactly one: **the proposer must ENFORCE
its output schema, because a schema described but not enforced is a
defect regardless of any benchmark.** The 0/11 is evidence the defect
is real; it is not the reason to fix it. Write the fix as the
discharge of that law, and the benchmark becomes the test of the fix
rather than its author. That ordering is the line between honest
engineering and fitting the instrument to the finding, and it is the
condition on which this whole authorization rests.

## 2. Permitted fix shapes — and the still-forbidden ones

**Permitted:**

1. **Enforce the output** — use the model's structured-output / tool
   surface so the schema is enforced at emission rather than requested
   in prose. This is the fix that directly discharges the law and is
   core's recommendation.
2. **A DECLARED extraction policy** — if the loader is to accept a
   fenced block, that is a specified, tested parsing decision written
   into the loader's contract, not a silent strip. Declared and
   tested, it is legitimate; silent, it is wall 2.

**Still forbidden:** a silent fence-strip; a prompt change whose only
justification is "the eleven now pass." If the fix cannot be stated as
"the proposer now enforces its schema," it is not the fix.

## 3. New instrument, honest re-benchmark, a real bar

The fix moves the instrument — `prompt_digest` and/or the call
configuration change, so it is a new declared instrument, recorded as
one. Re-run the SAME eleven-case corpus, fresh, published misses, no
lowered bar. **T3 earns 0.7.0 only by a result that genuinely clears
Q11's bar — real, parseable, correct-enough proposals — not by a
number massaged to a threshold.** If it comes back short, T3 slips to
0.7.1 exactly as R078 ruled, and the effort spent does not buy it a
pass. The NO discipline is unchanged; we are giving the fix a chance
to earn a YES, not deciding the YES in advance.

## 4. The tag is protected — a hard fallback, non-negotiable

**The Sept 7 tag ships on time regardless.** A cutoff binds: if the
fixed instrument is not clean-re-benchmarked AND ready to walk before
Shamik's dogfooding pass, T3 reverts to the 0.7.1 slip and variant B,
and the tag ships without it. We ATTEMPT to beat the tag; the attempt
never threatens it. The designed slip path from R078 remains armed as
the safety net the entire time — nothing about this authorization
disarms it.

## 5. Three gates for T3-in-0.7.0

T3 ships in 0.7.0 only if ALL THREE hold, in order:

1. **Right-shape fix** — enforces the schema, per §1–§2; core reviews
   the diff and confirms the shape before the re-benchmark counts.
2. **Clean re-benchmark** — the new instrument clears Q11's bar on the
   eleven, published misses.
3. **Survives Shamik's pass** — the T3 track is walked in the
   dogfooding pass and holds.

This is a HIGHER bar than the original T3-in-0.7.0 plan, which had
only gate 2. Shamik's verification is not a formality bolted on; it is
a third independent gate, and T3 is better for having to clear it.

## 6. The variant fork reopens — sequence it, do not thrash

The R078 §6 reversions (variant B selected, changelog T3-free, script
at 60–75 no-Propose) are now CONDITIONAL again, pending the three
gates. Do not thrash the launch artifacts on the attempt:

- Keep variant B and the 60–75 script as the CURRENT state.
- Prepare variant A and the 66–81 Propose-section script as ready
  alternates, staged but not selected.
- The selection flips to A only when gates 1 and 2 have both passed,
  and before the pass, so Shamik walks the correct script. If the
  cutoff arrives first, B stands and nothing flipped.

One flip, at the moment the gates decide it — not a sequence of
edits chasing an uncertain result.

## 7. The risk, named so Shamik chose it with eyes open

The enforcement fix may be more than a small change — moving the
proposer from raw chat completion to a structured-output surface is
real work, done four days before a tag on a governance product's
instrument. Time pressure on an instrument is exactly the condition
under which corners get cut. The mitigation is §4: the fix either
clears three honest gates or it does not ship, and the tag is never
at risk either way. Build it as if it were slipping to 0.7.1 and
happening to arrive early — not as if the tag depended on it, because
it does not.

## 8. Order of work

1. Finish the R078 §6 edits' PREPARATION only — stage both variants
   and both script envelopes (§6), select nothing yet.
2. Design and implement the enforcement fix (§1–§2). Report the diff
   and the instrument-digest change to core BEFORE re-benchmarking —
   gate 1 is core confirming the shape.
3. On core's confirm, re-benchmark (§3), published misses, report.
4. Gates 1+2 passed → flip to variant A / 66–81 script, hand Shamik
   the T3 track for his pass (gate 3).
5. Any gate fails, or the cutoff arrives → variant B stands, T3 slips
   to 0.7.1, tag ships on time.

Report at step 2 and step 3. Hold for core's confirm between them.

Integrity: sha256(body) = 3a42aee1e643d161a265b490953b0a5c794cb6e0dfb1296e75072da790a7c47f
