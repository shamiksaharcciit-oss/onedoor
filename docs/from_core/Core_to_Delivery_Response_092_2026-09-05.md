# Core → Delivery (onedoor) — Response 092

**Date:** 2026-09-05
**Re:** the operator's re-walk on `1682f4a` — verdict, two new findings, one script
correction, and one error owned by core
**Verdict:** RE-WALK COMPLETE AND CLEAN. Every gate passed on the operator's screen.
Two surface findings (F-D1, F-D2) and one script correction (G2) are authorized below
as ONE commit; after it lands and the targeted re-check passes, core writes the 0.7.0
manual and the tag follows.

---

## 1 · The re-walk, as witnessed

Every stop below was performed by the operator against the running Studio on
`1682f4a`, with output or screenshots relayed to core. Passes, in order:

- **0** Restart on existing store: banner `50e54154…a938` survived. Nothing lost.
- **C2a** `bad.yaml` upload: draft page 200; Changes panel defers with
  PREVIEW_UNAVAILABLE; Validation shows the loader's line with `line 2, column 5`;
  ceremony page shows the same sentence and **no Ratify button**. The tag-blocker is
  dead on screen.
- **C2b** `broken.yaml`: stopped at "reading the file", parser's words with position,
  all three not-run stages named.
- **C2c** non-UTF-8 upload: accuses the file ("not UTF-8 text", codec's byte
  position), explicitly not the policy.
- **C2d** the honesty line present under both refusal lists.
- **C3a** API drafts list = the browser's drafts, one store, `active_version` correct.
- **C3b** validation object: `refusals` and `forecasts` as separate keys; the refused
  draft returns 200 JSON, no crash; `position.state: "absent"` honest for a stored
  draft with no file. (Findings F-D1/F-D2 observed here — §2.)
- **C3c** submit on a stale draft refused with `base_moved`, naming both versions —
  the guard the C3a `base_moved: true` flag promised, witnessed at the one door where
  it matters. A fresh API-created draft (`cd730807…`) then submitted:
  `"state": "submitted"`, `ceremony_url`, and the exact "Nothing has been approved, no
  version pointer moved, and no receipt was written" sentence. Policies unchanged.
  Also witnessed en route: `malformed_request` answering a shell-mangled body with the
  parser's own position — accused the request, invented nothing.
- **C3d** the openapi description carries the "adds no approval route" sentence
  verbatim; the legacy `/draft/{id}/ratify` route is `"deprecated": true` in the
  machine-readable schema with its history in the docstring. The Ask holds against
  everything seen this walk.
- **D1–D3** cap-without-`cost_param` appears under "Once in force, these rules will"
  with `cost_unknown` and NOT under the refusals; both notices correct; no safety
  claim. Bonus pass: a `caps` key misplaced inside `bounds` was REFUSED at the schema
  stage — "bounds.caps: Extra inputs are not permitted — line 4, column 13". Strict
  schema, no silent drop. Exactly right.
- **G1/G2** the downloaded pair verifies (`verified`, exit 0). Corruptions: snapshot
  truncated → `failed`/1 reporting the actual hash (`7f210165…`); snapshot
  digit-tampered → `failed`/1 (`b88fb723…`); receipt truncated → `unreadable`/2 with
  the parser's position. The triad witnessed end to end on really-downloaded bytes.
- **Spot-checks** C1d: NUMERIC BOUNDS renders BOTH clauses ("amount_eur max 2000,
  amount_eur min 0.01") in saved state (F-E1 closed on screen). F2: history detail
  shows seven `not recorded` fields, `Sequence: unchained`, real version present,
  "no version in force" nowhere (F-H1 closed on screen). E and H stand from the
  prior walk; G1 re-witnessed above.

## 2 · Two findings, authorized for one commit

**F-D1 — the forecast notice leaks into the refused state.** `FORECAST_NOTICE`
(forecast.py:54: *"These are not refusals: the loader accepts every rule below…"*)
renders unconditionally wherever the forecast list appears. On the `bad.yaml` draft's
validation (API and the draft page's panels alike), `payments.transfer` sits in the
forecasts list while the refusals list above says the loader refuses it — so "the
loader accepts every rule below" is false on that output. Same constant, two surfaces,
one fix. **Requirement, not wording:** the notice must be true on both branches. Keep
the forecast rows for refused rules — "once the refusal is fixed, this is how it will
behave" is useful — but when the staged result has `loads == false`, the notice must
say that honestly (e.g. that forecasts describe how each rule will behave once it is
in force *and once any refusals above are fixed*). Agent drafts the sentence; a test
asserts the current sentence never renders beside a non-empty refusals list.

**F-D2 — the empty-declared-params sentence.** forecast.py:163 substitutes
"no parameters at all" into a slot written for a comma-joined list, producing *"a
request carrying any parameter other than no parameters at all"*. Witnessed on both
the API output and the editor surface. The empty case needs its own sentence — e.g.
*"strict_params is on and this rule declares no parameters, so any request carrying a
parameter is refused at decision time."* No sentence may be assembled by substituting
a description of absence into a slot written for a list.

Both are Studio-surface wording. `_apply`, `validate_policy`, the engine, ND-053/054/
057 untouched. One commit, tests included, renders reported per the standing close
condition.

## 3 · G2 script correction — core's error, owned

R091 §2 prescribed, for the script's next touch: *"delete the final `}` [of
snapshot.json] → expect `unreadable`, exit 2."* **That was wrong, and the operator's
run proved it:** the snapshot is never parsed by the verifier — it is hashed, byte for
byte, against the version digest the receipt ratified. A truncated snapshot is a
perfectly readable file whose bytes hash elsewhere; the check runs and answers no.
`failed` is the honest verdict, and the verifier gave it, naming the actual hash both
times. `unreadable` belongs to the RECEIPT, the one artifact the verifier must parse —
witnessed: truncated receipt → `unreadable`/2 with the parser's position.

**Corrected G2 for DOGFOODING_SCRIPT.md, in the same commit:** two corruptions, each
named for what it teaches — (a) truncate the downloaded **receipt.json** → expect
`unreadable`, exit 2 ("a receipt that cannot be read is a check that never ran");
(b) change one digit in the downloaded **snapshot.json** (still valid JSON, irrelevant
— the verifier reads bytes) → expect `failed`, exit 1 ("a readable snapshot whose
bytes hash elsewhere is exactly what tampering looks like"). Reseal the script;
commit message carries the prior digest (`b4ff82b0…7ab3b5`); `scripts.verify_memo`
before commit. Budget unchanged — same two commands, different file.

Direction of cut against core: I prescribed an instrument's expected outcomes from the
names of its outcomes, not from what the check actually reads. **Law: before
prescribing what an instrument will answer, read what it consumes.** R091 stands as
sealed; this section is its correction, by the numbered-memo chain, never by edit.

## 4 · Sequence

1. Agent lands §2 + §3 as ONE commit: gates green, tests for both findings, script
   resealed, renders reported (the corrected notice beside a non-empty refusals list;
   the empty-params sentence).
2. Operator targeted re-check, three calls, minutes not hours: (a)
   `GET /api/v1/drafts/e4832880…/validation` — notice no longer claims acceptance of
   what the refusals list refuses; (b) the same page's panels in the browser; (c) one
   editor pause on a rule with no declared params — the new sentence.
3. Core writes the 0.7.0 manual (`manual/build_manual.py`). Tag follows.

Everything else about `1682f4a` and this walk is closed. Hold after the commit.

Integrity: sha256(body) = d79b601d7a0b2b758c193cf39da0b245d8e3ebf98b38d4cd2a68e99a08216f62
