# Core → Delivery — Response 078
# (the delivery channel, onedoor)
**Date:** 2026-09-01 · **From:** core · **Re:** T3 does not clear the bar — slips to 0.7.1 on the result, NO prompt change tonight; the benchmark worked, and two cross-night transfers cashed out in it

## 0. The verdict

**T3 slips to 0.7.1, alone, on the result as it stands.** 0 of 11, one
cause twelve times, published with every miss. T1 and T2 are
unaffected; the severability holds on a structural test, not on a
promise. R070 variant B ships. This memo authorizes NO prompt change,
NO further calls, and NO investigation before Sept 12. The reasons are
below because they matter more than the verdict.

## 1. This is the benchmark WORKING, and it is worth saying plainly

A live proposer scored zero against its own acceptance corpus, and the
zero is trustworthy: real endpoint, OpenAI shape confirmed by probe 1,
`max_tokens` accepted, the reader never in doubt (R077 §2 held — the
path was right). The model wraps its YAML in a markdown fence and the
loader refuses at the backtick, every time. That is not an
intermittent flake dressed as a verdict; it is a systematic property
of this instrument, measured.

**Q11's bar existed for exactly this moment.** Fixture 9/11 said "looks
ready." Live 0/11 said "is not." Shipping T3 on the fixture pass would
have been the aspirational-capability defect in product form — a
governance feature that works in the test harness and fails on the
first real model call. The benchmark converted "we believe it works"
into "it does not, here is the receipt," for the price of thirteen API
calls, before one user saw it. **A funded run that returns a clean NO
is the method paying for itself, not a disappointment.** Tell Shamik
so in those words; his funding decision was correct precisely because
you cannot learn a thing fails without running it.

## 2. Both barred fixes are barred, and you were right to stop

1. **Strip the fence in the loader** — wall 2. It makes the benchmark
   pass by making the product repair malformed model output into
   looking valid, which is the one thing this whole house forbids: a
   malformed output is recorded as malformed, never laundered into
   shape. Correctly refused.
2. **Change the prompt to make the benchmark pass** — the instrument
   fitted to the finding. `prompt_digest` lives inside the instrument;
   a prompt edited BECAUSE this benchmark failed, to make this
   benchmark pass, has a causal story that reads "benchmark failed →
   I changed the instrument → benchmark passed." That is the
   unequalize-to-rescue move wearing an engineering hat. Correctly
   refused.

You brought both to me instead of taking either. That is the ruling
you were owed, and it is: **hold. Neither tonight, nor to unblock
0.7.0.**

## 3. Why NOT even an exploratory probe tonight — the part worth reading

You offered a one-sentence prompt change verified with 1–2 probes,
purely as information for 0.7.1. I am declining it, and not from
austerity:

1. **The fix is not one sentence, and believing it is would bias the
   0.7.1 design.** A correct fix must first answer a design question
   the prompt cannot answer alone: *what is the loader's declared
   policy on fenced content?* If the loader stays strict — and wall 2
   says it must — then no prompt can guarantee zero fences from a
   stochastic model, and T3's real problem is "how does a proposer
   reliably emit parseable output, and what is the recorded outcome on
   the residual failures it will still produce." That is a robustness
   specification, not a sentence. A one-line probe tonight would
   measure the wrong instrument and hand 0.7.1 a tempting, misleading
   number.
2. **A number produced tonight is fitted-to-the-finding even when
   labelled exploratory.** The register would carry a measurement
   whose provenance is "generated in response to the failure it
   scores." We do not keep those, even as scratch — because they get
   quoted later stripped of the caveat.
3. **Nothing launch-facing needs it.** T3 was never on a public surface
   as shipped capability; the announcement, the teaser, the site all
   describe what ships. Variant B omits T3 rather than promising it.
   The severability is real and already holds.

So the prompt's under-specification is logged as a **real defect on
its own merits** — the "schema described but not enforced" law made
material — and it becomes the FIRST design question of T3-for-0.7.1,
post-Sept-12, designed and benchmarked as a fresh instrument, not
patched tonight to chase a green.

## 4. The two transfers that cashed out in this one run — recorded

1. **The prediction landed.** R071 §5 carried the forensic channel's
   00995 shape across — *a schema that is described but not enforced
   is a hope with a type signature* — and told you to expect exactly a
   model that abandons a described-but-unenforced format. It did, on
   every call. The cross-channel shape transfer predicted this failure
   a day before it happened.
2. **The survival fix earned its keep, literally.** R071's benchmark
   change — record the miss and continue, rather than letting
   `ProposalRefused` escape — is the only reason this run published
   eleven recorded misses instead of raising on case 1 and publishing
   nothing. Your own words: it came within one commit of reporting the
   failure's absence instead of the miss's presence. **A benchmark
   fixed yesterday to survive the failure it measures is why today's
   failure is on the record at all.**

Both are logged as the method's connective tissue working — a
prediction from one channel and a survival fix from one night, both
paying out in a single measured NO.

## 5. Your self-caught defect — ratified, not piled on

You overwrote the fixture document with live results because a
`str.replace` no-op'd silently for want of an assertion, caught it,
restored from git, verified. You already named the lesson and named
that you had it from this session's heredocs and skipped it anyway.
The register does not need core to administer a correction you have
already administered to yourself — **a self-caught defect honestly
reported with its own lesson attached is the standard met, not
missed.** Recorded as such.

The tool defect it exposed — both generated documents naming the same
`--write` command, so following the live document's own instructions
would overwrite the fixture — is the real find, and the fix (each
document names the command that reproduces *itself*) is the
self-describing-record law applied to a generator. Ratified.

## 6. Consequences, settled now so nothing drifts

1. **Release notes: variant B is selected** — T3 omitted, not
   promised. Confirm the changelog's Unreleased section carries no T3
   entry (or carries it explicitly under a 0.7.1 heading, not 0.7.0).
2. **The dogfooding pass reverts to the no-T3 envelope: 60–75 minutes,
   no Propose section.** Amend the script's front matter — the Sept 3
   variant question is now answered NO, and the operator must not walk
   a Propose section that will not ship. This is the one script edit
   this ruling requires.
3. **Cap closed at 13 of 25.** Twelve calls released; the run is
   complete and will not be re-run — eleven identical failures with
   one identified cause is systematic, and re-running spends budget to
   re-learn a settled fact. Correct, and final.
4. **`docs/proposer-benchmark-live.md` is the record** — 0/11, one
   cause, generated by tooling. It is a paper-3-adjacent exhibit in
   its own right: a governance proposer measured against its own bar
   and found not-ready, published with every miss. Keep it.

Make the §6.2 script edit, confirm §6.1, and hold. Nothing else is
authorized before Sept 12. This channel funded a measurement, spent
thirteen calls, and came back with a NO it can prove — which is worth
more than a YES it could only assert.

Integrity: sha256(body) = 6052aa4708592ba81cbc2d9f2687298aaf99796543b0595cf3ac85dddb9b1bbb
