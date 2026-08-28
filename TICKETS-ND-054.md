# `ND-054` — numeric bounds accept the decimal-string form · decomposition

**Ruled:** core's F-B ruling, 2026-08-27 — an **unnumbered acknowledgment**, not a numbered memo (`R055` is `ND-055`, the Studio build; see §8).
**Status:** specced, **build held**. Lands as the **first post-freeze change**.
**Kind:** widening — `denied` → `permitted` for input the engine accepts today.

---

## 1. What this is, corrected

Not a design question. **A conformance defect against AADP-01's own worked example.**

`draft-saha-aadp-02` §5:

> Monetary values are decimal strings (for example, "12.50"), never floating-point
> numbers. **This rule applies wherever a monetary value appears, including inside
> "params"**: the example in §5.1 carries "amount_eur" as "40.00", and a PDP that
> evaluates numeric bounds or caps over such a parameter **MUST** accept the
> decimal-string form, evaluated exactly, and **MUST NOT** require the caller to supply a
> binary floating-point number instead.

And §5.1's request literally reads:

```json
"params": { "payee": "acme-gmbh", "amount_eur": "40.00" }
```

**A decimal string in `params` is not merely permitted — it is the draft's own example**,
and onedoor refuses it whenever a `numeric` bound is declared over that parameter.

## 2. The irony, which is the reason this is not cosmetic

The refusal **forces integrators toward binary floats** — the exact representation the
draft's own Security Considerations names as an attack surface:

> Monetary values as decimal strings avoid floating-point rounding as an attack surface
> on budget arithmetic.

So the stricter-looking check was steering callers to the less safe form. **A check that
looks stricter can be the one steering you toward the hazard**, and "it fails closed" was
not the whole story: it failed closed on *this* request while pushing the next one onto a
representation the spec warns about.

## 3. The engine's own inconsistency, unchanged

Measured on shipped code, same request twice:

```
params {"amount_eur": "40.00"}
  no numeric bound      -> resolve_cost sees Decimal('40.00') -> PERMITTED, 40 EUR charged
  + numeric max=2000    -> resolve_cost sees Decimal('40.00') -> denied / bounds
```

`caps.resolve_cost` accepts `str`; `bounds` does not. **Adding a bound changes which wire
types the action accepts.** Two implementations of *"is this a number?"*, which is the
root and which the fix must close rather than paper over.

## 4. The fix

**One `numeric_value(raw) -> Decimal | None`, called by both `bounds` and
`resolve_cost`**, with a test asserting they cannot answer differently. That clause is the
fix; accepting decimal strings is what it makes true in both places at once.

- Parsed as `Decimal`, **never through `float`** — the draft says *evaluated exactly*, and
  routing through a binary float to check a bound would reintroduce the hazard at the
  check rather than at the caller.
- The frozen `params_json` is untouched. Interpretation for evaluation, never
  normalisation of received data (E10).
- `bool` excluded, as both paths already do; `NaN`/`Infinity` stay **malformed**, not
  "not numeric".

## 5. The three tests the ruling requires, both directions

1. **`"40.00"` accepted and evaluated exactly** — including that a bound of `40.00`
   admits `"40.00"` and refuses `"40.01"`, which is the equality a float would blur.
2. **A float-precision edge case handled deliberately** — a value that is exact as a
   decimal and not as a binary float (`"0.1"`, `"1.005"`, a bound at `"0.3"` against
   `"0.1"`+`"0.2"`). The test states which answer is correct and why, rather than
   asserting whatever the implementation happens to produce.
3. **A garbage string still refused**, with the bounds message **naming the parameter** —
   the widening must not become "accept anything that is a string".

Plus the shared-function test from §4: `bounds` and `resolve_cost` never disagree about
one value.

## 6. Why it waits

**`denied` → `permitted` is the one direction that never rides a hotfix into launch
week** (the F-B ruling, ratifying delivery's own lean). It is not a launch blocker: the failing
direction is closed, and `README.md`'s *Known limitations* carries the gap meanwhile so an
integrator meets it in documentation rather than in a refusal.

## 7. Delivery's error, recorded

The escalation's §2 read was **wrong**, and the way it was wrong is worth keeping.

It argued the decimal-string rule belonged to *generated* structures — the budget object —
and that the spec was silent on `params` typing. **−01's rule was already unqualified:**
*"Monetary values are decimal strings… never floating-point numbers."* Monetary values,
full stop. The scope restriction was delivery's inference, drawn from **where it first met
an example of the rule** (`CONFORMANCE.md`'s budget-object line) rather than from the
rule's own words.

And the mechanism of the error is the plainer failure: **delivery reasoned from
`CONFORMANCE.md`'s summary of the spec instead of opening the draft** — which was on the
same disk, and which delivery opened an hour later for the Appendix B review. The standing
rule already says the memos are authoritative over the summary; the draft is authoritative
over both, and it was never consulted.

> **A summary is a claim about a source. Check the source before you reason from the
> claim.**

The escalation itself was still the right act: it flagged a verdict-changing behaviour
rather than taking it, and it surfaced the engine-internal inconsistency that the spec
question sat on top of. **What was wrong was the read, not the escalating** — and the
proposal it reached was the one core ruled for.

## 8. A citation defect, self-caught and corrected

This ticket cited its ruling as **`R055`**. That was wrong, and the way it was wrong is
worth keeping.

Core's F-B ruling arrived as an **unnumbered acknowledgment**. Delivery gave it the next
sequential response number *by assumption* — and the same for the Appendix B ruling, which
became "R056". Both real memos then arrived on 2026-08-28 and took those numbers: `R055` is
the `ND-055` Studio build authorisation, `R056` is the seal ruling.

So two response numbers each meant two different things, in the register whose entire value
is that a reader does not have to wonder. **A number that names two rulings names neither.**

Caught by an audit of every `Resolved by Response NNN (date)` heading against the archived
memo bearing that number — **exactly two mismatched, both delivery's, both from numbering
something core had not numbered.** `tests/protocol/test_ruling_citations.py` now runs that
audit, so a citation cannot drift from the archive again.

The rule: **cite what the source calls itself.** An unnumbered acknowledgment gets a date
and a subject, never a number invented to make it look like the ones around it.
