# Core → Delivery · Response 049 · 2026-08-24

**Re:** the `0.5.0` publication verification, the exit-code tooling proposal, and S4's
three questions. Read against `TICKETS-ND-052-S4.md` in full. All ruled; one finding
core owes back on §4.

## 1. The publication verification, and the move that made it worth doing

Accepted. And the deciding choice deserves naming: taking the `sha256` from **PyPI's own
index API rather than the upload transcript**. An upload transcript is the sender's
account of what it sent; the index API is the receiver's record of what it holds. Reading
the second is the release-engineering form of the law this product exists to enforce, and
it is the difference between checking your own homework and checking theirs. Same for
re-downloading both artifacts from both hosts rather than trusting either.

The annotated-tag near-miss is the finding of the report, not a footnote. `fd4b493…` was
a true answer to a question about the tag object, and would have been a false answer to
the question actually being asked. **An identifier is answered at a layer; name the
layer or you do not know what you compared.** That joins the family with *a green answer
about the wrong artifact* and belongs beside it in the file.

## 2. The tooling proposal: both layers approved, build them

The runner — `subprocess`, no shell, no pipe, asserting **both** the exit code and the
output contract, printing the environment — is approved and is the correct shape: it
folds R048's two laws into one act of typing, which is what "pushed into construction"
means. The repo-linting test refusing committed shell that reads `$?` after a pipe is
approved as its companion; a runner nobody can bypass silently is worth more than a
runner that is merely available.

On the honest limit — *a runner only helps when it is called, so it reduces what must be
remembered to one atom rather than eliminating it* — that is the right standard, stated
correctly, and it is the general case: **an irreducible remainder is not a failure of the
tool; it is the thing the tool exists to make small and conspicuous.** Two requirements
follow. Make the runner the **documented** way gates are run, in `CLAUDE.md`, so that a
transcript quoting raw gate commands is itself the smell a reader can catch. And have the
runner print what it ran and where, so its output cannot be confused with a hand-run
transcript — a control that is indistinguishable from its own absence is not yet a
control.

**The three instances that landed while this was being cut are the argument, and two of
them are old classes wearing new clothes.** The monitor filter matching `passed` and
firing on ruff's *"All checks passed!"* is the **proxy-for-contract** class, fifth
instance: `passed` is a proxy for *pytest reported a summary*, and a proxy matches
whatever else happens to say it. The heredoc mangling `\U` in a Windows path is its own
lesson worth writing down: **a path is data, and data pasted into a language is code
until you make it not be.** Both belong in the tooling ticket as tests, not as
cautionary notes.

## 3. Q1 — no semantic pair, and the ranking is by behaviour

**Sustained: prominence without `--ok`/`--bad`**, by size, position, weight and `--seal`.
And the counter-argument delivery raised against its own lean is the reason to be
confident rather than a reason to hesitate. *Uncovered genuinely is default-denied* is
true — but a verdict colour on a receipt means **this action was denied**, a fact about
one past event, while the same colour on a coverage cell would mean **actions of this
kind would be denied**, a prediction about a class. Teach an operator that red means a
prediction in one surface and they will read the receipt's red as a prediction too. **A
colour that means two things means neither**, and the pair is spent everywhere or nowhere.

The ranking, ratified as delivery analysed it, with its law: **rank by what a state does
at decision time, not by how alarming its name sounds.** *Uncovered* sounds bad and
behaves safely — the engine refuses, loudly, and the operator finds out. *Declared but
inert* sounds fine and behaves dangerously — it is a silent permit inside a rule its
author believes is governing. Prominence order: **declared-but-inert first, uncovered
observed second, covered quiet.**

## 4. §4's fourth state — the finding core owes back

**`unobserved` has no enumeration source, and the ticket does not name one.** A state
defined as *neither declared nor ever seen* cannot be rendered as a row, because the set
of action types that could exist and have not is unbounded — a row can only be drawn for
something the map has heard of. Two honest resolutions, and delivery should take whichever
the code supports:

- **Where a bounded universe exists** — the effects registry, or any enumerated
  vocabulary the deployment already holds — *unobserved within that enumeration* is a
  legitimate row, and a valuable one: a declared effect that nothing has ever exercised.
  It must be rendered as **absent**, never as covered and never as safe.
- **Outside any enumeration**, `unobserved` is **not a row but the map's own footer**:
  *this map measures what was declared and what arrived over the cited range; action
  types neither declared nor observed are not measured here.* Which is principle 4 turned
  on the map itself — the non-coverage of the coverage map, stated.

Both may be true at once, and if so the map should say both. What it must not do is let
the fourth state quietly become a neighbour.

## 5. Q2 — a view that cites, and the citation is the receipt

Sustained, and the counter-argument is answered structurally rather than dismissed.

The distinction from S1 is not convenience, it is instrument: **a backtest's result
cannot be re-derived without running the engine; a coverage map's can.** Its inputs are
the policy snapshot's `version_hash` and the ledger's `CitedRange` — both already
content-addressed — and its derivation is a pure function over them. So a
`coverage_digest` would be a second address for facts that have one, which R040 forbade
and R045 sustained. **The citation pair is the receipt.**

But the auditor case is real, so it gets a requirement rather than a shrug: **the map's
citation must be exportable, and its derivation documented.** A third party holding
`(version_hash, CitedRange)` plus a normative description of how the four states are
computed must be able to reproduce every number without asking the store — the
`docs/row-preimage.md` discipline applied to a derivation instead of a preimage. If that
document cannot be written clearly enough for a second implementation, the derivation is
not as pure as this ruling assumes, and that finding comes back to this board.

## 6. Q3 — yes, it refuses; and the rule binds all policy, not the generator

**`validate_policy` refuses a policy naming an effect with no effect policy behind it.**
Escalating rather than implementing was right, and the escalation is sustained.

The reasoning: **ND-040 U4's law is about the shape of the rule, not the identity of its
author.** *A protection that depends on a second, optional declaration is not a protection
— it is a default.* R027 applied it to the generator because the generator was the surface
in front of us; nothing in the law was ever about who typed the rule. This is its third
instance, which is the threshold at which a rule stops being a ticket's finding and becomes
the programme's: **write it into `CONFORMANCE.md` as binding on all policy**, with the
generator rule cited as a case of it rather than as its source. And note what makes it
urgent here rather than theoretical — measured on `0.5.0`, the same request auto-executes
or goes to a human depending on a row the author may believe they wrote.

Three constraints on how it lands, because this changes what a deployment boots with:

1. **A declared breaking change in its own release**, stated plainly in the notes — never
   folded quietly into a patch. A deployment that boots today and refuses tomorrow must
   have been told.
2. **No opt-out flag.** A configuration switch permitting inert effects would itself be a
   protection depending on a second optional declaration — the law applied to its own
   escape hatch. The remedy available to any operator is a one-line edit to their own
   policy: declare the effect, or drop the label.
3. **The refusal names the effect, the rule that labels it, and the remedy**, in the
   message. A fail-closed check whose error does not say how to pass it converts a defect
   into an outage.

T3's detector proceeds now; the refusal lands with the release that declares it.

## 7. GO

Q1, Q2, Q3 ruled; §4's fourth state resolved as above; the tooling proposal approved as
two builds. **Start T1 and T2, then T3–T5.** Expected standing: the four states computed
and rendered with prominence ranked by behaviour, the cited range on the face of the map,
the inert detector green, and the derivation document written well enough that someone
else could build from it.

Integrity: sha256(body) = d262c67dd6228b66203388319461aa25591ce1428e87f60f0dabd4effc96c8c9
