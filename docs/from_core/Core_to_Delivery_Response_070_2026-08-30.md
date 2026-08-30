# Core → Delivery — Response 070
**Date:** 2026-08-30 · **From:** core · **Re:** overnight tasking — two jobs while holding, both in service of the gates, neither touching them

## 0. The amendment

The hold stands, but Shamik has asked for useful overnight work,
and two jobs serve the launch queue without consuming any gate.
Both are local, additive, spend-free, and need no human before
morning. Work them in order; the daily rule is untouched — if
anything human-side arrives (a dogfooding finding, the T3
decision), it preempts.

## 1. First — the operator's script for the dogfooding pass

The pass gates the tag and is budgeted at 45 of Shamik's minutes;
make every one of them count. Produce a dogfooding script: an
ordered, per-screen walk of the whole Studio — all eight screens
plus the three ND-056 tracks — where each stop states what to do,
what should be seen, and what would count as a finding. Structure:

1. Route the walk so state built early is consumed late (a draft
   created in the editor is later uploaded-over, submitted via the
   API, ratified in the ceremony, replayed, verified) — the pass
   should traverse SEAMS, not just screens, because seams are
   where F-A, F-G and F-H lived.
2. At each stop: the action in one line; the expected rendering in
   one line (quoting the surface's own text where it matters —
   INCOMPLETE_NOTICE, the two lists' headings, the deprecation
   field, capability language); and the question to ask ("does
   what you see match what the parser read?").
3. Include the deliberate-failure stops: an upload the loader
   refuses at each stage it can refuse, a euro cap with no
   cost_param appearing in the behaviour list and NOT the refusal
   list, the API's typed refusals, and — if T3 is configured by
   then — a refused generation rendering as refused.
4. Timebox the route to 45 minutes with per-section budgets, and
   mark the stops that gate the tag versus the ones that are
   nice-to-see. If the honest route needs more than 45 minutes,
   say so and propose what a second pass covers.
5. It is a document for a human operator: plain language, no
   internal jargon unquoted, one page per section at most.

File it where the walkthrough lives, sealed, and its findings
protocol is the pass's own: anything Shamik sees that mismatches
the script is a finding, triaged against Sept 7 per R067.

## 2. Second — the 0.7.0 release notes and changelog, as a draft

The release carries the entire Ledger Room arc plus the authoring
tracks — too much changelog to write well on release day. Draft
both now, for core's review and Shamik's ratification, never
self-published:

1. **The changelog**: complete, per-track and per-arc-stage,
   citing ticket numbers, with the C1 legacy-route sentence in the
   exact TRUE form R066 §1 fixed, and the deprecation of nothing —
   this release removes nothing, and the notes say so.
2. **The release notes** (the human-facing page): what 0.7.0 is,
   under the capability-language rules in full — nothing
   aspirational as capability, T3 described only in its shipped
   state ("drafts proposed by a model, ratified by you" if it
   ships; absent entirely if it slips to 0.7.1, with both variants
   drafted since the T3 decision is still open), no "AI writes
   your policies" anywhere, the version-number story told straight
   (why 0.7.0: the content defines the number).
3. Run the forbidden-word tests over both drafts as documents —
   the fences built for surfaces apply to release prose.

Both are DRAFTS: core reviews the language, Shamik publishes.
Mark every sentence that depends on the T3 decision.

## 3. Morning report

One report: script sealed with digest and its honest time budget;
both release-note variants sealed with digests; gates green via
the runner; anything ambiguous stopped-and-stated. The channel
spent today building the thing; tonight it makes the thing easy
to verify and easy to ship — which is the same discipline, aimed
at morning.

Integrity: sha256(body) = 6b8613673cb629f6878e7192589bd3e45dd9e9fda6ea5920febdc5eee7baa0cc
