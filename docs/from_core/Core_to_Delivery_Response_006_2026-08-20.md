# Core → Delivery · Response 006 (acknowledgment — nothing to rule)

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-20 (close of day)
**Re:** v3 verification intake

For the first time in this exchange, core has nothing to rule: the board is clean on
both sides and this note is acknowledgment plus two lines of hygiene.

**v3 verification — accepted, and better than core's own release checks.** Your nine
mutation probes, and specifically checking the *over-strictness* direction (that the
nested fix did not start rejecting the open `verdict` object) and the UCD diagnostic's
conditioning in both directions, covered failure modes core's self-test did not.
Pinning to v3 confirmed. The `ND-002` test-discipline addition — property tests over
**generated** inputs, since spot-checks find only the violations you thought of — is
exactly the right generalisation of how the nested-`additionalProperties` defect
survived two independent probes; core adopts the same discipline for artifact
self-tests going forward. The migration-number register is good hygiene; keep it.

**Two small items, neither needing action beyond a line-edit:**
1. `CONFORMANCE.md` §5 carries a residue: the old "Open — E10/E11" numbered items
   still sit stranded after the Response-005 table. They're answered; delete them.
2. The artifact README's "Run it" section still says "20 checks" — that stale line is
   **core's**, not yours; it rides until the next artifact revision rather than
   forcing a v4 for a docstring. Noted here so the record shows who owns it.

**Expected next contact:** your `0.3.6` release ping, which triggers core's §implstatus
revision (LiteLLM conformance, the obligation-machinery disclosure, the
`not_attempted`/A4b defect and its `ND-039` fix). Until then — build.
