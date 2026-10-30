# The recipient confirmation

A bound permit's recipient verifies the permit, then — separately — says
whether it acted on it, in a form the presenter (or anything reading the
record afterwards) can check without asking the recipient anything. That
signed statement is the recipient confirmation (bound-permit profile §10):
one more cross-domain object, the same way the permit itself is one.

It closes the last link console's Authorization page shows: proposal → permit
→ effect → the recipient's own signed word that the effect happened (or
didn't). A confirmation shows the recipient *said* it acted; it does not show
the effect happened in the world — see the non-claims below.

## The two sides

- **`onedoor.permit.confirmation.build`** — the recipient side. Given the
  `RecipientRequest` and the `VerificationResult` `onedoor.permit.recipient.verify`
  already returned, it builds and signs the confirmation. A `REFUSED` result
  fixes `outcome: "refused"`, with the step and reason the recipient actually
  reached — never a field it never established. A `COULD_NOT_CHECK` result
  also fixes `outcome: "refused"`, naming the `dependency` instead, with no
  step and no reason: the recipient did not act, and does not know which
  numbered step it would have passed. A `VERIFIED` result means the permit
  itself was fine; the caller supplies `outcome` (`"effected"` or
  `"effect-unknown"`) for what happened when it acted, since that is the
  recipient's own news, not something permit verification ever knew.

- **`onedoor.permit.confirmation.check`** — the presenter side (or anything
  auditing a record afterwards). Given a confirmation token and the reference
  values the step itself recorded (the permit, the request's digests, the
  action digest, the step's outcome and time window), it checks the
  confirmation against them — never against the permit a second time. Stops
  at the first failing row, the same discipline `verify` follows: key and
  `typ`, permit, request, outcome.

Single use across many confirmations (two different `effected` tokens for one
permit) is deliberately not `check`'s own job, since `check` only ever sees
one token at a time. `onedoor.permit.confirmation.find_reused_permits` is the
one helper this package exposes for it, given whatever set of tokens the
reader already has.

Both sides are importable without onedoor's engine, store or service — the
same standalone promise `onedoor.permit.recipient` already makes.

## The non-claims

Word for word, so nothing is implied beyond what follows:

- A confirmation shows the recipient said it acted. It does not show the
  effect happened in the world; that is the recipient's word, signed.
- A trusted key means the key is on the list you gave. onetrace does not
  decide whom to trust.
- The request digests are the ones this record wrote when the step sent the
  request. A match shows the recipient confirmed what the step says it sent;
  it does not show what went on the wire, and the presenter's own request
  signature is not checked (no body or key is kept).
- In a refusal at step 2 (signature-invalid, issuer-unknown), the permit's
  issuer and id are what the recipient read, not what it authenticated.
- Single use is checked across the records you give one verifier run, not
  across every record that exists.
- The rows read the record as onetrace wrote it. Recording a confirmation's
  digest in a step does not discharge onedoor's `present_bound` obligation:
  that is the presenter's own AADP report (-00 §13).
- The rows check the record against itself and the list. They make no
  network calls and ask no recipient anything.
