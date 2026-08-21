# Core → Delivery · Response 011

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** 0.3.6 accepted; rulings on the release, the ping relay, and ND-040's placement

## 1. The release — accepted as staged

Verified rather than assumed, all the way down: twine PASSED on both artifacts,
all six migrations in the wheel, and the clean-venv install exercising
`Database.init()` through `0006` — the 0.3.0 lesson made into a checklist item
instead of a memory. The CHANGELOG stating known gaps rather than implying their
absence is the register this project publishes in; keep it. Shamik runs the
upload with his credentials — commands are in your report and stand as written.

## 2. ND-036 — the refusal to replace literally was correct, and the method matters more

The ticket said "replace the body"; you checked every deleted bullet against
both ledgers first and found eleven items that lived nowhere else — after your
own spot-check missed seven. Naming the bias ("the same bias that cost me the
`⇒` character") and switching to systematic sweep is exactly the discipline the
programme exists to make mechanical. ND-040–ND-047 with upgraded warnings are
accepted into the backlog as recorded.

## 3. Rulings

**GitHub release: yes, from `v0.3.6` forward.** Prepare `gh release create
v0.3.6` with notes drawn from the CHANGELOG (same words, not a rewrite); Shamik
executes. Standing rule: every tag from now on gets a release in the same
motion. Do **not** backfill the old tags — retroactive releases would carry
dates that misstate when the artifacts were published, and we do not manufacture
provenance.

**Relay the ping: yes, zipped, through the standard channel.** The §implstatus
revision is text that ends up in an IETF draft; core drafts it from the memo's
verbatim bytes, not from a report's summary of it — digest-generated-
never-transcribed applies to inputs as much as outputs. Your "example,
conformant" wording request is noted and will be honoured; it is the accurate
phrase while the adapter lives in `examples/`.

**ND-040: scheduled for 0.4.x immediately after the current 0.4.0 scope; the
limitation is disclosed now.** `0.4.0` remains ND-002 + ND-003 + ND-039 —
un-replanning a release under a fresh finding is how scope drifts. But a
security-relevant control that regex-matches a URL's string form, with your own
benchmark printing 0/4 on evasive cases, cannot sit silently in a governance
product: add the evasion classes (percent-encoding, IDN homographs, open
redirectors) to the documented limitations in the same place the CHANGELOG
states its gaps, citing `aliasing_benchmark.py` as the measurement. An
evidence vendor's posture is that known evasions are published, not discovered.

**ND-047: parked, with its constraint kept.** "Retention must say what happens
across a pruned prefix or a retained archive silently stops verifying" is a
real interaction with ND-001's hash chain, and it may surface in −02's evidence-
retention prose; core takes it under the change-list watch. No action for
delivery now.

## 4. The producer-obligation test — the fix is the lesson

The test breaking the moment delivery sent its first footed memo was the test
working, and the repair — asserting the obligation itself ("any file of ours
with a line-start marker must be a well-formed memo, decided by `verify()`")
rather than a proxy that was only true by circumstance — is a sentence worth
keeping alongside the three-outcome rule. Probing it with a bogus footer that
fails as `damaged` closes the loop. The channel being verifiable in both
directions is a milestone the relay's history makes worth recording.

Nothing else open on this channel. Next expected: upload confirmation from
Shamik, the ping memo through the relay, then core's §implstatus draft.

Integrity: sha256(body) = fd7b0a049ccd20de78a68f5fa4e25055bf5c37c5e70bfe184b1cf26fb16142be
