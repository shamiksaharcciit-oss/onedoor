# Bound permits

A bound permit is a signed, short-lived statement that onedoor already decided
a specific action is permitted, carried across a trust boundary so a second
party — one that does not run onedoor's own decision engine — can check it
without re-running the decision.

## What onedoor issues

When a policy asks for one, a permitted action's response includes a compact
JWS (RFC 7515), typed `aadp-permit+jwt`, with claims (RFC 7519) that state:

- who issued it, who it is for, and a unique identifier (`iss`, `aud`, `jti`);
- when it becomes valid and when it stops being valid (`nbf`, `exp`), with a
  short, bounded lifetime;
- the action it authorises, as a digest over a canonical JSON rendering
  (RFC 8785) of the decided parameters, not the parameters themselves;
- a confirmation key: the RFC 7638 thumbprint of the key (RFC 9449's `cnf.jkt`
  confirmation claim) the party presenting the permit must sign its request
  with.

The permit is signed with an Ed25519 key configured for the deployment. It is
issued only for an action that is actually being permitted — never for a
proposal awaiting approval, a dry run, or an observed action — and only when
the request presenting it can name the key it will sign with. A policy that
asks for a bound permit but cannot get one issued denies the action outright,
before reserving any budget, rather than permitting it without a permit.

## What a recipient verifies

A party receiving a bound permit runs one ordered sequence of checks and stops
at the first one that fails, so a request refused for any reason never
consumes the permit it presented. In order:

1. The permit is present and well-formed.
2. It was issued by an issuer the recipient trusts, and its signature verifies
   under that issuer's key.
3. It names this recipient as its audience.
4. It is currently valid — not expired, not yet valid, and its declared
   lifetime does not exceed the bound this profile sets.
5. The kind of authorization it grants is one the recipient recognizes.
6. What it authorises falls within that issuer's declared scope — the type of
   action and any limits on its parameters (an amount ceiling, for instance).
7. The bytes actually received match the digest the request declares
   (RFC 9530's `Content-Digest` field).
8. The request itself is signed (RFC 9421, HTTP Message Signatures) by the key
   the permit's confirmation claim names, over a fixed set of the request's
   components.
9. The action the request actually describes matches the digest the permit
   authorised.
10. The permit's currentness is still good — see below.
11. If the permit names an external authority the decision deferred to, that
    authority's current verdict is consulted and must not have changed to a
    denial or a pending state.
12. The recipient's own local policy, whatever it is, allows the request.
13. The permit has not already been consumed — a repeated presentation of the
    exact same request returns the stored outcome rather than acting twice; a
    repeated presentation of a *different* request under the same identifier
    is refused.

Every outcome is exactly one of three things: verified, refused with a named
reason and the step that refused it, or could-not-check with the dependency
that was unavailable (a key directory, a status endpoint, the store that
tracks consumption). A dependency being unreachable is never reported as a
policy refusal, and a policy refusal is never reported as a technical failure
— the two are always distinguishable in the record.

A permit that names a parent permit — one issued on the strength of another —
is refused outright. A bound permit authorises exactly one request, to one
audience, presented once; a party that itself needs to act further in another
domain takes its own decision there and issues its own permit, rather than
forwarding this one.

## What this does not cover

A bound permit does not, on its own, prove that the policy behind a decision,
or an authority it deferred to, is still current at the moment it is
presented — only that it was current when the decision was taken, within the
permit's short lifetime. Every permit today carries only that time bound: a
stronger currentness check (confirming, at presentation time, that nothing
has since been superseded or revoked) is recognized in the recipient check's
claim vocabulary but always reports as unavailable, since no such mechanism
is wired in yet. That mechanism, referencing an external authorization
authority by digest, and a signed record both sides of a cross-domain action
can check, are documented as design work, not yet built, in
`docs/design/bound-permit-next.md`.
