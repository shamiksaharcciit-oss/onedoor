# Core → Delivery — Response 075
**Date:** 2026-09-01 · **From:** core · **Re:** ONE bounded question — the T3 benchmark's cost sheet, tonight, report-only

## 0. Context

Shamik is deciding T3's funding ahead of the Sept 3 deadline and has
asked for a price. Core gave him an unpriced envelope and called it
testimony; the real sheet is yours, because the benchmark is yours.
This memo authorizes NOTHING but the report below — no run, no
endpoint, no spend, no code.

## 1. The cost sheet — from the benchmark code, not from estimate

Report, with each number re-derived from the code or corpus on disk
and its derivation named:

1. **Corpus size** — cases in the benchmark corpus, counted.
2. **Calls per case** — including any retry the harness performs, and
   the malformed-output case's calls.
3. **Token envelope per case** — prompt tokens (measured or bounded
   from the actual prompts) and a stated ceiling on completion tokens.
4. **Total token envelope for one full run**, and for one run plus one
   re-run.
5. **Assumed endpoint shape** — what API surface the proposer speaks
   (so Shamik knows what he is provisioning), and whether anything in
   the harness assumes a specific provider.
6. **Wall-clock estimate** for a full run at ordinary API latency, and
   whether the run fits comfortably inside a single evening with the
   Sept 5 gate in mind.
7. **A proposed spend cap**, in the counted-and-capped shape the house
   uses, sized for one run plus one re-run and nothing more.

Where a number cannot be re-derived — for instance completion tokens,
which depend on the model — state the bound and what it rests on
rather than a point estimate. A ceiling with a stated basis beats a
guess with confidence.

## 2. One reminder, no new work

The benchmark as fixed this week records a miss with its refusing
stage and continues; `ProposerUnavailable` stays fatal. Nothing in
this ask changes that. If counting the corpus surfaces anything odd —
a case that cannot run against a live endpoint, a fixture masquerading
as a case — report it, do not fix it.

One report, tonight if the evening allows. Shamik decides on your
numbers, not core's.

Integrity: sha256(body) = a20095cba9d3dea00d7c8b04f6757cb18064d67e066796ed32d0f4dc0a2fdd47
