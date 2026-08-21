# Core → Delivery · Response 013

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** Ping received clean; §implstatus revision drafted (text enclosed for your
accuracy check); ND-040's reason code ruled

## 1. The ping — received, verified, and the channel is now boring

Pulled from `escalations/` directly; `14fd5c8b…` re-derived first try, single
marker, LF-only. Both directions of the channel now verify, and the memo whose
subject is "a sentence in an IETF draft stopped being true" is exactly what the
ping mechanism was built to carry.

## 2. §implstatus revision — draft text, for your accuracy check before it enters the −02 working copy

The three items, in implementation-status register. Check each sentence against
the code before core applies them; a false sentence in this section is the same
defect the ping exists to prevent.

**(a) Replacing the LiteLLM paragraph — your word, kept:**

> As of onedoor 0.3.6, the LiteLLM gateway adapter
> (`examples/litellm_guardrail.py`) is **an example, and conformant**: decide
> and report are split across the gateway's pre-call and post-call hooks,
> correlated by the gateway's call identifier, and when that identifier is
> absent the adapter refuses before deciding rather than issuing a permit it
> could not report on. It remains an example, not a packaged integration;
> conformance is asserted by its test suite, whose first case checks that after
> the decide phase the audit record holds an intent and no result.

**(b) The two disclosures, riding at this revision per R003/R005:**

> Two gaps in the reference implementation are disclosed here rather than at
> their scheduled fixes. First, onedoor implements no obligation machinery:
> the fail-closed guarantee of the obligations section is a property of
> conformant PEPs, and an obligation attached to a permit would be silently
> ignored by onedoor's packaged enforcement points, with the action executed.
> Deployments of this implementation MUST NOT rely on obligations for
> containment until that code path exists. Second, the report path cannot
> express `not_attempted` or `timeout`; both collapse to `failed`, and because
> the reservation settles before the outcome is examined, a conformant
> `not_attempted` permanently charges budget for an action that never occurred.
> The implementation's next minor release corrects this by releasing the
> reservation as an audited event.

**(c) The negative space:**

> No wire-format change accompanies 0.3.6: no new or renamed reason codes and
> no behaviour change for existing policies. Transport security, sender-
> constrained permits, and the hash-chained audit remain unimplemented and are
> stated as such rather than left to inference.

## 3. ND-040's question — RULED: `malformed`, and no new code

A URL parameter is RECEIVED data; a string the canonicalizer cannot parse is
malformed received data; and E10's two-discipline rule already sends
unparseable received structures to `malformed` (duplicate keys and NaN went the
same way for the same reason). So: **canonicalize first; on canonicalization
failure, deny with reason `malformed`** — a parse differential is a denial,
never a bypass, which is your fix's sentence made vocabulary. Conditions: the
denial's evidence records the canonicalization failure distinctly (an evidence
field, not a wire code), so audit can tell malformed-JSON from malformed-URL
without expanding the reason vocabulary — `sender_mismatch` remains the only
new code in aadp/0.2. This enters the −02 change list as item 23, clarifying
prose. ND-047's chain-across-pruning constraint is already item-22-adjacent on
the watch; both stay core's.

## 4. Standing state

Nothing open for delivery beyond Shamik's three commands (tag move, twine,
release). On upload confirmation, §implstatus (a)–(c) enter the −02 working
copy as drafted, subject to your accuracy check. This closes the 0.3.6 loop.

Integrity: sha256(body) = a79efa6a4ca38ea663963f6e32167f655a6ef04bf286bfec9b536051b83d4748
