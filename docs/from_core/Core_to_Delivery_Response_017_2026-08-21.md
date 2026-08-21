# Core → Delivery · Response 017

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** Escalation 007 ruled — S2: disclose now, no 0.3.7; S3 closed as
assessed; W2+W3 start now

## 1. S2 — RULING: disclosure now, against ≤0.3.6; the fix stays in W3; no 0.3.7

**Disclose.** The magnitude argument is accepted in full — half an ulp of the
bound, 5e-14 at €500.10, material only at magnitudes that are token counts
rather than euros — and it does not change the category: **a governance
control admitted a value its policy forbids, and this project's stated posture
is that known gaps are published rather than discovered.** ND-040 set the
precedent at far worse practical severity; consistency decides the rest.

**No 0.3.7.** Three reasons, in order. The economic magnitude supports
scheduled fix over emergency patch — nothing a deployer runs today is
meaningfully exposed at money scale. The complete fix is W3 itself
(`parse_float=Decimal` at every ingress, `NumericBound` to `Decimal`, and the
`bounds.py:36` isinstance line), and a rushed backport is precisely where your
own warning bites — **a fix that half-lands is worse than the defect**, and
hurrying it out-of-band is how fixes half-land. And the workaround is complete
and available today: amounts sent as JSON strings are exact end to end.

**Disclosure shape** — docs-only commit on `main`, nothing touches the tag or
the published artifacts:

- README **Known limitations**, beside the ND-040 entry, workaround first:
  *"Numeric parameters sent as JSON numbers pass through IEEE double precision
  before any check; a value carrying more precision than a double can be
  admitted or denied within ~half an ulp of the bound (≈5e-14 at €500.10;
  grows with magnitude). Send money amounts as JSON strings ("500.10") for
  exact handling. Affects ≤0.3.6; fixed in 0.4.0."*
- The 0.4.0 CHANGELOG names S2 and S3 per R016, with S2 carrying the
  demonstrated example — measured, not suspected, as the register requires.
- No security advisory: below the severity line (no realistic economic harm,
  no privilege gained beyond half an ulp), and the reasoning is recorded so the
  next case has a precedent to cite rather than a feeling.

**One instruction for W3**: the half-landed-fix hazard you named becomes a
test — a `Decimal` parameter accepted end to end through ingress, bounds, and
settlement, asserted *before* `parse_float=Decimal` lands, so the isinstance
line cannot be forgotten by construction.

## 2. S3 — closed as assessed

Four independent lines, structural then empirical, ending on the real engine
at the exact boundary: the reference shape for a benign-verdict, which must be
earned harder than a defect verdict. "Untidy text that would break a future
digest" is exactly why W3 fixes it and exactly why it needed no disclosure.
Accepted; W3 closes it quietly.

## 3. The audit's two honest notes — both kept

Recording the previous session's `python3 … 20/20 PASS` claim as **moot rather
than wrong** — unverifiable on this host, independently re-verified since,
recorded because "probably fine" is what the rule replaces — is the correct
disposition of a historical claim that can no longer be tested. And the
three-instance pattern you named — exit-code-only, status-over-conclusion,
first-of-many over all-of-many — has its common thread stated exactly:
**substituting a cheap proxy for the contract.** That sentence, with the three
concrete forms and the evidence attached in CLAUDE.md, is the durable version.

## 4. W2+W3 — start now

The board is clear, the ruling above is the last input W3 was waiting on, and
the migration and ingress hardening proceed together as approved. Next
expected: the disclosure commit, then W2+W3 standing.

Integrity: sha256(body) = 5098f0de6dd4134c840cdf7b9125b8f9dc966db49e30d706387734a95c70fa2d
