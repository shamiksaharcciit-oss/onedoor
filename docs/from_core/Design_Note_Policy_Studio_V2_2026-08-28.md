# Design Note — Policy Studio v2 ("The Ledger Room")
**Date:** 2026-08-28 · **Author:** core · **Status:** REVIEW-GATED — nothing
implements until the mockup is agreed WITH Shamik; then this note becomes the
build instruction for onedoor as ND-055 (post-launch; freeze law holds).

## 1. Why

The 0.6.1 Studio works (draft → pin → validate → digest → ratify) but renders
as bare text. Shamik's requirement, 2026-08-28: "a UI where we can define
policies, view them, modify them, look into execution history, a detailed UI…
better than veto.so and Portotify not only in capability but in look and feel.
That's what draws people."

## 2. Competitive position (read 2026-08-28)

**veto.so** — runtime authorization SaaS. English-to-policy authoring, three-way
classification (safe/approval/forbidden), decision records, thin SDK wrapper,
near-black minimal theme (#070707), EU AI Pact badge. Strength: onboarding
friction near zero. Weaknesses we exploit: cloud custody (their records, their
tenancy), no visible mutable state, no policy-version time travel, no
pre-ratification backtest.

**Portotify (Ayaz)** — decision governance boundary. Fail-closed, four risk
tiers, ALLOW/REVIEW/BLOCK, Ed25519-signed capsules, navy/teal dark (#08181E),
strong historical-governance narrative. Closest conceptually. Weaknesses we
exploit: same two — no live state, no version re-evaluation — plus no
draft/backtest/ratify ceremony.

**The gap both share: they show RULES; we can show STATE.** Budgets filling,
reservations held, approvals aging, a kill switch that visibly outranks
everything — and every verdict pinned to the policy version in force, with
re-evaluation under any version as a click. The UI is built around what they
cannot draw. (Differentiation, never critique, in anything public — the Ayaz
rule stands.)

## 3. Design language — "the ledger room"

Both competitors are cold dark SaaS. We are a *ledger*: the warmth of paper,
ink and seal, rendered dark. Ownable, matches the whole programme's thesis
(evidence, receipts, registers), and already latent in the current gold-on-
black Studio header.

- Ground: warm charcoal/umber (#1c1713 family), never blue-black.
- Seal gold: BRAND ONLY, never state (oneview §4). Header wordmark, section
  rules, the ratify seal motif.
- State colors live separately: allow-green / review-amber / refuse-red,
  muted, colorblind-checked.
- Type: a serif display for ceremony moments (ratification, section heads),
  a clean sans for UI, mono with tabular-nums for digests, amounts, versions.
  Digests always render as first-8…last-4 with copy-on-click, full on hover.
- Texture: hairline rules, numbered entries, stamped timestamps — register
  aesthetics. No gradients, no glassmorphism, no SaaS chrome.
- The validator's honesty line ("These are the problems found, not all
  problems…") is a FEATURE. Keep it verbatim, styled as a footnote to every
  validation panel. Honest limits are part of the brand.

## 4. Screens (six)

**S1 · Policies** — the library. Card/table of active policies from the pinned
version: id, effect labels, bounds, last-changed, coverage badge (from
studio/coverage.py). Version banner: "in force: 29e85d2c… since <date>".
Click → read view with plain-language rendering of each rule beside its YAML.

**S2 · Editor** — define/modify inside a DRAFT (never live rules; fence-post
one stands). Two panes: guided form (bounds, currencies, approval requirements,
effect labels) ↔ raw YAML, always in sync. Inline validator with the honesty
footnote. Every change shows its diff chip immediately.

**S3 · Drafts** — the pipeline the engine already has, made visible: pinned
base version, per-rule diff (was/would-become), backtest panel (replay the
draft against the decision history: N decisions, M verdicts change — list
them), then RATIFY as a ceremony page: would-become digest large, base version,
session note, one deliberate confirm. Receipt rendered on success. Repin flow
when the world moved.

**S4 · History** — the execution ledger. Filterable register (time, action,
verdict, policy version, actor/api-key): each row = numbered entry with
verdict chip, amount, policy version. Detail view = the full decision record:
inputs (digested), rule path, obligations, effects consumed, receipt digest —
plus the flagship control: **"re-evaluate under version…"** dropdown of all
historical versions → verdict-then vs verdict-now, side by side. "Was this
correct under last week's rules?" as one click. Nobody else has this; put it
where nobody can miss it.

**S5 · State** — the live room. Cumulative budget bars per counterparty/period
(consumed/reserved/free), open reservations with ages, approval lifecycles
(granted → consumed/expired), and the kill switch: a physical-looking control
with its rank stated plainly ("outranks everything, including granted
approvals"). Empty states designed (absent is a state to render).

**S6 · Verify** — the deposition page. For any receipt: the exact offline
command a third party runs, the expected digest, copy button. The page states
it cannot verify — it shows a verification and how to repeat it (oneview §4
discipline, same as onewatch).

## 5. Constraints carried forward

Loopback-only binding stays and becomes a selling line ("your policies never
leave your machine" — local-first vs veto's cloud). No aspirational labels in
the mockup — every screen mocks only capabilities the engine has or ND-specs
already frozen (numeric_value fix lands as ND-054 post-launch; the editor's
decimal handling notes it). Design-study banner on every mockup frame until
built. Studio is an editor, not a oneview viewer — §3 static fence does not
apply, but §4 (seal never state) binds everywhere.

## 6. Sequencing

Pre-launch (allowed): F-G empty-state affordance + F-H quickstart db note.
Post-launch: this note + agreed mockup → onedoor as ND-055 spec. Mockup built
by core as a labelled design study (P0: S1, S3, S4, S5 mocked with the
payments-pack fixture; S2/S6 stubs) for Shamik's review before any agent
instruction.

Integrity: sha256(body) = 118c61b3cc83712053820b76dc6320619141b3a2f49bb56f8fd3afbfd7a724ca
