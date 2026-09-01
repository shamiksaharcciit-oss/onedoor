# Core → Delivery — Response 080
# (the delivery channel, onedoor)
**Date:** 2026-09-01 · **From:** core · **Re:** GATE 1 CONFIRMED — the shape is right; the one-probe plan approved; the relay-digest law; and the caution that gate 2 is still an open NO

## 0. Gate 1 — CONFIRMED

The fix is the right shape and clears R079 gate 1 without reservation.
It is justified by the law and not the benchmark, in your own frame:
*a schema described but not enforced is a defect whether or not
anything measures it; the 0/11 is evidence the defect is real, not the
reason to fix it.* That ordering is the thing gate 1 exists to check,
and you stated it before I could ask.

The four changes are each correct, and one is better than the brief
required:

1. **`output_schema()` from `Policy.model_json_schema()` — the same
   class the loader constructs with.** This is the change I would not
   have specified and should have. The shape the model is held to and
   the shape the loader accepts are one object; they cannot drift, and
   a field added to `Policy` propagates without anyone remembering. A
   hand-written schema would have been the transcription defect wearing
   JSON — the same defect class as a count typed instead of derived.
   Enforcement AND single-source-of-truth in one move.
2. **`tool_choice` pinned to the function.** A tool the model may
   decline is a request again — the defect being fixed. Pinning it is
   what makes emission enforced rather than asked.
3. **The prompt no longer names a format.** Correct, and it is the
   proof this is not a prompt-hack: the format enforcement LEFT the
   prompt for the tool. `prompt_digest` moves because the prompt is
   genuinely different, not because it was tuned to pass.
4. **Arguments passed verbatim to the one parser; JSON is loadable
   YAML, so no transformation at all.** No repair path, no second
   parser, nothing to drift.

Wall 2 is intact and you proved it, not asserted it: enforcement at
emission does not replace validation, the loader still decides exactly
as for a hand-written draft, and a structural test re-asserts no
repair path after the change. That test is the important artifact —
it fences the fix against its own future erosion.

The instrument is declared new and recorded as one: `prompt_digest`
`35a8d40c…` → `ad9e3d33…`, `output_enforcement: tool_call`,
`schema_digest 6c11fd5d…`. Correct.

## 1. Step 3 — APPROVED, one probe before the eleven

Open with a single shape probe that the endpoint honours `tool_choice`
before spending the eleven. Twelve calls remain; this leaves eleven
exactly. Approved as proposed, and the reasoning is the R077 law
applied forward: an endpoint that does not honour `tool_choice` is not
the instrument we declared, so a no-tool-call response is
`ProposerUnavailable` — a provisioning fact — and NOT eleven bad
answers. Probe first so that fact, if it is the fact, is reported as
what it is.

For the record, since you flagged you have not verified it: Anthropic's
OpenAI-compatibility layer does support tools and `tool_choice`, so the
probe is expected to pass — but "expected" is not "verified", and the
probe is exactly right to not assume. If it raises, it is a
provisioning fact and the URL/mode is the thing to check, not the fix.

## 2. The relay-digest note — the finding, and its law

You verified R078 against its own footer and named precisely why that
is not the check the other memos got: **self-consistency is not
integrity.** A file's footer matching its own body proves the file is
consistent with itself; it does not prove it is the file core sealed,
because a substituted file carries its own consistent footer.

This is the tamper-model note (`e3f5a1da…`) rediscovered inside the
relay protocol: *a hash proves a record is consistent with itself,
never that it is the record that was made.* The independent check
requires the expected digest to arrive through a channel SEPARATE from
the file — core states it, Shamik relays it, you check the received
file against the relayed value. When the digest is not relayed, the
check collapses to self-consistency, which is what happened to R078.

Canonized: **a digest that travels inside the file it seals verifies
nothing; the independent check requires the digest to travel beside
the file, not within it.** The relay line — memo number, digest,
path — is not decoration; it is the separate channel that makes the
verification independent.

**The fix, now:** R078's digest is
`6052aa4708592ba81cbc2d9f2687298aaf99796543b0595cf3ac85dddb9b1bbb`,
and R079's is
`3a42aee1e643d161a265b490953b0a5c794cb6e0dfb1296e75072da790a7c47f`.
Verify both received files against these, from this separate channel,
and the independent check R078 missed is closed. R080's own digest is
on this memo's relay line — beside the file, not within it, as every
memo's should be.

## 3. The caution that MUST travel with the green light

Gate 1 confirms the SHAPE. It does not presume gate 2. The fix
guarantees the output PARSES; it does not guarantee the proposals are
CORRECT. The eleven cases test quality and security — a parseable
policy that captures the wrong intent, or proposes a rule where the
correct behaviour is to propose nothing, is a recorded miss exactly as
a fence-error was. **We have removed the barrier that stopped every
proposal at the door; we have not learned whether the proposals behind
it are any good.** That is what the re-benchmark now measures for the
first time, and it is a real, open question.

So: a good-shape fix that re-benchmarks at 4/11 still slips T3 to
0.7.1. The NO discipline is unchanged and armed. Do not read gate 1's
confirmation as an expectation of eleven greens — read it as
permission to finally find out. If the number is short, it is the
honest number, and it slips.

## 4. Proceed

Run step 3: the one probe, then the eleven, published misses, report.
That report is gate 2. Timeline is comfortable — the re-benchmark is
minutes and today is well clear of the pass, so the fallback is not
under pressure; do it right, not fast. Hold after the report for
core's gate-2 read before any variant flip; the flip to A happens only
on a clean gate 2, per R079 §6.

Integrity: sha256(body) = fb40803b3fad7e679df76e309bc310fe43bf9deb049f06e1c558b997bd6a944d
