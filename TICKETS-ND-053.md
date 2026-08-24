# `ND-053` — `validate_policy` refuses an effect label with nothing behind it

**Ruled:** R049 §6, on delivery's escalation from S4's decomposition (Q3).
**Status:** specced, **not built**. Lands with the release that declares it.
**Kind:** breaking. Deployments that boot today will refuse to boot after it.

---

## 1. The defect, measured

`decision.py` resolves effect policies like this:

```python
effect_policies = [ep for e in effects if (ep := store.get_effect(conn, e)) is not None]
```

An effect a policy **labels** with no `effect_policies` row behind it is **silently
dropped**. No tier floor. No effect caps. Run on `0.5.0`:

```
label with NO effect_policies row       -> PERMITTED, effective_tier 1
same policy, effect policy now declared -> proposed,  effective_tier 3
```

The same request auto-executes or goes to a human depending on a row the policy author
may believe they wrote.

## 2. Why it is a refusal and not a warning

**A protection that depends on a second, optional declaration is not a protection — it is
a default.** Third instance of that law, and the one that made it the programme's rather
than a ticket's — recorded in `CONFORMANCE.md` as binding on **all** policy.

R027 applied it to the Studio's generator because the generator was the surface in front
of us. **The law is about the shape of the rule, not the identity of its author**, so the
generator rule is a *case* of it, not its source. Hand-written policy has the same shape
and the same hazard.

## 3. The three constraints core attached

Because this changes what a deployment boots with:

1. **A declared breaking change in its own release**, stated plainly in the notes.
   Never folded quietly into a patch: *a deployment that boots today and refuses
   tomorrow must have been told.*
2. **No opt-out flag.** A configuration switch permitting inert effects would itself be
   a protection depending on a second optional declaration — **the law applied to its own
   escape hatch.** The remedy available to any operator is a one-line edit to their own
   policy: declare the effect, or drop the label.
3. **The refusal names the effect, the rule that labels it, and the remedy.** *A
   fail-closed check whose error does not say how to pass it converts a defect into an
   outage.*

## 4. Work

- **T1** — `validate_policy` raises when any effect in `policy.effects` or in a
  `param_effects` rule's `add_effects` has no `effect_policies` row. It needs the
  connection, which `validate_policy` does not currently take — that signature change is
  the bulk of the work and touches `load_file`'s validate-all-then-write ordering.
- **T2** — the message: effect, labelling rule, and both remedies, in one sentence.
- **T3** — the migration story. Existing stores may hold inert labels **already**; the
  refusal must fire at policy-write time with a message an operator can act on, and the
  release notes must tell deployers to run the coverage map first. `ND-052`/S4's
  `declared_inert` rows are exactly the pre-flight check, which is why the detector
  shipped first and the refusal follows.
- **T4** — both directions tested, plus a test that **no configuration can disable it**
  (constraint 2 asserted structurally, in the shape of `serve`'s bind-refusal test).

## 5. Sequencing

The **detector shipped in S4** and is available now: `studio.coverage` reports
`declared_inert` with the remedy in its detail line, and the coverage map renders it
first. An operator can find every instance before the refusal exists.

The refusal lands with the release that declares it — **not** in `0.5.x`, and not folded
into a Studio release. Its own increment, its own notes, its own migration guidance.
