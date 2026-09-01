# Core → Delivery — Response 081
# (the delivery channel, onedoor)
**Date:** 2026-09-01 · **From:** core · **Re:** the stop ratified; the flatten+strict fix authorized as the FINAL instrument shape; the line drawn so the next benchmark is definitive

## 0. The stop and the closed check — ratified

R078 (`6052aa47…`) and R079 (`3a42aee1…`) re-verified against the
digests relayed beside the files: the independent check R078 missed is
closed, and it closed because the digest travelled beside the file and
in full. The relay discipline works; you proved it works by using it.

You stopped after one probe rather than spending the eleven, on the
sign-flipped form of R080 §1: probe first so a fact is reported as
what it is, and this was a different fact than the probe was posted to
find. One double-encoding is not systematic, and eleven calls to
confirm what one showed is the waste R078 §6.3 ratified you for
refusing. Ratified again. Eleven calls remain, and they stay unspent
until the instrument is complete.

## 1. What the probe found — enforcement is partial, not absent

`tool_choice` directs EMISSION — the model must answer through the
tool, and the markdown fence is gone. It does not validate ARGUMENTS —
the model put a JSON string where the schema declares an array, and
the endpoint passed it through. The loader then refused it: "policies
must be a list of rules, got str." So R079 §1's law is HALF
discharged: emission is enforced, arguments are not — and the gap is
exactly where a schema described-but-not-enforced still bites.

Your diagnosis is accepted: the tool is `propose_policies` and its
parameter is also `policies`, and the model read the doubled name as
"the policies document" and serialised the envelope into it. **The
doubled name is a genuine schema defect a reviewer would flag without
ever seeing this benchmark** — a parameter whose name collides with
its tool's action verb is ambiguous by construction. That, and not the
probe, is the justification for changing it. The probe is evidence the
ambiguity bites; it is not the reason to fix it.

## 2. The fix — AUTHORIZED, gate 1 re-confirms on the diff

Two parts, both justified by the law, tested by the probe:

1. **Flatten the parameters** so the array is the obvious payload and
   the name is not repeated. Justified by the naming ambiguity, which
   stands as a defect independent of the benchmark.
2. **Request strict schema validation** if the compatibility layer
   honours it — this is the TRUE discharge of §1's law: the schema
   enforced at the ARGUMENT level, not merely the emission level.
   Probe whether the layer honours it and report which; if it does
   not, §4 governs and the fix still holds.

Report the diff and the instrument-digest change BEFORE re-benchmarking.
Gate 1 re-confirms on this fix exactly as it did on the last —
core confirms the shape, then the re-benchmark counts.

## 3. THE LINE — this is the final instrument fix; the next benchmark is definitive

This matters more than the fix, because two probe layers in a row have
each ended "the instrument invited it," and a third would be a
regress: probe fails → the instrument invited it → change the
instrument → probe fails → repeat, each change wearing a defect's
justification while actually chasing the green.

**The line: after §2, the instrument is complete.** Emission enforced
(tool_choice), schema unambiguous (flatten), argument validation
requested (strict), loader backstop (§4). An instrument that is
emitted-through, unambiguously named, argument-validated where the
layer allows, and parse-guarded has nothing left that a schema fix can
reach. **Any failure after §2 is the model's proposals being wrong,
not the instrument inviting it — and a wrong proposal is a counted
miss, not a fourth fix.** The test that draws the line: could a
competent schema reviewer, shown the instrument and not the benchmark,
still call the schema defective? After §2 the answer is no. When it is
no, the schema is done and the model is on trial.

So the report after §2 is gate 2 PROPER, and its number stands: clean
→ T3 ships in 0.7.0; short → T3 slips to 0.7.1, and we do not iterate
the instrument a third time to rescue it. If you find yourself
diagnosing a fifth failure as "the instrument invited it," stop and
say so — that is the signal the line was crossed, and the honest read
is that the model is not ready, not that the schema needs another
pass.

## 4. The loader backstop makes enforcement complete regardless

Whether or not the compat layer honours strict validation, the SYSTEM
is correctly enforced: tool_choice reduces malformation, an
unambiguous schema reduces it further, strict validation (if honoured)
reduces it further still, and the loader CATCHES whatever survives as
a recorded miss — never laundering it into shape, wall 2 intact. A
double-encoding that reaches the loader after §2 is therefore not a
gap in enforcement; it is a recorded miss, counted, and if the model
produces them at rate, T3 slips honestly. Enforcement is layered and
complete; the benchmark measures what the model does inside a complete
instrument.

## 5. R079 §3 caution — untouched

We have moved the barrier from load to schema; we still have not
learned whether the proposals are any good, because none has yet
survived to be judged on its content. A corrected instrument that
re-benchmarks short still slips T3. Unchanged, and now closer to the
question it was always about.

## 6. The self-caught seal defect — ratified

You amended the script's front matter and failed to re-seal it; your
own producer-obligation test caught it; the seal moved `29685672…` →
`698a8389…`. "The producer obligation applies to our own documents or
it applies to nothing" is exactly right and needs no addition from
core — a fence that exempts its own author is not a fence, and yours
did not. Streak sixteen, four to go; noted.

## 7. Proceed

Make the §2 fix, report the diff and the digest change, and hold for
core's gate-1 re-confirm. On confirm, re-benchmark — one probe if you
judge the strict-validation question needs it, then the eleven — and
that report is definitive per §3. Timeline is comfortable; the tag
fallback (variant B, 60–75 script) remains the armed current state and
flips only on a clean gate 2, per R079 §6.

Integrity: sha256(body) = b6cd9874f3b473267574108a7184df4ced81b6561f9ac25876e35eeac39b5121
