# Design Note — The Policy Studio (core feature, post-launch flagship)

**From:** core · **To:** onedoor delivery (for ticketing) + strategy shelf
**Date:** 2026-08-22 · **Status:** Design constitution, ratified by Shamik.
Sequencing unchanged: after the crypto epic; untouched before launch. Ticket
as an epic with the next free ND number; the constitution below binds every
sub-ticket.

## 1. What it is

The user describes their problem, domain, and AI landscape in natural
language. The system derives a complete candidate policy set — with named,
adjustable parameters — and proposes it for review and ratification. Elevated
by Shamik from GUI-epic component to **core product feature**: the strong
deterministic core exists; the Studio is how humans reach it.

## 2. The constitution — five principles, each a programme rule in product clothes

1. **The proposer is never the enforcer.** The LLM emits a candidate policy
   document and nothing else; it is structurally outside the decision path,
   permanently. Only a human-ratified canonical artifact (hashed into
   `version_hash`) is ever active. Runtime enforcement stays deterministic
   and model-free.
2. **The explanation derives from the artifact, never the model's memory**
   (X-11 for policies). Plain-English renderings of rules are generated from
   the compiled canonical form. The drafting model does not narrate its own
   output.
3. **Adjustable parameters are the review surface; defaults are
   fail-closed.** Proposals arrive as named dials (caps, windows, tier
   floors, effect classes), every default conservative. R027's rule binds
   the generator: it may never emit a rule whose safety depends on an
   optional second declaration.
4. **Non-coverage is stated, never silent** (three-outcome for drafting).
   Every proposal ends with the dark-surface list: what the description
   mentioned that got no rule, and why. A policy set that does not declare
   its gaps is an E11 violation in product form.
5. **The derivation gets a receipt.** Description frozen as received bytes;
   model + prompt + template pack recorded as the instrument; proposal,
   edits, and ratification chained. "Why does this policy allow X?" is
   answerable years later by provenance, not memory.

**Grounding:** the generator drafts against per-vertical template packs
(Addendum 004 GTM inventory), never from a blank page.

## 3. The experience layer — flashy, but every flourish principled

- **Conversational intake.** The Studio asks clarifying questions rather
  than guessing — "you mentioned refunds; is there a monthly cap as well as
  a daily one?" Honesty as UX: unanswered questions land in the dark-surface
  list, not in invented rules.
- **Live policy canvas.** As the description evolves, rule cards materialise
  — each showing the plain-English meaning (derived per principle 2), the
  canonical form on flip, and its dials inline.
- **The backtest — the killer flourish.** Before ratification, the draft
  policy replays against the *actual audit ledger* (or synthetic scenarios
  for day-one users): "under this policy, yesterday's 214 actions: 209
  allowed, 3 sent to approval, 2 denied — here they are." Deterministic
  engine, dry-run, receipts-native — a what-if no competitor can fake
  because it requires the append-only ledger we already keep. The single
  most demo-worthy moment in the product.
- **Coverage map.** The dark-surface list as a visual: effects mentioned /
  covered / uncovered, uncovered rendered prominently — the honest gap as a
  first-class UI element.
- **Ratification ceremony.** Diff against the active policy, the hash shown
  becoming the new `version_hash`, the provenance receipt issued on
  signing — the Oneview seal, stamped. Make ratification feel like signing,
  because it is.
- **Explain-this-decision.** From any decision receipt: "why?" answered in
  plain language derived from the canonical policy artifact (principle 2),
  never from a model's recollection.
- **Drift proposals (later phase).** "Your traffic shows a pattern your
  policy doesn't address — here is a proposed amendment," arriving as a new
  Studio proposal with its own receipt, ratified like any other. The
  Studio's loop becomes continuous, and every iteration stays human-signed.

## 4. Competitive posture

veto.so sells plain-English single rules; Amazon's VERAFI paper explores
neurosymbolic policy generation. Neither receipts the derivation, neither
declares non-coverage, neither backtests against an append-only ledger.
The Studio's pitch line: **"Describe your world. Ratify your rules. Every
step receipted."** One vision slide in the launch deck, labelled roadmap;
no code before launch.

## 5. Acceptance posture (for the eventual epic)

The generator is benchmarked like every instrument (aliasing-benchmark
pattern: published cases, published misses); principle-violations are test
classes, not review notes — a proposal whose safety depends on an optional
declaration must fail CI, not review. The Studio ships when the five
principles are enforced structurally, or it does not ship.
