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
property that has nothing to do with the rule in front of it.

### 6a. Core's lean, and the measurement that decides part of it

Core recorded an unbaked lean (post-R054 acknowledgment) and invited attack: *the
set-level check wants to live where the set already assembles — the ceremony and the
coverage build — rather than as a second entry point an author must remember.*

**Agreed in direction, and the measurement strengthens it past a lean into an argument.**
Option (a) — a connection-reading check inside `upsert` — is not merely inelegant. **It is
wrong, and measurably so**, because the two set-assembling paths write in *opposite
orders*:

```
policy_loader.load_file : POLICIES FIRST, then effects
ratify._apply           : EFFECTS FIRST, then policies
```

`load_file` upserts every policy before it upserts a single effect policy. So a check
inside `upsert` that read the `effect_policies` table would see **nothing declared yet**
and refuse every valid file at boot — while the same policy set, written through the
ceremony, would pass. **The same rules would get different verdicts depending on which
path wrote them**, which is precisely the class this programme refuses everywhere else.

That kills (a) on evidence rather than on taste, and it also constrains the rest: the
check must run **over the assembled set in memory** — before any write, or after all of
them — never per-row mid-write.

### 6a-pinned. The write-order asymmetry is load-bearing, and a test says so

**This measurement is now evidence in a ruling, so it is pinned**
(`tests/guardrail/test_policy_write_order.py`).

Harmonising the two orders in a future cleanup would be a defensible change — and it would
**silently invalidate the analysis above without failing anything**, because nothing in the
engine depends on the orders differing. Only the *argument* does.

So three tests read the two functions' ASTs and assert the orders, and a fourth asserts the
asymmetry itself as its own fact — the one the ruling actually uses. **None of them forbids
the change.** They require whoever makes it to come back here and re-run the reasoning,
because if both paths were to write effect policies first then option (a) becomes viable
and the parked lean needs revisiting.

Verified by sabotage: reordering `ratify._apply` to match `load_file` fails
`test_the_ceremony_writes_effect_policies_before_policies` and
`test_the_two_orders_are_still_opposite`, each naming §6a.

*Evidence that no test protects is evidence with a shelf life.*

### 6b. Where delivery's reading differs from core's lean

Core named *"the ceremony and the coverage build"*. Two corrections, one of which matters
a great deal:

- **`load_file` must be included, and it is the important one.** It is the *engine's* own
  set-assembling path — the documented way a deployment seeds its policy — and **most
  deployments never touch the Studio at all.** A refusal that lives only in the ceremony
  would leave the primary boot path unchecked, which is the hole the whole ticket exists
  to close. `load_file` is also already shaped for it: it validates every rule *before
  writing any*, so a set-level check drops into an existing before-any-write phase rather
  than needing a new one.
- **The coverage build cannot host a refusal**, only a detection. `coverage.build` reports
  `declared_inert`; it returns a map and refuses nothing, by design and correctly. It is
  the **pre-flight**, not the gate. Naming it as a home for the check would blur a
  detector into an enforcer — the same distinction the epic spent six tickets keeping
  straight.

So delivery's position: the refusal lives at **both set boundaries** — `load_file` and the
ceremony — computed over the in-memory set, with `coverage.build` remaining the detector
that lets an operator find every instance first.

### 6c. The residual, named rather than papered over

**A bare `upsert(conn, policy)` of a single rule stays unchecked, and cannot be checked.**
You cannot tell from one rule whether its effects are declared without reading the table,
and §6a is the proof that reading the table mid-write gives order-dependent answers.

That is a real gap and it should be stated in the release notes rather than discovered:
**a library caller who bypasses both set boundaries can still write an inert label.** What
closes it for them is the same thing that closes it for everyone — `coverage.build`, run
against their store. Delivery does not propose making `upsert` refuse, because the only
way to do that correctly is to make it take the whole set, at which point it *is* the
set-level check under another name.

**Core's underlying point survives intact and is adopted:** the check belongs where the set
assembles, not as a third entry point an author must remember to call. *A check nobody
thinks to call is a check that does not run* — which is exactly why it goes into the two
functions everyone already calls, rather than beside them.

### 6d. The amended lean, as it stands going into the build ruling

Core accepted the attack and amended its lean (R054 acknowledgment). **This is the
presumptive shape for the build ruling after Sept 12, and remains attackable here until
then:**

- The set-level inert-effect check lives at **both set-assembling paths** — the ceremony
  **and `load_file`** — since most deployments never touch the Studio and **the engine's
  own boot path cannot be the unchecked one**.
- **`coverage.build` detects and never refuses** — pre-flight, not gate.
- **The residual is named, not papered:** a bare single-rule `upsert` stays uncheckable,
  and the release notes say so.

Option (a) is closed on evidence rather than preference: it would give the same rules
different verdicts depending on which path wrote them.

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
