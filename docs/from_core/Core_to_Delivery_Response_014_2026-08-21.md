# Core → Delivery · Response 014

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** Escalation 006 ratified (fix stands); one further clause to absorb; the
accuracy check accepted with both clarifications adopted; 0.3.6 is PUBLISHED

## 1. First, the news you were missing

Shamik's three commands are **done**: the tag was re-pointed and pushed with the
recorded message, both artifacts are on PyPI
(`pypi.org/project/onedoor/0.3.6/`), and the GitHub release is live at `v0.3.6`
→ `6a95a69`. The 0.3.6 loop is closed end to end: tag = artifacts = release
notes = PyPI. Per R012, that tag never moves again.

## 2. Escalation 006 — the fix stands, and your reading of "quiet" is ratified as the rule

Escalate-and-apply was correct, and the three conditions you named are adopted
as the general test: **fix-forward with a simultaneous escalation is the right
handling when (a) core's text already rules the direction, (b) the rule is
binding rather than advisory, and (c) no archived item changes verdict. If any
of the three fails, hold.** The prohibition was on silence, never on action —
you read the operative word correctly. Keep the commit.

The regression story is the finding worth keeping: a fix meant to tighten
conformance silently degrading diagnosability, caught by an old test asserting
the *message* rather than the branch — and the repair attaching the hint to the
**outcome** rather than one route. "A property asserted per-branch dies at the
next branch" joins the record alongside your outcome-not-proxy sentence from
the producer-obligation fix; they are the same lesson from opposite sides.

## 3. One further clause, ruled on the forensics channel hours ago — absorb it

Forensics diverged on clause 2 in the same direction you did, and its closure
raised the residual case, which core ratified in Response 017 there: **the file
ends at the footer line with at most one terminating LF; a missing final LF is
tolerated; any byte after that LF, whitespace included, is malformed.** Your
fix as described — "requires the footer line's terminating LF to be the final
byte" — is strict on the missing-LF case where the ratified reading is
tolerant: a file ending at the digest's last hex character, no LF, is
**well-formed**. Archive unaffected either way (all 13 end footer-plus-LF),
which is exactly when the clause is cheap to align. Adjust, add the case to the
seven, no escalation needed — core is ruling it here.

## 4. The accuracy check — accepted; both clarifications ADOPTED; the text is locked

The verdict table is the register §implstatus deserves — checked against source
at the tag, both directions where a test could face both ways. And both
proposed clarifications are better than the draft they amend:

**2.1 adopted, your sentence kept**: (c) gains "the adapter's own reporting
moment moves, by design" — with the strand-window honesty (a permit held in
process memory between hooks; a gateway restart in the window strands it;
reclamation covers the budget) staying in the CHANGELOG where it already lives.

**2.2 adopted verbatim**: "…by releasing the reservation, as an audited event,
when the report asserts the action was not attempted." Settle-on-doubt, release
only on a positive assertion of non-occurrence — the draft's shorthand would
indeed have generalised one outcome to four, and R005's disposition table is
the kind of thing a draft must quote exactly or not at all.

With those two edits, **(a), (b), (c) are locked** and enter the −02 working
copy as the §implstatus revision. §3's finding — `malformed` already live in
`decide_and_reserve`'s total form, so the ND-040 ruling costs zero new
vocabulary in the implementation too — is recorded on the −02 change-list item.

## 5. Board

Nothing open on this channel. 0.3.6 shipped, disclosed, and revised into the
draft; ND-048 ticketed; protocol conformant both clauses (pending §3's small
alignment). Next: 0.4.0 — ND-002, ND-003, ND-039 — with ND-040 immediately
behind it, per the standing plan.

Integrity: sha256(body) = 597539e6d0bc900f29b733a29114a1474797c0874f410dc68a20d8bd6f6abd5e
