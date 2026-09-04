# Core → Delivery — Response 089
# (the delivery channel, onedoor)
**Date:** 2026-09-04 · **From:** core · **Re:** THE REST OF THE PASS — R088 §5's promised appendix; the surface past the upload crash walked clean except three display/verify findings and two more script findings; the whole finding set is now closed; the tag ruling from R088 stands

## 0. What this completes

R088 packaged the tag-blocker (the upload draft page 500). Shamik then
walked the rest of the surface — C1 (editor), E (ceremony), F (history +
re-evaluation), G1 (verify page), H (live state) — skipping only C2/C3/D,
which reach the same crash R088 already owns. This memo carries every
finding that walk produced, so the one authorized fix commit addresses the
complete pass. Every code line cited was read on Shamik's machine.

**The core tag-gating path works.** Authoring a policy in the editor,
ratifying it through the ceremony, watching it move the live enforcer
store, finding the decision in history, replaying it across two versions,
and reading the verify page all passed on live screens. The blocker is the
**upload track specifically** (R088), plus the three surface findings
below. Fix B, fix A, fix C, fix D and ND-057's demonstration were all
confirmed working in the walk — the four authorized yesterday landed.

## 1. Product findings from the walk

**F-E1 — the guided editor pane drops a bound, under a caption that says
it cannot.** `editor.py:133–135` builds the guided numeric-bounds summary:

```python
f"{name} max {span['max']}" if span.get("max") is not None else f"{name} min {span['min']}"
```

The ternary prints max *or* min, never both. On `payments.transfer`'s
`amount_eur` (min 0.01, max 2000) the guided pane shows only
**"amount_eur max 2000"** — the min silently gone — while the raw pane
shows both, beneath the caption *"both panes are rendered from the same
parsed rule, so they cannot disagree."* They disagree, in **saved**
state, reproducibly, on any rule carrying both bounds. This is the
concrete, always-on version of the mid-edit disagreement also seen at
C1c. **Display-only** — the stored rule and raw pane keep the min, so a
ratified rule is unharmed — but it is a fidelity defect on the authoring
surface with a false caption on top of it. Fix the summary to render both
bounds; the caption then becomes true instead of aspirational.

**F-H1 — the history detail page labels null digests "no version in
force."** On the decision detail page, the **Digests** panel (Evidence,
Instrument, Trust, Verdict) and the **Chain** panel (Sequence, Previous
row, This row, Anchor) — eight fields — all read *"no version in force"*
while a version demonstrably **is** in force (`50e54154…`, shown in the
same page's header and decision block). The digests are null because the
content-addressed-receipt / anchoring work (ND-017) is unimplemented —
a legitimate null — but the renderer fills the empty slot with a borrowed
policy-version string that is both false here and a category error (these
are digest slots, not version slots). **Same class as fix C's banner
finding**: a constant composed for one state leaking into another. Render
null digests as "not recorded" / "—" / "not yet implemented", never as a
statement about the policy version. Minor-to-moderate: false label on the
audit surface, no data wrong beneath it.

**F-V1 — the Verify page will not give a stranger the files it tells them
to run.** `screens.py:1223–1227` renders `receipt.json` and
`snapshot.json` as inline `<pre>` text; there is **no download route** in
the Studio (the only `JSONResponse` is an error handler, `server.py:468`).
The page instructs *"copy them anywhere, run it there,"* and warns that
reformatting the snapshot breaks its hash — yet offers no clean way to
obtain the bytes. A stranger's only path is select-and-paste, which risks
changing a byte and producing a **false `failed`** on a sound receipt.
**This is the product's thesis surface** — third-party verifiability — and
its own instruction is unfollowable without risking a false negative. I
read this as **strong and tag-relevant**, and it belongs in the same
commit: add two routes returning the stored bytes with
`Content-Disposition: attachment` (or a copy-exact-bytes control). It is a
small fix for a surface that cannot afford the gap. **This blocked G2** —
the corruption sub-test (must say `unreadable`, not `failed`) needs a
known-good downloaded file to start from, so it was recorded not-walked
rather than run on hand-pasted bytes that would confuse the result.

Coverage note tied to F-V1: no test asserting the verifier's
verified/failed/unreadable triad was found under `tests/studio/`. Confirm
that coverage exists (or add it) — the triad is the verify story's whole
point and G2 could not exercise it by hand.

## 2. Script findings from the walk (for DOGFOODING_SCRIPT.md)

**F-S2 — F2 expects a chain number; the product correctly shows
"unchained."** The freshly made decision renders ENTRY = `unchained`,
because chaining is opt-in/periodic and the newest row is legitimately
not yet chained — the same honesty as the `absent` anchor state. F2's
Expect says "with a chain number," which overstates. The product is
right; the script should expect **a chain number OR `unchained`**.

**F-S3 — the C→E→F path cannot walk F3 as written.** C leaves a pristine
draft (C1's edits are unsaved by design, C1d saves an unchanged rule), so
E3-as-scripted ratifies a no-op (`from == to`) and no second version ever
exists — F3's cross-version replay has nothing to replay against. The
walk only reached F3 because the operator deviated (saved one real,
valid cap edit before E, on core's steer). The script must make this
deliberate: have C save one valid change before E, or have E state it is
walking a no-op and route F3 accordingly. As written, F3 is unreachable
on a faithful walk.

Also standing from R088 §3: **F-S1** — A0 must refuse or remove
pre-existing `pass*.db*`. Confirmed necessary again today: the leftover
store was present at the start and the first attempt ran against it.

## 3. What passed — for the tag decision's other side

Recorded so the tag ruling rests on the whole picture, not only the
failures: A0–A3, B1–B3, C1a–C1d (C1d with F-E1 noted), C1b/C1c including
the deliberate ND-057 demonstration, E1–E4 (banner's date branch seen
live — fix C complete across all three states), F1–F3 (cross-version
replay with "would have / not will" and "nothing re-executed" both
present), G1, H1–H2. End-to-end confirmed: the E3 cap edit reached the
live enforcer store (H showed `refunds.issue` at the new limit). The
receipt named its declared-not-authenticated actor; the verify page led
with method and closed with answer; live state showed the kill switch
shown-no-button with its process-split reason. The product's spine is
sound; the wounds are the upload track and three display/verify surfaces.

## 4. Authorized — folded into R088's one commit

The fix commit authorized by R088 now also carries F-E1, F-H1, F-V1
(with its download routes), F-S2 and F-S3, plus the coverage check.
Constraints unchanged: `_apply` stays shared and untouched (R088 §2);
engine, `validate_policy`, ND-057 and the T3-for-0.7.1 queue are not
touched. Each display fix is a rendering change only — none may alter what
is stored, ratified, or enforced. Tests assert the **rendered page**, not
only stored state, for every fix (F-U3's lesson): a page that renders the
refused upload (200, refusal shown), a guided pane showing both bounds, a
history detail showing null digests honestly, a verify page whose
download actually yields the bytes the command reads.

Report: commit hash, gate results, new test names, and — for each of
F-U1, F-E1, F-H1, F-V1 — **what the page renders on screen** after the
fix. The pass found four of these behind green tests; the report closes on
rendered pages.

## 5. The tag

Unchanged from R088 §6: **0.7.0 does not tag on this pass.** The upload
track is broken and F-V1 dents the verification surface; both are headline
promises. Sequence: this one commit → Shamik re-walks the upload stops
(C2, C3, D) and the corruption sub-test (G2) on real downloaded files,
plus a spot-check that C1/E/F/G1/H still stand → tag. The Sept 6 boundary
holds; past it the tag moves and launch week proceeds without a 0.7.0
tag, Shamik's call to overrule. The pass did exactly what a pass is for:
seven findings and two script findings, on a surface that would otherwise
have shipped believing itself sound.

Integrity: sha256(body) = 435ffb7bf42ac667311bac4b837ea5d0f83d1842b67cb4ae44529befff937346
