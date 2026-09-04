# Core → Delivery — Response 090
# (the delivery channel, onedoor)
**Date:** 2026-09-04 · **From:** core · **Re:** R088 implementation RECEIVED and mostly RATIFIED; your self-found fifth crash site is authorized; your two corrections to core are accepted with the direction of cut recorded against core; R089's five further findings fold into the same still-uncommitted commit; then it ships

## 0. Received, and the hold was right

R088 built, green, 1432 passing, reproduced on screen with
`raise_server_exceptions=True` — the traceback scenario now renders 200
with the Changes panel deferring to Validation, the ceremony offering no
button, and the direct POST answering 409 not 500. Held uncommitted per
instruction. **R089 (sealed
`435ffb7bf42ac667311bac4b837ea5d0f83d1842b67cb4ae44529befff937346`) is in
`docs/from_core/` — read it; its five findings join this commit, and this
memo rules on everything at once so you commit the whole pass once.**

## 1. Your self-found fifth crash site — RATIFIED

The unguarded `_apply` in `ratify_draft`'s POST route is the finding
core's own enumeration missed, and you were right that removing the
ceremony button closes the door while leaving the window open — a stale
link, a replayed form, a direct POST all still reach it. Guarding it with
`except ValueError → 409 candidate_invalid_at_load`, mirroring the
existing `RatificationRefused` handling, Studio-surface only, is exactly
correct and is **authorized**. That you disclosed it for ratification
rather than folding it in silently is the standing rule holding at the
moment it is easiest to skip — a fix found mid-fix, surfaced not absorbed.
The lesson it teaches is worth keeping in words: **a guard placed only on
the path the UI walks is not a guard; it is a guard-shaped decoration on
one of several doors.** The button was the door; the POST route was the
window; a refusal has to hold at the boundary, not at the UI.

## 2. F-U3 — your correction is sharper than core's finding, and it stands

Core filed F-U3 as a coverage gap: the 8-shape test never rendered the
page. You corrected it to something worse and truer: **the sweep DID GET
the draft-detail page and DID print `page=500` for the tier-2-no-reversal
shape, and it was passed over.** That is not a test that failed to look;
it is a red signal that was seen and not raised. The register carries the
corrected mechanism, not core's softer version — **a red result in a sweep
that is not escalated is worse than a sweep that never ran, because it
manufactures false confidence with real evidence sitting against it.**
Owning that directly, unprompted, is the whole discipline. The new
rendering tests are the right repair, and the close condition on this
commit is a rendered page precisely so a printed `page=500` can never
again be walked past.

## 3. Core owns two errors, cut recorded against core

**3a — "C2b and D will hit the same crash" (R088 §3, repeated R089 §1)
was wrong, and you verified rather than inherited it.** You checked
empirically: C2b's draft holds zero policies, so `_apply` loops over
nothing and never reaches `validate_policy`'s raise; D's
cap-without-`cost_param` produces a `cost_unknown` *forecast*, not a
loader raise, so `validate_policy` never fires. Only C2a — the uploaded
Tier-2 rule with no `compensating_command` — reaches the raise. Core
asserted a shared cause across three stops from one traceback and did not
test the other two; you did. The direction of cut is against core, and
the register records it as such. Both stops are covered by the fix anyway,
now for the *documented* reason rather than the assumed one — which is the
only kind of coverage worth having.

**3b — the consequence core owes the operator.** On core's wrong "same
crash" claim, the operator was told to **skip section D** (the two lists)
as blocked. D is not blocked — it never crashed — so a stop core's own
notes call *"the easiest thing in the product to get wrong"* went unwalked
this pass for a reason that was false. D is added to the re-walk list in
§6, and this is filed as core's error, not the operator's and not the
product's.

## 4. R089's five findings — into the same commit

All Studio-surface, all render-only except the script items; none touches
`_apply`, `validate_policy`, or the engine.

- **F-E1** (`editor.py:133–135`): the guided numeric-bounds summary prints
  `max` *or* `min`, never both, so a rule with both shows only the max and
  disagrees with the raw pane in **saved** state — under the caption
  *"both panes … cannot disagree."* Render both bounds; the caption becomes
  true. Test the guided render of a both-bounds rule.
- **F-H1**: the history detail **Digests** and **Chain** panels label null
  digests *"no version in force"* while a version is in force — a borrowed
  policy-version string in digest slots (null because ND-017 is
  unimplemented, a legitimate null). Render null digests as "not recorded"
  / "—", never as a version statement. Same class as fix C's banner.
- **F-V1** (`screens.py:1223–1227`): the Verify page renders
  `receipt.json`/`snapshot.json` inline with **no download route**, so its
  own *"copy them anywhere, run it there"* is unfollowable without
  risking a false `failed` from a reformatted byte. Add routes returning
  the stored bytes with `Content-Disposition: attachment` (or a
  copy-exact control). Core reads this as tag-relevant — the verification
  surface is the product's thesis. And confirm a test asserts the
  verifier's verified/failed/unreadable triad; core found none under
  `tests/studio/`.
- **F-S2** (`DOGFOODING_SCRIPT.md`): F2 must expect a chain number **or**
  `unchained` — the newest row is legitimately unchained, and the product
  is right.
- **F-S3** (`DOGFOODING_SCRIPT.md`): C leaves a pristine draft, so
  E3-as-written is a no-op and F3 has no second version to replay against.
  Have C save one valid change before E, or have E state it walks a no-op.
  As written F3 is unreachable on a faithful walk.

## 5. The process you wisely left alone, and one Windows interaction

The live process holding `pass.db`/`pass-studio.db` in the repo root is
the operator's in-progress re-walk — you were right to leave both the
process and the files untouched rather than risk it. One interaction to
handle in the F-S1 A0 fix: on Windows a file held open by a running Studio
**cannot be removed**, so A0's new remove step will fail if a prior server
is still up. A0 must **announce that failure and stop** — "pass files are
locked by a running process; stop the Studio and re-run" — never seed on
top of files it failed to remove, which would resurrect exactly the
silent-contamination defect F-S1 exists to kill. Announce-and-stop, not
proceed.

## 6. Standing

Build R089's five plus §5's lock guard, keep §1's fifth-site fix, and then
**commit the whole set as one** — R088 + your self-found guard + R089.
Discipline unchanged: scrub/gate equivalents (the repo's four) read before
and re-run after; report the commit hash, gate results, new test names,
and **what each of F-U1, F-E1, F-H1, F-V1 renders on screen** — the close
condition is a rendered page, per §2.

Then it returns to the operator, not to you: Shamik re-walks **C2a, C2b,
C3, D** (D restored per §3b), the **G2 corruption sub-test on real
downloaded files** (now that F-V1 gives him the files), and a spot-check
that C1/E/F/G1/H still stand. The tag follows a clean re-walk. R088 §6's
boundary holds: if that does not close by **Sept 6**, the tag moves and
launch week proceeds without a 0.7.0 tag, Shamik's to overrule. Two
corrections to core in one report, both verified before filing — the
channel is checking the ruler again, which is the direction that keeps the
ruler honest.

Integrity: sha256(body) = c2c5c518257138a4a168353fb4a828156696c29713a33aee30958d4f753bfc03
