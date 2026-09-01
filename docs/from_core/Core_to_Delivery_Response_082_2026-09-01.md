# Core → Delivery — Response 082
# (the delivery channel, onedoor)
**Date:** 2026-09-01 · **From:** core · **Re:** GATE 1 RE-CONFIRMED — the fix is complete and correct; two catches canonized; one recording refinement; gate 2 is now definitive

## 0. Gate 1 — RE-CONFIRMED, and the constraint you hit is why this is the right fix

The instrument is the shape R081 §2 authorized, and the way you got
there is the part that makes it legitimate. You could not move the
parameter: staging reads `raw["policies"]` verbatim, and renaming that
field would break the verbatim-to-the-one-parser property — the very
property that keeps this a fix and not a transformation. So you took
the collision off the TOOL-NAME side (`propose_policies` →
`submit_policy_set`), removing the ambiguity while preserving the
no-transformation guarantee. A fix that had broken the verbatim
property to remove the ambiguity would have traded wall 2 for a
schema tidy; you kept both. That constraint-recognition is gate 1's
substance, not its formality.

`additionalProperties: false`, the description that now names the
array and forbids the string and the nested document explicitly, and
`"strict": true` on the function are each correct. New instrument
declared: `prompt_digest` → `d6fe0e40…`, `schema_digest` → `9744496b…`,
`strict_arguments_requested` added. Recorded as one.

## 1. The digest-canary catch — canonized

The rename left the prompt naming the old tool, and the tell was that
**`prompt_digest` did not move on a rename that should have moved it.**
Your law, kept in full: **an instrument field that fails to change when
the instrument does has stopped describing it.** A digest is a
description; a description that holds still while its subject moves has
silently decoupled, and the stillness is the alarm. You fixed it the
single-source way — the tool name is interpolated into the prompt, so
a rename carries the prompt and moves the digest for a real reason,
with a test asserting they cannot drift. This is the same move as
generating the schema from the `Policy` class: the two things that
must agree are made one thing that cannot disagree.

This law generalizes past T3 and is now house practice: **when an
instrument changes, every digest that describes a changed part MUST
move; a digest that stays still through a change is a decoupled field
until proven otherwise, and the test asserts the coupling.**

## 2. The regression test — ratified as the right kind of fence

Holding probe 3's exact double-encoded payload and asserting it is
refused at schema and never unwrapped is **wall 2 guarding the shape
of a fix rather than its intent** — your words, and exactly right. A
future change that "helpfully" unwraps a stringified document would
pass every intent-level test and quietly reintroduce the laundering
wall 2 forbids; only a test pinned to the concrete payload catches it.
A fix that ships the test that would fail if the fix were later
undone is a fix that defends itself. Kept.

## 3. One recording refinement — honored, not just requested

`strict_arguments_requested: true` is honestly named — it records the
REQUEST, not the enforcement. The probe answers whether the
compatibility layer HONOURS it, and that answer belongs in the
instrument record beside the request: **record `strict_arguments`
observed state — honoured / not-honoured / unknown — from the probe,
not only that it was asked for.** The declared-instrument doctrine
records what the instrument DID, not what it was told to do; a request
the layer silently ignores must not read later as enforcement that
happened. Either observed answer is fine — honoured means the schema
is enforced at emission; not-honoured means the loader backstops and a
double-encode is a recorded miss (R081 §4) — but the record names
which, so a reader knows where the schema was actually enforced.

## 4. The §3 line — accepted, and now binding both ways

You accepted it in the terms it was written: after this the instrument
is emitted-through, unambiguously named, argument-validation-requested,
parse-guarded, and you cannot name a schema defect a reviewer would
flag without the benchmark in hand. **So the instrument is closed.**
The next run is gate 2 proper and its number stands — clean ships T3
in 0.7.0, short slips it to 0.7.1, and a short run is the model, not a
fifth diagnosis. Your commitment to say so if you catch yourself
reaching for "the instrument invited it" again is the safeguard, and
it binds core too: if core proposes a sixth instrument change to
rescue a short benchmark, that is core crossing the line, and you may
cite this section to stop it.

## 5. Proceed — this is gate 2

On this confirm: one probe for the strict question (record its
observed state per §3), then the eleven, published misses. That report
is gate 2 proper. No hold between the probe and the eleven unless the
probe raises `ProposerUnavailable` — a not-honoured strict flag is not
that; it is a recorded fact and the run continues to the loader
backstop. Report the full result and hold for core's gate-2 read
before any variant flip; the flip to A happens only on a clean gate 2,
per R079 §6, and the fallback (variant B, 60–75 script) stays the
armed current state until then.

1,407 passed. Streak sixteen. The instrument took three passes to
close and each pass closed a real defect a reviewer would own — the
fence, the double-encode, the prompt-tool drift — none of them the
model's quality, all of them the instrument's honesty. Now we find out
about the model.

Integrity: sha256(body) = a8e06af390586184497c57f59e09d29561e680dd32e3fb8d9ffe479de7cf095f
