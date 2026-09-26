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

Each side of a cross-domain action — the issuer's own decision record, the
recipient's verification outcome — is, on its own, a self-authored account.
A joint record is a second object, signed by whichever side produces it,
naming the other side's artifact by digest, so a dispute has one object both
sides can check rather than two that merely happen to agree.

**Attachment point.** The recipient side: `onedoor/permit/recipient.py`'s
`verify()` returns a `VerificationResult` today and stops there. A joint
record would be a value produced *from* that result — a small, separate
function, `onedoor/permit/confirmation.py`, taking the result, the parsed
permit claims, and the recipient's own signing key, and returning a signed
JWS naming: the permit's own digest, the request's content digest and
signature-base digest, the action digest, the mandate verdict's digest where
one was evaluated, and the outcome. Kept separate from `verify()` itself for
the same reason `jws.py`/`httpsig.py`/`jcs.py` are separate modules already —
one function, one responsibility, so a recipient that wants verification
without ever producing a confirmation is not forced to.

**Inputs.** Nothing this package does not already compute somewhere:
`action_digest` (already computed at step 9), the Content-Digest header
(already validated at step 7), a digest over the HTTP message signature base
(`httpsig.signature_base`'s own output, already computed at step 8) — the
gap is only that `verify()` discards these intermediate values on return
rather than making them available to a confirmation builder.

**Tests that would prove it.** A confirmation built from a `VERIFIED` result
verifies under the recipient's own public key and names the exact permit and
request digests `verify()` computed; a confirmation built from a `REFUSED`
result still names the reason; the confirmation's own digest, once computed,
round-trips through parse/verify the same way a permit does (this package
already has that machinery in `jws.py`).

**Open questions.**
1. `VerificationResult` is a frozen dataclass with no field for the
   intermediate digests a confirmation needs. Threading them through means
   either widening `VerificationResult` (a public-surface change every
   existing caller would need to tolerate) or having `verify()` optionally
   return a second, richer object — which shape is worth the disruption is a
   question for whoever picks this up, not answered here.
2. Direction of reference matters for the record to stay acyclic: the
   confirmation should name the permit and the request, and nothing written
   after the confirmation should be something the confirmation itself names.
   Is that ordering constraint something this package should assert in code
   (refusing to build a confirmation that references something not yet
   computed), or is it purely a caller discipline to document?
3. Should a refused verification also produce a signed confirmation? A
   refusal that is merely returned is an assertion the recipient can later
   deny making; a refusal it signs is evidence. Whether *every* refusal
   should be confirmed, or only ones past a certain step, is unresolved.
