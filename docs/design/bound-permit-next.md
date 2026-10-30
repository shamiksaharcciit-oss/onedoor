# Bound permits: three mechanisms not yet built

`onedoor/permit/` and `onedoor/guardrail/bound_permit.py` implement issuance and
standalone recipient verification for a bound permit: a signed, short-lived
decision carried across a trust boundary, bound to a presenter's key by an HTTP
message signature (RFC 9421) over a fixed set of covered components, with the
authorised action named by a canonical digest.

Three mechanisms the wider design describes are not implemented. Each is
independent of the other two and of what already exists — none blocks a
deployment from issuing or verifying permits today. This note states, for
each, where it would attach, what it would need, what would prove it, and what
is still open.

## Modes of currentness

A time-bounded permit proves a decision was taken; it does not prove the
policy or the referenced mandate was still in force between issuance and
presentation. `onedoor/permit/recipient.py`'s `verify()` already declares two
values for a permit's `currentness` claim: `time-bounded`, which is fully
implemented, and `status-checked`, which is recognised but always returns
`could-not-check` with `dependency="status-unavailable"` — there is no status
mechanism behind it.

**Attachment point.** Step 10 of `verify()`, currently:

```python
if currentness == "status-checked":
    return _could_not_check(RefusalReason.STATUS_UNAVAILABLE.value, ...)
```

A real implementation would take a `status_checker` callable alongside
`mandate_evaluator` and `local_policy` — the same "deployment supplies the
mechanism, this package supplies the ordering" shape those two already use —
and call it with the permit's `jti`, `policy_version` and `mandate` claims,
returning current / superseded / unreachable.

**Inputs.** Two mechanisms are worth distinguishing, since they need different
inputs: a status-list lookup needs only the permit's own status identifier and
a way to reach the issuer's list; a stapled freshness statement needs the
presenter to supply a separate, issuer-signed, short-lived assertion alongside
the permit, which `RecipientRequest` does not currently carry a field for.

**Tests that would prove it.** A superseded policy version returning
`stale-policy` (RefusalReason already defines this; nothing produces it
today); a revoked mandate under `status-checked` returning `mandate-revoked`
(also already defined, also unreachable); the status endpoint unreachable
returning `could-not-check`, not a refusal — a property test already exists
for the current always-unreachable behaviour and would need to change to
"unreachable specifically" once a reachable path exists.

**Open questions.**
1. Should the two mechanisms (list lookup vs. stapled freshness) be one
   callable with a discriminated return, or two separate optional hooks? A
   deployment that only ever staples freshness statements has no use for a
   list-lookup callable's shape, and vice versa.
2. `onedoor.guardrail.mandate` already has its own verdict/resolver shape
   (`MandateVerdict`, `MandateResolver`) for the existing mandate-layer
   deferral. A status check on a *referenced* mandate (this mechanism) and a
   status check on an *in-process* mandate deferral (the existing one) are
   answering related but distinct questions — should they share one resolver
   interface, or stay separate because one runs at decide-time and the other
   at a recipient, in a different process, possibly a different organisation?

## The mandate reference

A permit can name a mandate — the authority under which the decision was
taken — as a reference (`type`, `id`, `digest`) rather than embedding the
mandate itself. `onedoor/permit/recipient.py` already implements the
recipient-side rules for this reference at step 11: an evaluator hook,
digest-mismatch refusal, PERMIT/DENY/PENDING handling, and an
optional-action-types escape hatch for permits that carry no evaluator at all.
What is missing is the **issuer** side: nothing in
`onedoor/guardrail/bound_permit.py` populates a `mandate` claim, and nothing in
`onedoor/guardrail/mandate.py` (the existing mandate-layer deferral) produces the
reference shape a bound permit would carry.

**Attachment point.** `onedoor/guardrail/mandate.py` already computes
`core_digest` for a request under mandate-layer deferral. `bound_permit.issue`
would need an optional `mandate_reference` parameter — `dict` with `type`,
`id`, `digest` — set from the same deferral machinery when a permitted
action's mandate was consulted, so the permit states which authority decided
under, not only that budget and policy permitted it.

**Inputs.** The mandate type registry this package would consult is exactly
`onedoor/permit/recipient.py`'s existing `mandate_evaluator` shape reversed:
the issuer needs to know, at issuance, which reference format a given mandate
type uses, so it can render the claim onedoor's own `mandate.py` already has
the digest for.

**Tests that would prove it.** A permit issued under mandate-layer deferral
carries a `mandate` claim whose `digest` matches `mandate.core_digest`'s
output for the same request; a permit issued for an action with no mandate
consultation carries no `mandate` claim at all (absent, not null — the same
discipline `present_bound`/`bound_permit_action_type` already follow: a field
that never applied does not appear).

**Open questions.**
1. onedoor's own mandate deferral (`mandate.py`) is deliberately **not**
   AAE-interoperable (its `core_digest` is onedoor's own scheme, disclosed as
   such in that module's docstring). A bound permit's `mandate.digest` claim,
   if built from `core_digest`, inherits that same non-interoperability. Is a
   `type` value other than `aae` appropriate for onedoor's own reference shape,
   or does every consumer of this claim need to already know onedoor's
   convention?
2. The reference must be established the way authorization-relevant
   provenance is established elsewhere in AADP — through an authenticated
   channel, never a caller-supplied parameter. `ActionRequest` has no field
   for a mandate reference today; adding one needs the same anti-spoofing
   framing `source` already has, not a bare optional string.

## The joint record

**Built.** `onedoor.permit.confirmation` (`build`/`check`/`find_reused_permits`)
implements this, closing bound-permit profile §10 per a separate,
not-yet-public format note; see [`docs/confirmation.md`](confirmation.md) and
`CONFORMANCE.md` §3 (V22). The three open questions below, as this design note
first posed them, resolved as built, not as originally framed:

1. `VerificationResult` was not widened, and `verify()` does not return a
   second object. `confirmation.build` takes the *request* (which already
   carries everything a confirmation needs to recompute: the permit token,
   the body, the signature's own `created`/components) alongside the
   `VerificationResult`, and re-derives each digest itself, gated on
   `result.step` so a field is only ever computed once the step it depends on
   actually passed.
2. The acyclic direction is kept by construction, not asserted at runtime: a
   confirmation always names a permit and a request that already exist (it is
   built *after* `verify()` returns), and nothing a confirmation names is ever
   itself required to carry a confirmation.
3. Every outcome gets a confirmation, including a refusal and a could-not-check
   — not only a verified one. `outcome` is fixed to `"refused"` for both,
   carrying `step`/`reason` for a check refusal and `dependency` for a
   could-not-check, per the format note's own §2.2.
