# Core → Delivery — Response 055 · ND-055: Policy Studio v2 — "The Ledger Room"
**Date:** 2026-08-28 · **From:** core · **Status:** BUILD AUTHORIZED

## 0. What this is

Shamik reviewed the 0.6.1 Studio hands-on (his findings F-A previously, F-G and
F-H below are his again), then set the requirement in his own words: "a UI where
we can define policies, view them, modify them, look into execution history, a
detailed UI… better than veto.so and Portotify not only in capability but in
look and feel. That's what draws people." A design note and a high-fidelity
mockup were produced and he approved them on 2026-08-28: "Lets implement this."

Binding design authority for this build:
- Design note: `Design_Note_Policy_Studio_V2_2026-08-28.md` (committed beside
  this memo; digest 118c61b3cc83712053820b76dc6320619141b3a2f49bb56f8fd3afbfd7a724ca).
- Mockup (labelled design study, fixture data from the payments pack):
  https://claude.ai/code/artifact/ee38c587-7761-4773-881a-764d21c0abdc
Deviations from either are escalations, not judgment calls.

## 1. Ruling and sequencing

ND-055 is authorized to BUILD NOW under three constraints, on the onewatch
precedent (R014/R015: additive, never gates launch):

1. **Additive only.** Zero breaking changes to the engine, service, schemas, or
   wire behavior before the firing sequence ends Sept 12 — the freeze law is
   untouched by this memo. If any stage genuinely needs an engine change, STOP
   and escalate; do not land it early, do not work around it silently.
2. **Never gates launch.** No launch artifact may depend on any V-stage
   landing. If Sept 9 arrives mid-build, the demo runs on 0.6.1 as shipped.
3. **ND-053 and ND-054 stay frozen** exactly as specced. The editor (V7) must
   note the decimal-string divergence honestly until ND-054 lands — an input
   that will be refused must say so, not pretend.

## 2. Pre-stage P0 — Shamik's two findings (allowed pre-launch, do first)

**F-G — the empty state is a dead end.** Studio index with no drafts renders
"no drafts" and nothing else (verified: 0 forms, 0 buttons, 0 inputs in the
emitted HTML). Fix: the empty state renders (a) a create-draft form (title
field + submit posting to `POST /draft`) and (b) the equivalent curl/PowerShell
one-liner for the automation-minded. The Studio is an editor with POST routes —
oneview §3's static fence does not apply to it; §4 (seal never state) binds
everywhere. A state with no next move is a wall, not a state.

**F-H — the silent db-name trap.** Service default `onedoor-service.db` vs
studio `--db` default `onedoor.db`. Fix both halves: quickstart names ONE db
explicitly in both commands, and the Studio warns visibly when the enforcer
store it opened contains zero active policies ("this store has never seen the
engine — did you point --db at the service's database?"). A wrong default that
cannot be noticed is a defect twice.

## 3. Design system (from the note; tokens are law, not suggestion)

Ground #1c1713 · panel #241d17 / #2b231c · line #3a2f26 · ink #e8ddcc · dim
#a5947d · seal gold #c9a227 (BRAND ONLY — wordmark, active-tab rule, section
rules, ratify seal motif; never a state signal) · allow #4f9e6b · review
#d07f3c · refuse #c05548, each with its muted bg. Serif display for ceremony
moments, clean sans for UI, mono with tabular-nums for digests/amounts/
versions; digests render 8…4 with copy-on-click and full value on hover.

**No network egress from Studio pages, ever.** Loopback-only is a product
claim ("nothing leaves this machine"), so pages must not fetch fonts, scripts,
or styles from any host. Vendor WOFF2 files into the package or use system
font stacks; a test asserts the emitted HTML references no external origin.
Server-rendered HTML + CSS + minimal inline JS, matching the current
architecture — no build toolchain, no framework; escalate if you believe
otherwise, with reasons.

## 4. Stages (tests first, per house law; report per stage)

**V1 — Shell.** Tokens, tabs (Policies · Drafts · History · Live state ·
Verify), header with wordmark and version banner ("in force <digest> ·
ratified <date> · N policies · M effects · loopback only"). Rerun the F-A
regression (8 sequential requests, real served app) against every new route.

**V2 — S1 Policies.** Read the pinned active version. Table: action, tier,
caps, bounds, effects, coverage badge (coverage.py). Detail: plain-language
rendering (descriptions.py exists for this) beside the YAML. The absence-is-
denial sentence appears on the library page.

**V3 — S4 History.** Read-only ledger over the enforcer store's decisions:
numbered entries, filters (time, action, verdict, policy version, key),
detail view = rule path, params, inputs digest, policy version, receipt
digest. No mutation of any kind on this screen.

**V4 — S5 Live state.** Budget bars per cap window (consumed / reserved /
free, cumulative — the thing neither competitor can draw), reservations with
ages, approval lifecycles, kill-switch state with its rank stated in words.
Engage/release only through an admin API that already exists; if none does,
render read-only and escalate. Every list has a designed empty state.

**V5 — S3 Drafts.** The existing pipeline made visible: pinned base, per-rule
was/would-become diff, backtest panel over backtest.py (N replayed, M changed,
each listed with direction — the mockup's "permits what was refused" sentence
pattern), ratification as a ceremony page (would-become digest large, base
version, session note, one deliberate confirm, receipt rendered), repin flow
that refuses a stale base. Validator honesty footnote appears VERBATIM.

**V6 — The flagship: re-evaluate under version.** FIRST verify the premise:
are ratified policy sets retrievable by version from the store? If yes: a
read-only replay (same inputs, policies-at-version → verdict) beside the
original verdict, from History detail. If no: escalate with a proposal —
additive snapshot-at-ratify table going forward, and historical versions that
predate it render "not retrievable: predates snapshots" — three-outcome
honesty applies to our own feature. Do not fake it with a diff of the rules.

**V7 — S2 Editor.** Guided form ↔ raw YAML, two panes, always in sync, inside
a draft only (fence post one: nothing here can reach the live rules). Inline
validation on change. ND-054 divergence noted at the decimal fields until it
lands.

**V8 — S6 Verify + the law tests.** The verify page shows the offline command
and expected digest and states it cannot verify — it shows a verification and
how to repeat it. Then the suite this build owes across ALL screens:
(a) `assert_seal_never_signals_state` strengthened to POSITIVE form over
emitted HTML — the owed item from R015 lands here; also apply the oneview
§5.4 fix in the spec (anchor-status moves out of the seal; §4 stands).
(b) Empty-state render test for every list view.
(c) No-external-origin test over every emitted page.
(d) Honesty-footnote verbatim test.
(e) Digest format test (8…4, copy attribute, full-on-hover).
(f) A control that cannot act must not render enabled — a button without a
working backend is an overclaim rendered in HTML.

## 5. Cadence and questions

Report after V1+V2 together, then per stage, house format (what built, what
the tests refuse, defects self-caught, questions). Questions before starting
are welcome; absent questions, proceed in order. P0 (F-G/F-H) may ship as
0.6.2 whenever ready — it is doc-and-additive only; everything V1+ ships as
0.7.0 after Sept 12, never before.

The bar, so it is written where the build can see it: put this Studio beside
veto.so and Portotify with all three open. Ours must be the one that looks
like it keeps records that could survive a courtroom — because it is the only
one that does.

Integrity: sha256(body) = 95dd6ea60cdb4e7f18a7531ec659cdc5af234488b43228cfb971f65297235bf5
