# Core Forward 006 — Studio Authoring Paths: BUILD DIRECTIVE (pre-launch, parallel)
**Date:** 2026-08-30 · **From:** core · **To:** delivery channel (onedoor)
**Origin:** Shamik's dogfooding finding and his ruling, 2026-08-30: the policy
authoring UX is a MUST-HAVE, built in parallel, in time for launch — not
post-launch agenda. **Status:** channel reactivation + scope; the agent's
implementation proposal comes back before code.

## 0. The finding, in Shamik's frame

Creating a policy should work three ways: (1) upload a policy file or
define it in YAML in an embedded editor that runs dynamic validation;
(2) define policies in natural language in the Studio, which generates
policies and proposes them to humans for approval — post-approval they
are added; (3) a REST API to add policies. Today the Studio offers a
guided/raw editor with on-save refusal and a drafts POST endpoint —
short of all three bars.

## 1. Lawfulness of the timing

The freeze law bars BREAKING changes before Sept 12; every track below
is additive, and the precedent is 0.6.2 (P0 shipped pre-launch as
additive on this exact reasoning). ND-053/054 stay frozen. The launch
critical path (teaser, −02, essay) is Shamik-side and untouched; his
minutes for THIS work are budgeted in §3.

## 2. Scope — three tracks

**T1 · Editor + upload + dynamic validation (additive, first).**
File upload creating a draft (same parser path as every other write).
Live validation in the editor — as-you-type or on-change, not only
on-save — surfacing the FULL loader rulebook inline with positions
and reasons: schema errors, tier-1/2 without compensating_command,
euro caps without cost_param, cost_param absent from bounds.required,
strict_params violations. The rule: nothing the loader would refuse
at boot is first discovered at boot.

**T2 · Policy REST API (additive).** Draft CRUD, rule add/update
within a draft, submit-for-ratification, and version/policy queries —
the same single parser behind every route, refusals typed. **No
approval-by-API pre-Q7**: ratification remains the human ceremony
until actor identity (key_id) exists, because an approval without a
named approver is testimony. The API's docs say so in one sentence.

**T3 · Natural-language authoring (the walls are the feature).**
NL in → a generated draft out, entering the EXISTING draft/ceremony
wall — the motto applied to policy itself: the model proposes, the
policy layer disposes. Binding conditions:
1. The generating model is a **declared instrument** — pinned,
   recorded on the draft it produced ("drafted via <instrument>").
2. Generated YAML goes through the **same single parser** as any
   hand-written draft; a generation the parser refuses is refused,
   shown with reasons, never auto-repaired silently.
3. The ceremony renders **what the parser read, never what the model
   claims** — approve against the schema, not the prose. The approval
   page shows the parsed rules (tiers, caps, bounds) exactly as the
   guided pane would; the model's own summary, if shown at all, is
   labelled as the model's summary.
4. **BYO model endpoint, opt-in, off by default** — no bundled
   credentials, no default provider; absent configuration the feature
   is absent from the UI, not broken in it.
5. Capability language exact on every surface: "drafts proposed by a
   model, ratified by you" — never "AI writes your policies."

## 3. Sequencing, cutoffs, and budgets

1. Agent returns an **implementation proposal** (F046 shape: per-track
   design, tests-first plan, Shamik-minutes itemized, pre-registered
   risks) before code. Core rules on it; Shamik ratifies scope.
2. **Feature-complete bar: Sept 5.** Ship as **0.6.3 by Sept 7**
   (Shamik publishes; his credentials, his hands).
3. **T3 quality gate**: if the NL track has not cleared its review by
   Sept 5, T3 alone slips to 0.7.0 as fast-follow — it never drags T1
   and T2, and nothing half-tested ships into launch week.
4. Launch copy changes only for what actually shipped, under the
   capability-language rules.
5. Daily rule: Shamik's launch tasks outrank this work every day it
   competes; if a review waits a day, it waits.

## 4. Standing fences

Additive only; the freeze on breaking changes holds; oneview
compliance (viewers static where the spec says so; seal gold = brand
only); tests-first per house standard; the dogfooding walkthrough
gains sections for each shipped track; user manual updated to match.
Nothing here touches forensics capacity or the Reranker Campaign —
the two channels run in parallel and share nothing but Shamik, whose
minutes both must budget.

Integrity: sha256(body) = f20677b3955b4985e400dca917231316213ee8e63ff16b333bd3786f4f511cfa
