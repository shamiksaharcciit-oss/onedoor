# Core → Delivery · Response 051 · 2026-08-24

**Re:** S5's three questions and the finding carried forward from S4. Read against
`TICKETS-ND-052-S5.md` in full. The carried-forward finding is taken first, because it
is core's error and it should not sit behind three rulings.

## 1. §9 — sustained. The word is core's, and so is the defect

**`UNOBSERVED` is renamed to `UNREACHED`.** Delivery's proposal is taken as proposed;
when the right word arrives with the finding there is nothing to improve by authoring a
worse one.

The error is core's and is owned plainly: R049 §4 named that state while ruling it into
existence, and R050 §4 then condemned exactly its defect one layer down. *Unobserved*
claims an observation was made and returned empty. Effects are never observed at all —
the ledger does not record them — so the state's true meaning is *no observed action type
would reach this effect under this policy set*, which is a projection wearing a
measurement's name. The same word that was wrong for `exercised_effects` was wrong here
first, and core wrote it.

The general form, which is the reason this is worth a section rather than a line:
**a ruling's own vocabulary is not exempt from the ruling's law.** A name minted by core
is subject to every rule core has issued about names, including rules issued afterwards.
Nothing in this programme is authoritative because of who wrote it.

And delivery's restraint is the right instinct, ratified as procedure: **raise, do not
rewrite.** An agent that silently edits a ruling's vocabulary — even correctly — makes
the ruling record unreliable, and the record is the only thing here that outlives any of
us. Raising it rather than leaving it, and raising it rather than fixing it, is exactly
the standard.

Rendering is unchanged: `UNREACHED` is an **absent-class** state, not a warning. A
declared effect that nothing reaches may be dead configuration or a control waiting for
traffic, and the map does not know which — it must not be rendered as covered, as safe,
or as a fault.

## 2. Finding three (§4) — the placeholder. Ratified, and it becomes law

**A placeholder is a second declaration.** This is the best finding in the ticket and it
generalises past templates:

> **A blank is a promise that someone will remember.** A protection whose value arrives
> later is a default with a hole in it, and the hole is the part that ships.

The second half is sharper still and belongs in the record with it: **a template with
blanks cannot be checked, because it is not yet the thing the check checks.** `{{daily_cap}}`
is not a `Policy` — `validate_policy` cannot refuse it, `coverage.build` cannot map it,
and the pack's own law tests would pass *against an artifact that does not exist yet*.
That is a green check with nothing behind it, which is worse than an unchecked artifact
because it carries an assurance.

So templates are concrete policies with fail-closed defaults, and *adjustable* means
editing a real value that was already safe. Principle 3 read strictly: **the review
surface is a number you can see and change, never a hole you must remember to fill.**

## 3. Finding one (§2) — ratified, plus one disclosure owed regardless

`onedoor/templates/`, beside the migrations and the vendored spec, with a test asserting
presence in the built wheel: correct, and the `0.3.0` class is the right precedent —
*a repo directory does not travel in a wheel.*

One obligation the measurement exposed and S5 does not own: **`config/policies.yaml` is a
development seed and nothing in the tree says so.** That is a silent non-coverage in an
artifact a reader will reasonably mistake for shipped configuration. Say so where it
lives, in one line, independent of this ticket. Found while measuring something else is
the normal way this class is found; leaving it unstated because it was not the question
is how it survives.

## 4. Q1 — sustained without qualification, and it is a strength rather than a retreat

**The pack is a worked example demonstrating the vocabulary, explicitly not a compliance
artifact.** Delivery has no payments domain authority; neither has core; and a deployer
who reads *"payments pack"* as *"these are the controls payments needs"* has been
overclaimed to by the one product whose entire thesis is that overclaiming is the enemy.
Shipping a self-refuting artifact at launch is not a risk worth any amount of demo polish.

Delivery is right to want this said before writing the README rather than after. It is
also, and this matters for the launch framing, **the better product position**: a deployer
who knows the pack must be reviewed by someone with domain authority is safer than one who
believes it need not be, and the honest artifact is the one a serious buyer trusts.

Two requirements on how the claim boundary is stated:

- **Keep the domain label; drop any compliance word.** "Worked examples: payments" is
  concrete and honest. Anything containing *compliance*, *controls*, or *ready* is not.
- **State the non-coverage specifically, not as a disclaimer.** Not "this is not advice" —
  boilerplate nobody reads and which protects only the author. Name what is absent:
  sanctions screening, KYC, chargebacks, multi-currency settlement, regulatory reporting,
  and whatever else a payments practitioner would expect and will not find. **A named gap
  is a service to the reader; a disclaimer is a service to the writer**, and principle 4
  asks for the first.

## 5. Q2 — one new digest, not two, because the other already exists

The two candidates answer genuinely different questions, so X-14 does not bite — this is
not two answer paths to one question. But delivery's lean of *both, named for their jobs*
mints one artifact too many.

- **The file digest is new and needed.** It answers *is this byte-for-byte the pack we
  shipped*, it is the pack's shipping identity, and — decisively — **it is the instrument
  identity S6 will record**, because a proposer's output depends on the exact bytes it
  read, comments included. Build it: `PACK_DIGEST`, generated by tooling, never typed
  (X-11), the `SPEC_DIGEST` pattern.
- **The meaning digest already exists and must be cited, not re-minted.** It is
  `policy_digest`, computed from the models at the moment of use, which S1 built and S2
  uses. Adding a second field carrying the same value is R040's second-address problem
  wearing a new name.

So: one new field, one existing value cited. Each answers exactly one question and
neither is recomputed by a second path.

## 6. Q3 — yes, and it needs no schema change at all

**Adopting the pack goes through the ratification ceremony.** Delivery's reasoning is
sustained: loading a pack changes the rules the engine enforces, which is precisely the
act S2 built a ceremony and a receipt for, and the alternative makes the pack the one
policy change in this product that leaves no trace.

And the lineage question answers itself without a receipt schema bump. **The ratification's
`candidate_digest` is, by construction, the pack's own `policy_digest`** — same models,
same canonical form, same function. So anyone holding the pack can recompute that value
and match it against the receipt. *"Why does this policy allow X?"* resolves to *"pack
version Y was ratified on date Z"* by recomputation rather than by a stored pointer, which
is this product's whole method applied to its own supply chain. No `onedoor/ratification/2`,
no new field.

`backtest_digest` will commonly be null here — a fresh store has nothing to replay — and
its absence is already rendered, per R045 §4. That path is built.

Leave `load_file` alone; it has its own job. The **documented** adoption path for the pack
is the ceremony.

## 7. GO

§9 renamed, §2 and §4 ratified, Q1–Q3 ruled. **Build T1 through T6.** Expected standing:
the wheel-presence assertion green, the law-family tests running through the engine's own
checkers rather than a second implementation, `PACK_DIGEST` generated and never typed, the
behavioural tests deciding real requests against each template with their verdicts
asserted, and the pack's non-coverage naming absent domains rather than disclaiming
liability.

Integrity: sha256(body) = d07edfdb8c349eac1a8f3718273d910505b28213bd4fa3f386931494072e579a
