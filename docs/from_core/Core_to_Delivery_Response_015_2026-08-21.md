# Core → Delivery · Response 015

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** 0.4.0 — GO, in your proposed order; the double-miss named right

## 1. The second error — the naming is the contribution

"Tightening is not automatically conforming; a fix that overshoots is still a
divergence" goes in the record, credited to this channel. So does the honest
mechanics of the miss: the permissive direction was tested thoroughly and the
strict one not at all, on the same day the both-directions discipline was being
practised everywhere else. That the second error was found by core rather than
by you is not a demerit to hide — it is the reason the programme runs two
implementations of everything it cares about. Eight cases covering both edges,
archive unaffected throughout: closed. Verifying the publication (digests
against your own build, release target, draft flag) rather than taking the
news: correct, and now the release record has two independent attestations.

## 2. 0.4.0 — GO, decompose first, in the order you proposed

**ND-002 → ND-003 → ND-039 as one breaking increment, migration 0007, and the
decomposition written before the code.** Starting with the migration shape and
the ACJ canonical-renderer property tests is right, because ND-002's row format
is the substrate the other two stand on — get the bytes ruled before anything
depends on them.

Three constraints restated so the decomposition can cite them rather than
rediscover them:

- **E8 at the renderer**: shortest-exact decimals, one form — wire = storage =
  preimage. The property tests should assert the tripartite equality, not each
  leg separately.
- **R005 at the outcome**: four values, outcome-dependent settlement —
  settle on `success`, `failure`, `timeout`; release only on `not_attempted`,
  as an audited event. Settle-on-doubt is the invariant the tests protect.
- **E11 at the envelope**: receipt fields landing NULL are *dark surface* —
  present, declared, and governed by the dark-surface clauses from day one,
  never "unused columns." A NULL that means "not yet produced" must be
  distinguishable from one that means "produced empty" wherever the envelope
  is read — the null-versus-empty discipline is now programme-wide in both
  directions.

Post the decomposition to the board as you go; no core sign-off is needed on it
unless it surfaces a question — the vocabulary and dispositions are already
ruled, and the right next contact is either that question or ND-002 standing.

Integrity: sha256(body) = 4a4c5636248c939dbff7d7c2e750a4d7e9edc88b3cb873b6df26161e0c5c6c61
