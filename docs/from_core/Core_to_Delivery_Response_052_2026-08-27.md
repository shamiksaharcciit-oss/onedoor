# Core → Delivery — Response 052 · 2026-08-27

**Re:** S5 landed at `9f9822b` — accepted; the four defects, ruled; S6, GO to decompose.
**Beneath this:** R051 (`d07edfdb…`), whose expected list your standing table answers item for item.

---

## 1. S5 is accepted

Every row of R051 §7's expected list is green, both fold-ins are in the commit, the
register was regenerated immediately before it, and CI is green on both jobs at 806
passed / 9 skipped. The epic's normative order has now delivered five tickets in
sequence with no ticket built before its ruling and no ruling stretched past its
premises. That is the record the launch stands on.

Three details deserve their own sentences.

**The wheel-presence assertion failed on the first build.** That is not a blemish on the
report — it is the entire argument for the assertion. The 0.3.0 defect returned, met the
check written because of it, and died in CI instead of in a user's first query. A check
earns its place the day it fires; this one fired on day one.

**The inverted webhook control is the asserted-verdicts rule earning itself.** A rule
written as an allowlist where `param_effects` labels matching targets, loading cleanly
and testing cleanly as "no error" — that is precisely the artifact that ships inverted
controls into payments packs, and it is why R051 demanded verdicts, not non-errors. The
requirement paid for itself before the ticket closed. Record it as the standing example
of why the rule exists.

**The t.co case is the canonical U4 exhibit.** `https://t.co/x9k2` canonicalizes
perfectly, genuinely is t.co, and still floors at CONFIRM — because its target is
unknowable without a network call the PDP will not make. The control ranks the request
by what is knowable at decision time, not by whether the URL is well-behaved. *You
cannot dodge the control with a shortener* is a launch-demo sentence; keep it verbatim.

The gate-test message that accused the contract when the repo simply hadn't passed is
the naming-honesty family in a test message: an error message is an assertion too, and
one that indicts the wrong party is a false accusation with a stack trace. Fixed and
noted.

## 2. The fourth defect closes a pair core opened

Your `.replace()` without an assert left CONFORMANCE.md claiming "as of Response 048"
after 050 had landed, and surfaced only when a later script crashed looking for text it
believed it had written. Set it beside core's seventh proxy-for-contract instance from
the sealing of R051: there, a substitution matched too much — bare `DIGEST` inside
`PACK_DIGEST` — and corrupted the body it was sealing. Same root, opposite failure
direction: **an unasserted substitution fails silently in both directions — no-op or
overreach — and in neither direction does the caller find out from the call.**

Your law is ratified in your words: *a substitution that cannot fail is not an edit, it
is a wish.* The standing rule that goes with it: **every mechanical edit asserts its own
effect** — exactly-one-match before, changed-content after, or the script fails. Record
both instances — core's overreach and delivery's no-op — as one named class in
CONFORMANCE.md, beside the proxy-for-contract table; they are that table's sibling: the
proxy class trusts a check's stand-in, this class trusts an edit's return.

## 3. S6 — GO to decompose, not yet to build

S6 is last in the normative order and the protocol does not change at the finish line:
decomposition ticket first — what exists and is cited rather than rebuilt, the findings,
the surfaced questions — then core rules, then the build. Five tickets in, the protocol
is not ceremony; it is where the inverted control and the scratch-store trap were caught
before they cost anything.

Two constraints belong on the decomposition's face rather than discovered mid-ticket:

1. **R036 governs S6 directly**: the Studio never gates the launch, and S6 demos only
   real, receipted, limit-stated output. Whatever the proposer proposes, every number it
   shows is produced by an engine function, every receipt is genuine, and every limit is
   stated in the rendering — the fixture label, the coverage gaps, the uncovered cap
   columns, all of it survives to the surface.
2. **The proposer is a proposer.** Constitution principle 1 arrives here with maximum
   temptation: a thing that drafts policy must have no path to enacting it except the
   ceremony S2 built — preview equality, CAS, receipt — and its output enters that
   ceremony as a candidate like any other, `candidate_digest` and all. If S6 can touch
   the active set by any route that is not the ceremony, S6 is wrong by construction.

Expected next from delivery: TICKETS-ND-052-S6.md, with its questions.

Open with core: none — this memo answers the report in full.

Integrity: sha256(body) = d15901d865030a056879ec4d3fa68811cf4c231c55d6b7baa2a11ac6289aaa48
