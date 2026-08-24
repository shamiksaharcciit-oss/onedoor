# Recomputable receipts

*Why a decision record is only worth what it costs someone else to check it.*

## The idea, in one sentence

A record is only as trustworthy as the cheapest way to check it. If checking requires
asking you, then **you** are the evidence — and the record is just a note pointing at you.

**The everyday version.** There are two ways a shop can prove you paid. One: a slip with
a reference number, and if anyone doubts it they can phone the shop. Two: a full receipt
— items, prices, total, date, and a stamp that can be checked against a published
record. The first is worthless the day the shop closes, changes hands, or simply says
something different. The second still works in ten years, in another country, with
nobody available to ask.

Almost every AI audit trail in production today is the first kind.

## Why "call our API to verify" fails

Three ways, all mundane rather than sinister.

**The service goes away.** Companies are acquired, products are sunset, APIs are
versioned out. A question about what an agent did in 2026 may be asked in 2031, and the
endpoint will not exist.

**The asker does not accept your word.** A regulator, an auditor, an insurer, opposing
counsel — the reason they are asking is that your account is what is in question.
Answering "our system confirms it" restates the claim rather than supporting it.

**You are structurally able to change the answer.** Not that you would. But if the
verification path runs through software you control, over data you control, nothing in
the architecture *prevents* a different answer. "We did not tamper with it" is a
promise. Recomputability replaces the promise with a property.

## Three ways systems fail the test

1. **The record is a pointer, not the thing.** *"Decision #48213 — see dashboard."* The
   dashboard is the evidence; the record is a bookmark.
2. **The data travels but the logic does not.** They have the fields; the rule for
   deciding whether those fields are self-consistent lives only in your codebase. They
   can read. They cannot check.
3. **Checking needs state only you hold.** They can verify the arithmetic but not the
   claim, because the policy in force and the configuration that ran never left your
   servers.

## How onedoor addresses it

Five mechanisms, each depending on the one before it.

**1 · The construction is a written specification, not only code.** The exact bytes
hashed for a decision record — which fields, in what order, how an absent value is
marked distinctly from an empty one, how each field is length-prefixed so two different
values can never produce the same byte string — are written in a normative document.
That sounds like paperwork. It is the load-bearing piece: without it, "the spec" is a
description of what one function happens to do today.

**2 · A second implementation, built from the document rather than the code.** This is
the test that the document is real. If only one implementation exists, nothing has been
specified — behaviour has been described. Two implementations that agree, one written
from the prose alone, means an outside party can build a third.

**3 · The receipt carries everything needed, and travels as a file.** Not a row in a
database — an export. It contains the record's hash and its position in the chain, four
content digests (what the decision was made *from*, what instrument made it, what must
be trusted to accept it, and the verdict itself), the signature and key identifier, the
published anchor, and the cryptographic proof that this record is included in that
anchor.

**4 · The verifier is tested in an empty room.** A test, not a claim: the acceptance
test runs the verifier in a directory containing exactly two files — the receipt and the
anchor — with no database and no network. If the verifier needs anything else, the test
fails and the design is wrong. A dependency on the service cannot be reintroduced by
accident, because the test would catch it.

**5 · Asymmetric signatures only, never shared secrets.** The verifier holds a public
key obtained independently. A shared-secret scheme — an HMAC-chained log, for instance —
can be checked only by someone holding the same secret. That is not public verification;
it is verification by insiders.

## The part that is unusual: a refusal

If a verifier checks a receipt against a root it found **inside the store being
verified**, onedoor does not report `verified`. It reports `self_consistent` — a
distinct, deliberately less flattering outcome meaning *everything here agrees with
everything else here, and that is not independence.*

To reach `verified`, the anchor must have been published somewhere the store does not
control: a file, a git commit, an endpoint, a line printed and taped to a wall. The
medium does not matter. The independence does.

> **onedoor never vouches for itself.** At the signature layer and the anchor layer
> alike, `verified` requires something the store does not hold.

Most vendors would treat that as a bug in the demo. It is the point.

## The outcomes do not flatten into pass and fail

| Outcome | Meaning |
|---|---|
| `verified` | the published root was supplied, the proof checks, membership holds |
| `self_consistent` | the proof checks against a root found in this store — real, and not independence |
| `absent` | not anchored yet. Anchoring is periodic; a recent record is normally absent |
| `unverifiable` | anchored, and the root could not be obtained |
| `failed` | the proof does not check |

`absent` matters most. Anchoring is periodic by design, so the most recent records are
always un-anchored, and that is not a fault. A viewer that showed them as failures would
train an operator to ignore failures.

## What this honestly does not give you

Offline verification establishes that a record is authentic and was included in the log
**as of the moment it was sealed**. It does not establish that a key was still valid an
hour later, and it cannot prove an operator was not also running a second, unlogged
system alongside this one.

Recomputability makes the record you are holding trustworthy without the operator. It
does not make the operator honest — it makes one specific, bounded part of their
honesty checkable.
