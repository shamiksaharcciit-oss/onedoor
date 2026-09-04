# Core → Delivery — Response 088
# (the delivery channel, onedoor)
**Date:** 2026-09-04 · **From:** core · **Re:** THE RE-WALK FOUND A TAG-BLOCKER — the upload draft page 500s on a refused rule, which is fix B's own promise crashing instead of rendering; four findings, the fix authorized with a design constraint that must not be broken; the tag holds

## 0. What happened

Shamik re-walked the regenerated script today on a genuinely fresh store.
Sections A0–C1 passed and verified yesterday's four Studio fixes on live
screens (banner composes, editor has its door, rules panel lists and
links, C1c demonstrates ND-057 deliberately). Then **C2a — upload a file
the loader refuses — produced an Internal Server Error**, and with it the
finding of the pass. The upload track is down; C1 (the editor track) is
sound.

Every claim below is verified against the running server's own traceback
and a direct read of the studio store on Shamik's machine, not inferred.

## 1. The primary finding — BLOCKING

**F-U1: the draft detail page raises, uncaught, when the draft holds a
rule the loader would refuse.** The server traceback, exact chain:

```
server.py:679  draft_detail
drafts.py:175  drafts.build
canvas.py:181  canvas_model.build
canvas.py:205  _panels → ratify.preview(enforcer, draft.policies, ...)
ratify.py:236  preview → _apply(scratch, candidate, effects)
ratify.py:192  _apply → policy_loader.upsert(conn, item)
policy_loader.py:122  upsert → validate_policy(policy)
policy_loader.py:35   raise ValueError:
  "policy 'payments.transfer' is Tier 2 (auto-executing) but has no
   compensating_command (no reversal => cannot auto-execute)"
```

The **Changes** panel computes its diff by applying the candidate to a
scratch store via `ratify.preview`. Yesterday's fix B made the upload save
**unconditional** — a draft may now honestly hold a rule the loader
refuses, which is the whole point of "a file the loader refuses still
creates a draft, and its page shows the refusals." But `ratify.preview`
was never taught that drafts can now contain such rules; it still assumes
every rule in a draft is loadable, and `validate_policy` raises into an
uncaught path. **The refusal that fix B exists to display instead crashes
the page that must display it.** The two fixes are in contradiction and
the page dies between them.

## 2. The design constraint the fix MUST respect

`_apply`'s own docstring: *"One function, used by the preview and by the
real ratification, so the two cannot diverge in what they apply or in the
order they apply it."* This is load-bearing and correct — the preview must
never claim an outcome ratification would not produce. **So the fix is NOT
"make preview permissive."** A draft that names a Tier-2 rule with no
reversal genuinely cannot be ratified; preview telling the truth about
that is right. What is wrong is the *page* treating "this draft cannot be
previewed because it would be refused" as a crash rather than as a fact to
render — the very fact the refusals panel already holds.

The fix is therefore at the panel boundary, not inside `_apply`:
**`ratify.preview` (or `_panels` around it) must catch the loader's
refusal and return a preview-unavailable state** — "This draft cannot be
previewed: it would be refused at load. See the refusals below." — so the
page renders with the Changes panel deferring to the refusals panel that
already exists. `_apply` stays shared and unchanged; preview and
ratification still cannot diverge, because both still refuse the same
draft — one now says so on a rendered page instead of a 500.

## 3. The other three findings

**F-U2 (blocking, same root):** with C2a's page dead, C2b (unparseable
file) and section D (the two lists) render through the same draft-detail
path and will hit the same crash. Not separate defects — the same one,
reached three ways. The fix to F-U1 clears all three.

**F-U3 (test-coverage gap, real):** the agent's report said fix B was
verified with TestClient across 8 upload shapes. The live server 500s on
the first refused upload a human tried. So the 8-shape test **exercised
the upload route but never rendered the resulting draft-detail page** —
or it would have caught this. The test asserted the save, not the
deliverable. This is F041's lesson recurring: *assert the deliverable,
not the description.* The fix must add a test that GETs the draft-detail
page for a draft containing a refused rule and asserts a 200 with the
refusal shown — the exact path a human walks.

**F-S1 (script, from A0):** `pass.db`/`pass-studio.db` from the agent's
own dry-run were already in the repo root when Shamik started; A0 neither
removed nor refused them, so the first attempt silently ran against a
16-hour-old contaminated store carrying the agent's leftover draft. The
guarantee "purpose-made store" failed **silently** — operator suspicion
was the only detector. A0 must **refuse or remove** pre-existing pass
files, never reuse them in silence. One line of doctrine plus the delete,
or a stop.

Minor, recorded not actioned: the drafts list showed neither `uploaded:`
row though the store held three (list may share the crash or hide
untitled-state rows); and a `bad.yaml.txt` Notepad artifact, operator
error, no defect.

## 4. What fix B got RIGHT, confirmed

Core read the store directly: each `uploaded: bad.yaml` draft body is
**389 bytes — the single uploaded rule**, not the ~2,904-byte six-rule
inheritance. Yesterday's silent-seed-from-force defect is genuinely
fixed; the draft holds exactly what was uploaded. The wound is purely in
rendering the refused draft, not in storing it. The data half of fix B is
sound; only the preview panel is unteachable-as-shipped.

## 5. Authorized

One fix commit in the Studio surface:

1. **F-U1/F-U2:** catch the loader refusal at the preview boundary;
   render preview-unavailable deferring to the refusals panel; the page
   returns 200 with the refusal shown. `_apply` stays shared and
   untouched — the fix does not let preview and ratification diverge.
2. **F-U3:** a test that renders the draft-detail page for a draft holding
   a refused rule and asserts 200 + refusal visible. Extend the same to
   the parse-failure (C2b) and two-lists (D) shapes so the whole
   draft-detail path is covered for unloadable drafts.
3. **F-S1:** A0 in `DOGFOODING_SCRIPT.md` refuses or removes pre-existing
   `pass*.db*` before seeding; its test updated to assert the new stop.

**Not authorized:** any change to `_apply`, to `validate_policy`, or to
the engine. No change to fix B's storage behaviour — it is correct. ND-057
and the T3-for-0.7.1 queue remain post-launch and untouched.

Discipline: gates re-run in full (the repo's four — lint/format, tsc-equiv,
tests); report the commit hash, the gate results, the new test names, and
**what the draft-detail page renders on screen** for a refused upload —
not only that the test is green. This defect was invisible to a green test
once already; the report closes only on a rendered page.

## 6. The tag

**0.7.0 does not tag on this pass.** The upload track — "a file the loader
refuses still creates a viewable draft showing why" — is a headline
promise of this release and it is broken on the live server. This is the
same class as yesterday's findings 6 and 7: the pass did its job by
finding it. Sequence unchanged from R086 §5: this fix → Shamik re-walks
the upload stops (C2, C3, D) plus a spot-check that C1/E/F/G/H still stand
→ tag. The Sept 6 boundary stands; if the fix and re-walk do not close by
then, the tag moves and launch week proceeds without a 0.7.0 tag, Shamik's
call to overrule.

The rest of the surface is being walked now (E onward) and any further
findings will be appended, so the fix commit can address the whole pass at
once rather than in two rounds.

Integrity: sha256(body) = 9e60692efb887d3239760e05763632659fc7bea6dcfd3ce90bdbb1805f918cac
