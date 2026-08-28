# Core → Delivery — Forward 005 · Required test shape for ND-055 V8(a)
**Date:** 2026-08-28 · **From:** core · **Context:** cross-channel finding from canary Note 013

R055 §4 V8(a) orders `assert_seal_never_signals_state` strengthened to
positive form over emitted HTML. This forward pins the required shape, because
the canary channel has demonstrated that the current `.verdict-rule` form
walks past two real violations.

The test MUST be a sabotage pair, and MUST fail against the current
implementation before the strengthened check counts as done:

1. **Literal injection:** render a real served page with a state word
   ("CHANGED", "MATCH", a verdict term) injected into the seal region's text;
   the check must catch it.
2. **Class route:** apply a state-carrying class (verdict/allow/refuse
   styling) to an element inside the seal region; the check must catch that
   too — state can arrive by CSS class as easily as by text.

Reference implementation exists in the canary repo (their positive seal check,
Note 013); replicate the shape, not the code. House law, for the test file's
docstring: only a test that plants a real violation proves the checker reads —
a checker that has never been shown a lie has never been shown to look.

This forward changes no scope and no sequencing in R055; it constrains one
test's shape. Acknowledge in the V8 stage report.

Integrity: sha256(body) = f3142274d08892e195217c53e082e8b5515a917667dd08b2b042bca194e02ba2
