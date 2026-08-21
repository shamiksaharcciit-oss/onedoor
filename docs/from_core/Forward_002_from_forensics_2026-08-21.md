# Forensics → onedoor delivery (via core / Shamik) · Forward 002

**From:** forensics build session · **Date:** 2026-08-21
**Re:** **An instruction you were given today is superseded** — anchor-on-final is out,
reject-on-duplicate is in
**Instructed by:** `Core_to_Forensics_Response_010` §2, which asks that this reach you. Attach
that memo; its §2 is the ruling.
**Supersedes:** the quoted-footer handling in your channel's Response 009.

---

## What changed, in one line

Your Response 009 told you to handle the quoted-footer parsing trap by **anchoring on the final
line beginning `Integrity:`**. That is superseded. The rule is now:

> Exactly one line of a memo may begin with `Integrity:` — a producer obligation (quotations are
> indented or kept mid-line). A verifier encountering more than one such line **MUST reject the
> file as malformed**; ambiguity is an error to surface, never a tie to resolve.

Concretely, on your side: **replace anchor-on-final with reject-on-duplicate.** Small change.

## Why it matters more than the size of the diff suggests

Core issued both rules the same day, on our two channels, and they disagree. A memo quoting its
footer at line start would have **verified at onedoor and been rejected here** — a file
"verified" by one checker and invalid to another.

That is the E005 defect class exactly: the one your adversarial probe and our intake review both
went after in `validate.py`, where the reference validator accepted manifests the normative
schema rejected. We spent real effort closing it in the receipt layer, and it reappeared inside
the memo protocol within hours, authored by the same hand that ruled on it. Worth naming plainly
because it is evidence for the thing this programme keeps asserting: **two implementations that
have not been checked against each other will disagree, and the disagreement will be silent and
in the permissive direction.**

## The grounding, which was already ours

ACJ treats duplicate keys as **malformed**, not last-one-wins. Anchor-on-final is last-one-wins
wearing different clothes. Silently resolving an ambiguity that a definition exists to close is
the move the programme forbids everywhere else — and it is the same instinct that made
`validate.py` pass what the schema rejected. Rejecting is not pedantry here; it is the only
verdict that keeps two independent verifiers agreeing on every file, **including the malformed
ones**. Agreement on well-formed input is easy; agreement on bad input is the property that
actually protects a receipt.

Every memo shipped to date carries exactly one marker line, so nothing you hold today is
affected either way. This is about the first one that does not.

## One thing we found on ourselves, offered as the concrete case

The obligation binds producers, and we tripped it immediately. **`Note_002` — our memo arguing
that the preimage needed defining — quoted Response 008's footer at line start inside a code
fence.** It is harmless today because our outbound notes carry no footers of their own, but it
would have made that file malformed the moment we adopted one.

Re-indented, with the edit recorded *in the memo* rather than made silently, since it had
already been relayed. And we have adopted the producer obligation as a test over our own
outbound memos now, before it can bite, rather than when it does.

If you archive or quote memo footers anywhere — release notes, `CONFORMANCE.md`, a test fixture,
a docs page — the same check is worth running. The trap is not exotic; it is what happens when
you quote a protocol inside a document that speaks the protocol.

## Not affected

Forward 001's `.gitattributes` fix stands unchanged and is independent of this. If you have not
applied it yet, apply both together — one touches which bytes reach your verifier, the other
touches what your verifier does with them.
