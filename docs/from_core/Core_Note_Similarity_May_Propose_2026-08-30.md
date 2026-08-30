# Core Note — Similarity May Propose, Only Identity May Permit
**Date:** 2026-08-30 · **From:** core · **Origin:** Shamik's question, 2026-08-30: how does onedoor check that an incoming action is not an exact match of a stored policy but semantically similar to one?
**Status:** design note, sealed for the record. **It changes no scope**: nothing here enters the 0.7.0 build (ND-056), and nothing here is a build authorization for the items it schedules.

## 1. The ruling, in one sentence

**Similarity may propose; only identity may permit.** Semantic
judgment about what an action "really is" belongs beside the gate —
in authoring, review, and proposal surfaces — and never inside the
decision path, where matching is exact and absence is denial.

## 2. Why the decision path stays exact-match

The tempting design — embed the incoming action, match it to the
nearest stored policy above a similarity threshold — fails three ways
at once:

1. **It makes the verdict testimony.** A similarity score is a
   model's opinion. Putting it in the enforcement path makes the gate
   probabilistic exactly where the product promises evidence, and the
   receipt stops being replayable: "was this correct under last
   week's rules?" is no longer a computation when the answer depends
   on an embedding model's weights that day.
2. **A threshold is a dial an attacker probes.** "How differently
   must I phrase the action before I fall through to a MORE
   permissive neighbor?" is a jailbreak surface built into the
   enforcer. Exact match has no such dial.
3. **The failure modes are asymmetric.** Exact-match fails closed: a
   semantically similar but unregistered action gets default_deny,
   which is recoverable. Similarity-match fails open: a wrongly
   inherited permission executes, which is not.

The engine's one existing "semantic" mechanism shows the honest
pattern: URL effects match after CANONICALIZATION — equality after a
defined, replayable transformation, with malformed-equals-denial.
That is what "semantically equal" means in an evidence product:
never a score, always a declared transform.

## 3. The three lawful mechanisms, beside the gate

1. **Observe-mode as the collector.** Denied and unknown action
   types accumulate in the ledger. A review surface — human first,
   Physician-shaped later — clusters them and says "`send_payment`
   was denied N times and reads close to your `make_payment`
   policy," producing a PROPOSED DRAFT that enters the existing
   draft/ceremony wall. The model proposes the mapping; a human
   ratifies it; the mapping then exists as an explicit, exact,
   receipted rule. Semantic judgment is converted into deterministic
   policy through the approval ceremony, never applied live.
2. **Authoring-time coverage.** The dark-surface list (T3 wall 6,
   constitution principle 4) already surfaces what a description
   mentioned that got no rule. The aliasing problem — same intent,
   different action name — is what the constitution's aliasing
   benchmark measures on the proposer: published cases, published
   misses. The similarity instrument is graded like any other
   instrument, never trusted.
3. **Explicit alias rules.** Where two action shapes should be
   treated as one, the mechanism is a declared alias or
   canonicalization in the policy itself — authored, validated by
   the one parser, ratified in the ceremony, receipted, and
   replayable. An alias rule is exact matching with a longer name
   list, which is why it is admissible where a score is not.

## 4. When (schedule as ruled 2026-08-30, no scope change to 0.7.0)

1. **Shipping in 0.7.0 already (no new work):** mechanism 3's
   substrate (exact match + default_deny + URL canonicalization) is
   the released engine; mechanism 2 ships IF T3 clears its
   published-misses gate by Sept 5, else with T3 in 0.7.1.
2. **First post-launch Studio work (the 0.7.x line, after Sept 12):**
   mechanism 1's deterministic half — a denials/unknown-actions view
   in the Studio grouping repeated denied action types from the
   ledger, with "create draft from this denial" entering the normal
   draft path. No model involved; countable, replayable, cheap.
3. **The post-launch engine line (with the actor-identity work):**
   explicit alias/canonicalization rules as a policy construct —
   loader-validated, ceremony-ratified, additive schema. Engine
   change; proposal-first per house standard.
4. **Physician horizon (post-Moment-2, post-paper-3):** the semantic
   clustering of mechanism 1 — a model suggesting which denials
   resemble which policies — as the first Physician-shaped feature,
   under the Physician walls: BYO instrument, declared and pinned,
   benchmarked with published misses, proposals only, ceremony
   always. Fenced behind the Physician addendum (f1b4af69…) in full.

Any future design note that lets a similarity score into the
decision path is out of order on its face, per the same clause that
guards the Physician wall.

Integrity: sha256(body) = b955de3bce21dfe47841200c77ba72c0dbb70e0c95512664d33fdab628fa947e
