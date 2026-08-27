# `ND-053` — `validate_policy` refuses an inert effect label · decomposition

**Ruled:** R049 §6, on delivery's escalation from S4's Q3.
**Status:** **decomposed. BUILD HELD.** R054 §4 — *no breaking change lands between here
and launch*, and the build ruling comes after **Sept 12**.
**Kind:** breaking. Deployments that boot today will refuse to boot after it.

---

## 1. Why this ticket is decomposed but not built

The freeze is the whole reason this section exists. **`ND-053` is the only breaking change
on the board**, and R054 §4 froze breaking changes from now to the firing sequence. So the
work is specced to the edge of the build and stops there.

That is not a delay dressed up as discipline. A breaking change landing in launch week
would arrive with no time for a deployer to hear about it, which is precisely the failure
the three constraints below exist to prevent — shipping it *now* would violate its own
first constraint.

**The detector already shipped** in `0.5.0`/`0.6.0` (`studio.coverage`'s `declared_inert`
rows), so an operator can find every instance in their policy today, before anything
refuses. Detector first, refusal after, is *the courtesy a breaking change owes the people
it will break* (R052 §5) — and the gap between them is doing useful work right now.

## 2. The defect, measured

```python
effect_policies = [ep for e in effects if (ep := store.get_effect(conn, e)) is not None]
```

An effect a policy **labels** with no `effect_policies` row behind it is **silently
dropped**. No tier floor. No effect caps. Measured on `0.5.0`:

```
label with NO effect_policies row       -> PERMITTED, effective_tier 1
same policy, effect policy now declared -> proposed,  effective_tier 3
```

The same request auto-executes or goes to a human depending on a row the policy author may
believe they wrote.

## 3. The law it enforces

**A protection that depends on a second, optional declaration is not a protection — it is a
default.** Recorded in `CONFORMANCE.md` as binding on **all** policy, with `ND-040`/U4 and
R027's generator rule as its other two instances. **The law is about the shape of the rule,
not the identity of its author**, which is why it binds hand-written policy exactly as it
binds a generator's output.

## 4. The three constraints, from R049 §6

1. **A declared breaking change in its own release.** Never folded into a patch: *a
   deployment that boots today and refuses tomorrow must have been told.*
2. **No opt-out flag.** A switch permitting inert effects would itself be a protection
   depending on a second optional declaration — **the law applied to its own escape
   hatch.** The remedy is a one-line edit to the operator's own policy: declare the effect,
   or drop the label.
3. **The refusal names the effect, the rule that labels it, and the remedy.** *A
   fail-closed check whose error does not say how to pass it converts a defect into an
   outage.*

## 5. Work order

- **T1** — `validate_policy` refuses when any effect in `policy.effects`, or in a
  `param_effects` rule's `add_effects`, has no `effect_policies` row.
- **T2** — the message: effect, labelling rule, both remedies, one sentence.
- **T3** — `load_file`'s ordering, and the migration story for stores that already hold
  inert labels.
- **T4** — both directions tested, plus a **structural** test that no configuration can
  disable the refusal (constraint 2, in the shape of `serve`'s bind-refusal test).
- **T5** — release notes stating the break plainly, with the coverage map named as the
  pre-flight check.

## 6. The finding this decomposition surfaces — and it is a hard one

**`validate_policy` cannot see effect policies today, and giving it the ability changes
what "validating a policy" means.**

Its current signature is `validate_policy(policy: Policy) -> None`. It is a **pure function
of one rule**: everything it checks is intrinsic — a Tier-1 rule needs a reversal, a
`cost_param` must be required, a pattern must compile. That purity is why it can run in
`load_file` *before any write*, why the Studio's collecting wrapper works, and why it can
be called on a candidate that has never touched a store.

This check is different in kind: **it is a fact about the rule's relationship to another
table.** Making it a `validate_policy` check means one of:

- **(a) pass the connection** — `validate_policy(policy, conn)`. Simple, and it makes a
  previously pure function require a database. Every existing caller changes, and the
  Studio's wrapper starts needing a store to validate a draft that has no store.
- **(b) pass the declared effects** — `validate_policy(policy, declared_effects=...)`.
  Keeps it pure and testable; requires every caller to know the effect set, which
  `load_file` does and a lone caller may not.
- **(c) make it a set-level check instead** — a new `validate_policy_set(policies,
  effects)` that runs where the whole set is known, leaving `validate_policy` untouched.
  Honest about what the check actually is; means the refusal fires at a different place
  than the other invariants, which a reader may find surprising.

**Delivery leans (c)**, because the check genuinely *is* set-level — §5 of the coverage
derivation says the same thing about `declared_inert` — and because (a) would make the
single most-called validator in the engine require a connection in order to check a
property that has nothing to do with the rule in front of it. But (c) has a real cost:
`validate_policy` would then no longer be the one place a policy author's mistakes surface,
and **a check nobody thinks to call is a check that does not run.**

This is a design question with a compatibility tail, and it wants a ruling with the build
rather than a decision taken quietly inside it.

## 7. What is unblocked under the freeze

Nothing that changes engine behaviour. What *is* free, and delivery will do if core wants
it before Sept 12:

- **T2's message text**, written and reviewed without being wired up — the wording is the
  part most worth getting right, and it costs nothing to settle early.
- **A survey**: run `coverage.build` over every policy set in this repository — the
  development seed, the shipped pack, the test fixtures — and report how many inert labels
  exist today. **Delivery has already run this for the shipped pack: zero.** Doing it
  everywhere would size the break before anyone has to absorb it.

Both are documentation-shaped and land no breaking change.
