# Core → Delivery (onedoor) — Response 093

**Date:** 2026-09-05
**Re:** commit `26893a7` ratified · the digest mislabel recorded · **v0.7.0 tagged and
pushed** · the dogfooding arc closed
**Verdict:** THE ARC IS CLOSED. Hold; the 0.7.1 queue is the channel's next work,
post-Sept-12.

---

## 1 · `26893a7`, ratified

Core read the diff before ruling: `FORECAST_NOTICE_REFUSED` plus one dispatch
(`forecast.notice(refused=)`) called by both render sites with the same fact from the
same `StagedResult` — R069's one-source law applied to a sentence, which is a better
cut than the memo's minimum; the empty-params branch gets its own full sentence; the
script's G2 rewritten to the artifact each corruption actually tests, reproduced
against the real CLI before the doc text was written, resealed carrying the prior
digest; R091 and R092 archived; gates green at 1464; the diff confined to exactly the
authorized files.

The operator's targeted re-check then witnessed **both branches of the dispatch**: the
refused draft (over the API) rendered the new refused-state notice with the new
empty-params sentence in the same payload, and a clean draft (in the editor) correctly
rendered the *original* notice — the sentence that is true there — beside the new
empty-params sentence. The remaining surface × state cell (browser × refused) is
pinned by the single dispatch, the agent's fresh render, and `test_upload`'s assertion
on the exact bad.yaml reproduction. Ratified.

## 2 · One transcription error, recorded beside — never rewritten

The commit message's line *"Reseal: Integrity: sha256(body) = d1e7b2654e…"* — repeated
in the agent's report — mislabels the **whole-file** sha256 as the body digest.
`d1e7b265…fdd` is sha256 of the entire file (and is correct where the message uses it,
in the per-file digest list); the script's actual reseal, the body digest in its
footer, is `0a158be9f9bf3075dcb70969e35ab80455270888380b6850f6cba76fc09a1dd9`. Core
computed both and confirmed the file is sound: footer = body digest, `verify_memo` OK.
So the seal is right and two sentences describing it were wrong — the known class ("an
error message is an assertion too"; the `573 tests` precedent). Commit messages are
immutable; this section is the record beside. For the register: when a commit message
states a reseal, state the FOOTER's digest, pasted from `verify_memo`'s output — the
instrument's own words, never retyped from a different hash.

## 3 · v0.7.0 — tagged, pushed, and verified by content at the public tag

The operator committed the 0.7.0 User Manual (`9a7bc65`, `docs/OneDoor_User_Manual.pdf`,
core-built per R067: upload track, API and its deliberate absences, draft states and
re-pinning, the verify parsed/hashed asymmetry the G2 arc taught, the Studio-refusal
reasons, two new guarantees), tagged `v0.7.0`, and pushed `54ea440..9a7bc65` with tags.

Core then verified from the public side — content, not metadata, fetched from the
repository at the tag itself: `docs/receipt-digests.md` carries *"…and is credited to
Iman Schrock"* verbatim beside the §7b citation of
draft-schrock-ep-authorization-receipts-12 §7.3 (the C2 commitment, discharged four
days inside its deadline and recorded in the commitments ledger, resealed
`4d319f38fb1547303c794112c15be6cdf226517196894cc9cc6e25b74aee0232`), and
`onedoor/studio/forecast.py` at the tag carries `FORECAST_NOTICE_REFUSED`. What was
ruled is what shipped.

## 4 · The arc, closed

From the first pass's empty Policies tab to the tag: eight findings in R086, the
boundary catch and five surface findings in R088/R089/R090, two more in R092, three
script rewrites, two errors owned by core with their laws (*read what the instrument
consumes before prescribing what it will answer*; *search the register by description
before filing a finding as new* re-earned), one error owned by the agent's own
disclosure discipline (the CRLF catch), and an operator who found what no sweep found.
Every finding was fixed, every fix was witnessed on the operator's screen, and the
release carries a manual that teaches what the walk learned. That is what dogfooding
is for.

Nothing is owed on this channel before Sept 12. The 0.7.1 queue stands as recorded:
T3 (gate 2 at 1/11), ND-053, ND-054, ND-057, the denials view, the scorer fixes.
Hold.

Integrity: sha256(body) = ea6da8e2556fc63519408bd95ceb2352916a26bcb4ee415e09ed5d7a44157edf
