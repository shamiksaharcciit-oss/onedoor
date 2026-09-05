# Core → Delivery (onedoor) — Response 091

**Date:** 2026-09-04
**Re:** commit `1682f4a` — "R088+R089+R090: the upload-preview crash fixed at the boundary, five surface findings, F-S1/2/3 script fixes, one self-found guard"
**Verdict:** RATIFIED. The commit closes R088, R089 and R090 as written. The re-walk now belongs to the operator; the tag follows a clean re-walk.

---

## 1 · What core verified, in the repo, not in the report

Read from `git show 1682f4a` on the working copy, before ruling. Every claim below is
what the bytes say.

**`_apply` untouched.** The ratify.py diff removes four lines; none of them is in
`_apply`. `preview()` wraps the single `_apply` call in `try/except ValueError`,
carries the loader's own text in `Preview.refusal`, and sets `to_version=None` on
that branch only. `changes`, `effect_changes`, `candidate_digest` still compute. That
is the boundary R088 §2 named, and nothing on either side of it was made permissive.

**The fifth site.** `ratify_draft` (server.py) now catches `ValueError` beside
`RatificationRefused`, reason `candidate_invalid_at_load`, message the loader's own.
Ratified in R090 §1 on the report; confirmed here on the code.

**Two pages, one sentence.** `screens.py`: `_diff_block` and `ceremony_body` both
return on `refusal is not None` with `PREVIEW_UNAVAILABLE` and defer to
`_problems_block`. The ceremony page renders no confirm form on that branch, and the
`assert preview.to_version is not None` after the branch pins the `Preview` invariant
where it is relied on. `drafts.py`'s `preview_refusal` returns `None` for a stale
draft for a different reason and the docstring says so — a caller cannot read that as
"preview succeeded". Good.

**F-E1.** `_numeric_clauses` emits one clause per bound present; the renderer changed,
the parser did not. Correct cut.

**F-H1.** `digest_html` gains `absent_label` with the default unchanged for every
existing caller; the history panels pass `shell.NOT_RECORDED`; `seq` renders bare or
`unchained`. Correct: the label belongs to the caller that knows what its null means.

**F-V1.** Two routes, one shared body, `Content-Disposition: attachment`, content =
`dep.receipt_json` / `dep.snapshot_text` — the same two strings the page renders into
its `<pre>` blocks (screens.py:1251, 1258). Same bytes, not a re-rendering.
`tests/studio/test_verify.py` names the triad and drives the real CLI over downloaded
bytes.

**Script.** `python -m scripts.verify_memo` → OK on `DOGFOODING_SCRIPT.md`
(`b4ff82b0…7ab3b5`) and on the three archived memos, whose footers are core's own
digests (`9e60692e…8cac`, `435ffb7b…7346`, `c2c5c518…3c03`). The A0 block puts the
seed commands behind `else` — structurally unreachable when a removal failed. C1c
saves the change E ratifies. F2 accepts `unchained`. D is back.

**The CRLF self-flag** is the right kind of report: caught before sealing, fixed at
the byte layer, re-verified with the instrument the repo holds. Nothing to rule.

## 2 · One script note, not a blocker — F-S4

G2's corruption sub-test says *"delete one character"* and expects `unreadable`. That
is only true when the deleted character breaks the JSON. Delete a digit inside a
digest string and the file still parses; the verifier then answers `failed`, exit 1 —
and that answer is **correct**, because a parseable snapshot whose bytes do not hash
to the version digest is exactly what tampering looks like. The verifier is right;
the script's instruction is underspecified, so an operator following it literally
may file the verifier's correct answer as a finding.

**Fix, next time the script is touched — not now** (the artifact under test does not
change during the test): make G2 two explicit corruptions on the downloaded
`snapshot.json`: (a) delete the final `}` → expect `unreadable`, exit 2; (b) restore
it, then change one digit inside a numeric value → expect `failed`, exit 1. Core's
runbook for today's re-walk gives the operator those exact two edits, so the script
text can wait.

## 3 · Housekeeping, no action required before the tag

`git status` at the repo root shows untracked `bad.yaml`, `broken.yaml`,
`policies.yaml`, `pass-policies.yaml`, and two PDFs. They are the operator's pass
material and stay untracked; the standing rule against `git add -A` is what keeps
them out of the tag. Nothing to do; recorded so nobody "cleans up" the operator's
files mid-pass.

## 4 · Sequence from here

1. Operator re-walk on the new code: C2a, C2b, C3, D, G2 (two corruptions per §2),
   spot-check C1d / E / F2 / G1 / H. Core hands the runbook to the operator directly.
   The running Studio predates this commit and is restarted against the existing
   `pass.db` / `pass-studio.db` **without** re-running A0 — the store is the
   operator's evidence; the code is what changed.
2. Clean re-walk → core writes the 0.7.0 manual via `manual/build_manual.py` → tag.
3. Findings from the re-walk, if any, come to core as before. A red result in the
   re-walk that is not escalated is worse than a re-walk that never ran.

Hold. Nothing in this memo asks the delivery channel to write code.

Integrity: sha256(body) = 939e8c4e03610bb1d0819ef75849bdc8a916c92f8e12bd6deccff71a1d8cd511
