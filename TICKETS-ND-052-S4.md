# `ND-052` / **S4** — the coverage map · decomposition

**Epic:** `ND-052`, the Policy Studio. Pre-launch, demo-grade (R036).
**Ticket:** S4, fourth in the normative build order, on the canvas S3 just proved.
**Baseline:** `0.5.0` published; tag `v0.5.0` @ `fef596e`, 719 passed / 9 skipped.
**GO:** R048 §4.

---

## 1. What S4 is, and the one line of the design note that decides its shape

> **Coverage map.** The dark-surface list as a visual: effects mentioned / covered /
> uncovered, uncovered rendered prominently — the honest gap as a first-class UI element.

It is constitution **principle 4** wearing product clothes — *non-coverage is stated,
never silent* — which is the three-outcome rule applied to drafting, and E11's dark
surface in a form a deployer can look at.

Carried in as settled, and cited rather than re-argued: the canvas edits candidates and
touches nothing else; **every number is produced by an engine function**; Oneview is the
design system, state colours are verdicts' alone (R046 §3, and see §6 below, where that
last one turns out to be the hard question of this ticket).

## 2. Finding one: "mentioned" has no source yet — and the ledger is a better one

The design note's three columns are *mentioned / covered / uncovered*. **"Mentioned"
comes from a description the proposer reads, and the proposer is S6 — last.** S4 lands
four tickets before its own input exists.

That is not a blocker; it is a redirection, and toward something stronger. **The ledger
already records what the world actually asked for.** An action type that arrived and was
`default_deny`-ed is an uncovered surface the *world* named, measured rather than
inferred from a paragraph. It is available today, it needs no model, and it is a better
class of evidence than a language model's reading of a sentence: a description says what
someone remembered to write down, and the ledger says what actually happened.

So S4 computes coverage from two sources it has:

- **the policy set** — the candidate or the active set: what is declared;
- **the ledger** — what arrived, what was default-denied, which effects actually resolved.

When S6 lands, the description's "mentioned" list becomes a **third source joining
these**, never a replacement for them. A gap the ledger measured outranks a gap a model
inferred, and the map should keep them distinguishable rather than merging them into one
"uncovered" bucket.

## 3. Finding two: a declared effect with no effect policy behind it is silent today — measured, not hypothesised

`decision.py` resolves effect policies like this:

```python
effect_policies = [ep for e in effects if (ep := store.get_effect(conn, e)) is not None]
```

An effect a policy **labels** but which has no `effect_policies` row is **silently
dropped**. The label contributes nothing: no tier floor, no effect caps.

Run rather than read, on `0.5.0`:

```
label with NO effect_policies row       -> PERMITTED, effective_tier 1
same policy, effect policy now declared -> proposed,  effective_tier 3
```

The same request auto-executes in the first case and goes to a human in the second. The
only difference is a row the policy author may believe they wrote.

**This is principle 4's exact target and it exists today, in hand-written policy, with no
LLM anywhere near it.** It is also the most dangerous state the map can show, and §6
turns on that fact.

## 4. Finding three: two states are not enough — there are four, and one of them is *absent*

*Covered / uncovered* is two, and R010 has been paid for too many times on this
programme to spend it here:

| State | Meaning | What it produces at decision time |
|---|---|---|
| **covered** | a rule declares it, and every effect it names has an effect policy | the rule's tier, floors and caps apply |
| **declared but inert** | a rule names an effect with no effect policy behind it (§3) | the label does nothing — a **silent permit** |
| **uncovered, observed** | the ledger saw this action type; no rule declares it | `default_deny` — a **loud denial** |
| **unobserved** | neither declared nor ever seen | **nothing is known**, and that is the finding |

**Unobserved must never render as covered or as safe.** It is *absent* — the state about
which no measurement exists — and folding it into either neighbour is the failure the
three-outcome rule exists to prevent. A map with three colours and four states will pick
a neighbour for the fourth, so the four are named in the model before anything renders.

## 5. Finding four: a coverage map is a measurement, so it states its window and cites its range

"Coverage over the ledger" without saying *which span of the ledger* is a dashboard
number — and the category to avoid is dashboards. S1 already built the right shape:
`CitedRange`, the sealed span with `row_hash_at_last_seq`, which is how a backtest proves
it saw real data by citation.

The coverage map reads the same ledger and should cite it the same way. A map that says
*"3 of 11 effects uncovered"* without naming the range it counted over is an assertion;
one that names it is a measurement someone else can repeat.

## 6. The question this ticket turns on, stated before §7 because it shapes T5

**S3's colour rule and the design note's "uncovered rendered prominently" collide, and
the danger ordering is inverted from the obvious reading.**

The reflex is red for *uncovered*. But look at what the four states actually produce:
*uncovered, observed* produces a **denial** — the engine refuses, loudly, and the
operator finds out. *Declared but inert* produces an **allow** that the policy author
believes is governed. **The state that most needs the eye is the one that does not
produce a verdict at all**, and the state the reflex would paint red is the one the
engine already handles safely.

Painting uncovered red and inert not-red would rank the map's warnings in exactly the
wrong order, using the one colour pair that means something else.

## 7. Work order

- **T1** — the coverage model: the four states of §4, computed from the policy set.
- **T2** — the ledger source: observed action types and resolved effects, over a cited
  range in S1's shape.
- **T3** — the declared-but-inert detector (§3). Unblocked as a *finding*; its second
  half waits on **Q3**.
- **T4** — receipt or view (pending **Q2**).
- **T5** — the Oneview rendering, with prominence resolved (pending **Q1**).

## 8. The questions this decomposition surfaces

**1. Does "uncovered" earn the semantic pair?** §6 is delivery's analysis; the ruling is
core's because it sets precedent for onewatch and onetrace too. Delivery leans **no —
prominence without `--ok`/`--bad`**, by size, position, weight and `--seal`. Two reasons:
state colours are verdicts' alone and a coverage state is not a verdict; and the map's
most dangerous row is *declared but inert*, which produces an allow, so spending red on
*uncovered* would paint the safer state louder than the more dangerous one. Against
delivery's own lean: an uncovered action type genuinely **is** default-denied, so red
would not be a category error the way green-for-added was — it would be pointing at a
real verdict. Delivery is not confident enough to set a cross-product precedent alone.

**2. Is a coverage map evidence, or a view?** S1 and S2 both emit receipts, and this
product's thesis is that claims get receipts. But a coverage map is derived **entirely**
from state that is already content-addressed — the policy snapshot's `version_hash` and
the ledger's sealed chain — so minting a `coverage_digest` would be a second address for
facts that already have one, which is what R040 forbade at the preimage and R045
sustained at the preview. Delivery leans **a view that cites** (§5), not a new receipt.
The counter-argument delivery cannot dismiss: the moment a coverage map is shown to an
auditor or a customer as *"these are our gaps"*, it becomes a claim someone relies on,
and this programme's answer to a relied-upon claim has never been "trust the screen".

**3. Should a declared-but-inert effect be a validator refusal, not just a map entry?**
The epic's acceptance posture (§5 of the design note) is unusually strong — *principle
violations are CI failures, not review notes* — and R027's rule binds the generator:
**it may never emit a rule whose safety depends on an optional second declaration.**
Finding two is that exact shape, in **hand-written** policy: `effects: [money.egress]` is
a rule whose safety depends on a second declaration that may simply be absent.

If that rule binds policy generally and not only the generator, then
`policy_loader.validate_policy` should **refuse** a policy naming an effect with no
effect policy — which is a **change to engine behaviour and to what a deployment will
boot with**, so it is not delivery's call. Delivery notes only that it would be
fail-closed in the same direction as the `cost_param`-must-be-required rule already in
that function, which came from the same class of defect. **Escalating rather than
implementing**, per the standing discipline.

T1 and T2 are unblocked. T3's detector is unblocked; whether it also refuses waits on
Q3. T4 waits on Q2, T5 on Q1.
