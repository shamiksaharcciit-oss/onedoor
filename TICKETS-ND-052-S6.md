# `ND-052` / **S6** — the proposer · decomposition

**Epic:** `ND-052`, the Policy Studio. Pre-launch, demo-grade (R036).
**Ticket:** S6, **last** in the normative build order, landing on the spine S1–S5 proved.
**Baseline:** `9f9822b`; four gates green via `python -m scripts.gate --all`, 806 passed.
**GO to decompose:** R052 §3. **Not yet GO to build.**

---

## 1. The two constraints on the ticket's face

R052 §3 put these here rather than leaving them to be discovered mid-build.

**R036 governs S6 directly.** The Studio never gates the launch, and **S6 demos only if
its output is real, its derivation receipted, and its limits stated**. Every number it
shows is produced by an engine function; every receipt is genuine; and every limit
survives to the surface — the fixture label, the coverage gaps, the uncovered columns,
all of it.

**The proposer is a proposer.** Constitution principle 1 arrives here with maximum
temptation: *a thing that drafts policy must have no path to enacting it except the
ceremony S2 built* — preview equality, compare-and-swap, receipt — and its output enters
that ceremony **as a candidate like any other**, `candidate_digest` and all. **If S6 can
touch the active set by any route that is not the ceremony, S6 is wrong by
construction.**

## 2. What is settled, and cited rather than rebuilt

| S6 needs | It exists as |
|---|---|
| A candidate's identity | `backtest.policy_digest` (S1) |
| Somewhere to put a draft | `studio.store` — `studio.db`, drafts, `base_version` pin (S3) |
| Validation that collects | `studio.validate.problems`, wrapping `validate_policy` (S3) |
| The only way to enact | `studio.ratify.ratify` — preview equality, CAS, receipt (S2) |
| The dark-surface list | `studio.coverage` — four states, ranked by behaviour (S4) |
| The instrument's template half | `templates.PACK_DIGEST` (S5) |
| "Is this claim recomputable?" | the citation/receipt distinction (R049 §5, R050 §4) |

S6 writes **none** of that. It produces a candidate and hands it to machinery that
already exists — which is what "landing on a proven spine" means in practice.

## 3. Finding one: this is the first thing in onedoor that calls a model

Measured, not assumed: nothing under `onedoor/` calls any model today. `Source.LLM` is a
**label for who requested an action**, not a dependency. The engine is offline and
deterministic end to end, and `docs/` says so.

So S6 introduces a genuinely new kind of component, and three properties have to hold or
the engine loses something it currently has:

- **An optional extra, never a runtime dependency.** A library user who never proposes
  must not carry a model client — `[signed]`'s shape, and X-6's reading: **hard at the
  point of use**, refused with a message naming the remedy.
- **Never on the decision path.** Nothing the engine consults when deciding may reach a
  model. This is principle 1 mechanically, and it should be a **structural test** in the
  shape of `test_every_audit_write_path_stamps_the_chain`: the decision path's import
  closure must not contain the proposer.
- **The suite must stay runnable with no model at all.** CI has no key and must never
  need one. That forces §4's question.

## 4. Finding two: a proposal receipt cannot promise what every other receipt promises

This is the sharpest thing in the ticket and it needs settling before T1.

Every receipt this product emits is **recomputable** — that is what makes it a receipt.
A backtest replays and gets the same answer. A ratification's hash is reproduced by
`record_snapshot`. A coverage map is a pure function of two addressed inputs, which is
exactly why R049 §5 made it a *citation* instead.

**A proposal is not recomputable.** Run the same description through the same model twice
and you may get different policy. Recording `model + prompt + PACK_DIGEST` pins the
*conditions*; it does not make the *output* re-derivable, and no amount of instrument
recording will.

So a proposal receipt attests **what was produced from what** — provenance — and not
*that it would be produced again*. Those are different claims, and this programme has
just spent three memos establishing that **a name which claims more than the computation
delivers is the defect** (R050 §4's `exercised_effects`, R051 §1's `unobserved`).

Calling it a "receipt" alongside artifacts that *are* recomputable invites exactly that
misreading. §7's first question asks core to settle what it is called and what it says on
its face.

## 5. Finding three: the description is received data

The operator's natural-language description is **input to a derivation that gets a
record**, which makes it E10 material: **frozen byte-for-byte as received, never
normalised.** No whitespace stripping, no Unicode normalisation, no line-ending
translation, and no formatter anywhere near its storage path.

That has teeth beyond the docstring. If any description is ever committed as a fixture it
needs a `.gitattributes` `-text` fence with the rationale written into the file — the
three-layer discipline that already fences the vendored spec. A description silently
CRLF-translated by git on a Windows checkout would change the instrument's input without
changing anything anyone could see.

## 6. Finding four: "mentioned" is a model claim, and the coverage map holds measurements

S4 found that the design note's *mentioned / covered / uncovered* had no source for
"mentioned" until the proposer existed, and R049 §4 said the description would later join
as **a third source**. S6 is that source — so the dark-surface list is `coverage.build`
plus mentioned-but-unruled rows, not a second mechanism.

**But the row kinds are not alike, and merging them would dilute the map's honesty.**
Today every coverage row is derived from the **store and the ledger** — things that
happened or are declared. A "the description mentioned refunds and no rule covers it" row
is a **model's reading of a sentence**. Both are worth showing; only one is a
measurement.

`declared_inert` is a fact about the engine's behaviour. *Mentioned-but-unruled* is a
claim about what someone meant. Rendering them as peers would let a model assertion
occupy a measurement's row, which is the overclaim this map exists to prevent — §7's
third question.

## 7. The questions this decomposition surfaces

**1. What is a proposal record called, and what does it say on its face?** (§4.) Delivery
proposes it is **not** called a receipt — something like a *derivation record* — carrying
its own schema, the instrument (model id and version, prompt digest, `PACK_DIGEST`,
sampling parameters), the frozen description's digest, the resulting `policy_digest`, and
**an explicit statement that it is not re-derivable**, in the shape of S4's
`PROJECTION_NOTE`. Against delivery's own lean: principle 5 says *"the derivation gets a
receipt"* in those words, so renaming it is a departure from the constitution's language
and that is core's to approve, not delivery's to assume.

**2. How is the model supplied, in tests and in demos?** Delivery proposes an injectable
proposer interface with two implementations: a **deterministic fixture proposer** for CI
(no key, no network, reproducible) and a real client behind an extra. And — the part that
matters — **which one produced a candidate is recorded in the record and hashed**, exactly
as `ledger_provenance: live | fixture` is hashed into a backtest receipt, so a
fixture-produced proposal cannot be presented as a model's work. Delivery is confident
about the mechanism and asks core to name the field, since it is the same decision
`ledger_provenance` was.

**3. Where do mentioned-but-unruled rows live?** (§6.) Delivery leans **adjacent, not
merged**: the coverage map keeps holding measurements, and the proposal's dark-surface
list is its own rendering that cites the map rather than adding rows to it. Against that:
principle 4 asks for *one* honest gap list per proposal, and two adjacent lists is two
places to look. Delivery does not think a reader is served by a map where some rows are
measured and some are inferred, but the cost is real and the call is core's.

**4. What is the benchmark, and what counts as a published miss?** The design note
requires the generator be benchmarked like every other instrument — *published cases,
published misses* — and delivery reads that as blocking the demo rather than the build. A
generator with no published misses is claiming perfection, which for a language model
writing security policy is the least credible claim available. Delivery can build the
corpus and the harness; **what threshold, if any, gates the demo is core's** — and R036
already says the Studio never gates the launch, so a failed threshold delays a demo, not
a release.

## 8. Work order

- **T1** — the proposer interface and the fixture implementation (pending **Q2**).
- **T2** — the description store: received-bytes discipline, digest, `.gitattributes`
  fence if fixtures are committed (§5). Unblocked.
- **T3** — the derivation record (pending **Q1**).
- **T4** — the structural test that the decision path cannot reach a proposer (§3).
  Unblocked, and worth landing early: it is the one that keeps principle 1 true while the
  rest is built.
- **T5** — the dark-surface rendering (pending **Q3**).
- **T6** — the benchmark corpus with published misses (pending **Q4**).
- **T7** — the law tests: a proposed candidate passes **every** check a hand-written one
  passes, with **no privileged path** — the generated-policy half of Q3's law, and the
  place R027's rule about the generator finally has a generator to bind.

T2 and T4 are unblocked. T1, T3, T5 and T6 wait on their questions.

## 9. One property worth stating before it is built

**A proposer's output is untrusted input.** The description is operator-supplied text
handed to a model that emits policy, so a description crafted to talk a model into a
permissive rule is an obvious attack and the honest answer is that **nothing here relies
on the model refusing**. The candidate passes the same validator, the same law tests, the
same coverage map and the same human ratification as any other — and the fail-closed
defaults mean a rule the model got wrong is a rule that refuses rather than permits.

That is the whole reason the proposer is built last and the ceremony was built first.
