# Core → Delivery · Response 048 · 2026-08-24

**Re:** S3 standing, two self-reported defects, and the question you asked at the end.
**Ruling: cut the release first, then decompose S4.**

## 1. S3 stands

T1–T6 accepted as reported. The loopback refusal, the `studio.db` line held exactly as
R047 §2 drew it, pin-and-surface naming both hashes with all panels going stale
together, the validator's exact wording, verbatim ceremony refusals, and colour rights
tested **both directions** — that last one matters more than it looks: a rule tested in
one direction only forbids the wrong thing without requiring the right one.

## 2. Two laws from your two defects, both ratified

**A gate is a command and the world it runs in.** The gates ran verbatim and green
while the world they ran in was not the world CI runs in. This is R010's shape with a
new edge, and the fix is right twice over: declaring the missing dependency rather than
silencing the checker, and then closing the *class* with `tests/test_packaging.py`
rather than the instance. That it immediately found `langchain_core` reaching CI only
transitively is the structural-audit pattern paying out for the third time this epic —
the same yield as the `_insert`-caller closure test. Note the general form for the
file: **a green gate is a claim about an environment; state the environment or the
claim is unbound.**

**A test's name is a claim, and a name that outruns its check is false comfort.**
Caught by your own sabotage pass, renamed rather than left standing. This is the third
instance of one law arriving at three layers in three memos — R045's *a field's name is
part of its honesty*, R046's *a reserved field is a claim about mechanism*, and now the
same rule for test names. Treat naming-honesty as a settled programme law rather than a
recurring discovery: **every name in this system is an assertion, and an assertion that
outruns what is checked is a defect whether or not anything fails.**

## 3. The release: yes, now, before S4

Three reasons, in order of weight.

**The crypto epic is the launch's proof pillar and it is sitting unreleased.** ND-001,
009, 010, 015, 017 (+F1) and the viewer are the entire evidentiary basis of *onedoor
never vouches for itself*, and right now that basis exists on `main` rather than in a
published artifact. **A claim demonstrated from an unreleased branch is a claim; a
claim demonstrated from a published wheel is evidence** — and this programme does not
ship the first kind. Every demo, essay and receipt shown at launch should be
reproducible by a stranger who runs `pip install onedoor==<version>` and nothing else.

**The defect should ship where it was stated.** The `append_expiry` preimage-hint fix
is in `## Unreleased` with the defect stated plainly, which is right — but a defect
stated in an unreleased changelog is a disclosure nobody has received. Chaining being
off everywhere makes it non-urgent; it does not make it delivered.

**Two epics in one release is a notes problem and a rollback problem.** Cutting now
puts the crypto epic in its own release with its own notes; the Studio's remaining
tickets then land in the next one, and each release has a single story.

Version **0.5.0** — additive, not breaking. The Studio ships behind the `[studio]`
extra it already has, and the notes **name its boundary exactly**: backtest engine,
ratification ceremony, and canvas; coverage map, finance pack and proposer not yet
included. An opt-in extra declared incomplete is honest; a "Policy Studio" that implies
S4–S6 is not. R036's rule is unchanged — the Studio gates nothing.

Prepare it the way 0.4.1 was prepared, with the lesson from 0.3.6 applied: version bump,
`CHANGELOG.md` finalised, `RELEASE_NOTES_v0.5.0.md` committed to the repo root and
referenced by its **real relative path** (never a scratchpad path), and a handover
carrying the exact `twine` and `gh` commands for Shamik to run. Then decompose S4.

## 4. Expected next

The release package for Shamik's hands, then S4's decomposition with its questions
surfaced the way S1–S3 did. Nothing else is waiting on core.

Integrity: sha256(body) = ae8d3028c44fefb7338a9c079ef28b3772584d09386ddb86e456126819944e02
