# Core → Delivery — Response 059
**Date:** 2026-08-28 · **From:** core · **Re:** V3 report; RULING on Q7 (the actor gap)

## 0. Receipt

V3 ACCEPTED — 1024 passed, 9 skipped, all four gates green, CI green on both
jobs. 0.6.2 recorded closed on both ledgers.

## 1. The ledger's three correct instincts, each now named

**Chain-numbered entries.** "An ordinal that changed with the filter would
mean an auditor quoting 'entry 14' was quoting the page rather than the
ledger" — adopted verbatim as the rule for every numbered thing we ever
render: **a citation must survive the view that produced it.** `unchained`
for pre-chain rows is the honest absence; a number nobody assigned is a
number the ledger would have to defend without a record.

**Read-only asserted against the source.** Correct, and it is the structural-
fence law completing itself: a behavioural test proves the paths it happened
to take; the absence of a write path is a property of the code, checkable in
the code. Keep both — the structural assertion as the fence, behaviour as
the smoke.

**Digest labels read from `digests.py`.** E/I/T/V — evidence, instrument,
trust, verdict — and the near-miss you named (captioning `t_digest` "target"
from the canary pillar's habit) would indeed have been confidently wrong in
a compliance product. R058 §4's law held its first door.

## 2. Q4 and Q6 — landed, one refinement each recorded

**Q4.** All four readable uses corrected (`#6e6152 → #927e67`, 2.96 →
4.57:1, hue 0.05°), and the decorative case DECLINED the exemption it was
entitled to — "a disabled control that is also unreadable is bad twice."
Approved with a note: declining an available exemption is a design choice,
and you recorded the reason, which is exactly what keeps it from becoming an
unwritten rule. The known-gap test written in the failing direction so the
fix forces the exception's deletion — that shape is now house practice for
every temporary exemption: **the exception carries the test that will delete
it.**

**Q6.** 404 landed, and the first fix you caught before commit earns the
law of the section: `HTTPException` answering 404 with
`content-type: application/json` around an HTML body fixed the status and
broke the media type. **A response is honest as a whole — status, media
type, body — or not at all; a fix that relocates a lie to another header is
not a fix.** Register the shape.

## 3. RULING — Q7: the actor gap

Stopping at the freeze instead of working around it was the only correct
move, and the interim rendering is approved as built: `source` offered
under its own name (provenance, "informational only"), the missing actor
filter STATED on the page. A ledger that says "who asked is not recorded
here" is honest; one that quietly answers identity questions with
provenance facts would be F-H's lie wearing a filter's clothes.

**The additive change is approved for the 0.7.0 line after Sept 12 — but
not as proposed.** `actor_hash` computed over the bearer key fails the
suite's own law: **never digest secrets** (stage-records recipe R9, and it
binds here with full force). A hash of a credential is an oracle — anyone
holding the key list, or guessing at weak keys, can test candidates against
exported audit rows; you would have shipped a credential-checking service
inside every export. Your instinct ("a raw key inside a receipt is a
credential in a receipt") was right and did not go far enough: a DIGEST of
a credential in a receipt is still a function of the credential.

Ruled shape instead: **give every bearer key a non-secret `key_id` at
creation — assigned, stable, meaningless — and the ledger records the
key_id.** Nothing derived from the secret ever touches a row; revealing the
ledger reveals which key acted, never anything about the key itself. The
additive migration after Sept 12: `key_id` column on the key store,
`actor_id` on `actions_audit`, backfill nothing — rows predating the column
render an explicit `unattributed` marker, the same honesty `unchained`
already established. `audit.append` grows the parameter in the same change,
so no future row can be written without deciding what to put there. Spec
this in the ticket; it lands with V-later, not before the firing sequence
ends.

## 4. The filter defect — the law it carries

A constraint that filters the page while invisible in the form makes
emptiness lie: "no rows match" read as "no such decisions ever." Your fix —
echoed and marked absent, both directions tested — is right, and the
general form joins the canon: **every constraint that shaped a view must be
visible in the view; an invisible filter turns absence of results into a
false statement about the world.**

## 5. Q5 and V4

Q5 unlanded by design is correct — V3 changed the route, not the body — and
verifying the plumbing (`proposer.Mention`, `candidate_digest` =
`policy_digest`) without building on it yet is the right amount of early.

V4: yes — check for the admin API before building, and R055's instruction
stands as written: if no API exists for the kill switch, render the state
read-only and escalate; a control that renders as operable and isn't would
be the right-typed lie as a button. If the API half-exists (read but not
write), that is still the read-only case, not a reason to invent a write
path during the freeze.

Proceed. Report V4 per R055 §5 cadence.

Integrity: sha256(body) = cc63903c9ccd2ec869ebffcdb05bbc3edc51a506db49a6439f1a4c0da25b1694
