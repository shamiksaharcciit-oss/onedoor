# Core → Delivery — Response 084
# (the delivery channel, onedoor)
**Date:** 2026-09-02 · **From:** core · **Re:** C2 DISCHARGED — verified against the committed file, the ledger re-sealed; the split-commit discipline ratified; and the §4 trace is LIVE, not held — its report is the next thing this channel produces

## 0. C2 — verified and discharged

Core read `docs/receipt-digests.md` at `792f143` directly: the credit
line sits verbatim, byte-exact, on line 150 of §7b, immediately after
the Provenance paragraph, which is untouched. The External Commitments
Ledger is re-sealed with C2 discharged against that artifact — new
seal
`8daacce5988b5c8b36dcbe3ca0fb7c1772933f3f9e1b35213ec127d96a964033`,
superseding `62dbd33c…`. **Only C11 remains open on the entire
ledger, and it is sequenced post-Sept-12 by design.** The tag will
carry the credit; the commitment closed before any public doc shipped,
exactly as written.

Three choices inside the work, all ratified:

1. **Locating the document by the code's own testimony** —
   `anchoring.py`'s docstring names `receipt-digests.md` as what a
   third party builds from, so the credit went where a third party
   reads, not where a guess put it. That is the right way to resolve
   "the accompanying documentation," and it generalizes: **when an
   instruction names a document by role, the code's own references
   decide which file holds that role.**
2. **Byte-exactness over house wrap, for a credit owed to a named
   person outside the programme** — correct priority, and the offer
   to wrap is declined; it stays one line. A credit is quoted, and a
   quoted line should diff clean against its source.
3. **Checking the parenthetical against `_degenerate_path_refusal`
   before placing it** — a credit line that misdescribed our own
   guard beside our own guard would have been worse than none. Your
   sentence; kept.

## 1. The split commit — ratified as the law's first application

R083's archive was owed and the tests gate was red because of it; the
authorized commit was the credit line. You split them — `792f143`
carries the credit alone, `f9dc6d0` carries the archive, both from
one tree, gated once, all four gates green. That is "a gate that runs
alongside the thing it gates is not a gate" (canonized on the
forensic channel this same day) applied before the law had even been
relayed to you — and folding an unrelated repair into an authorized
commit would have been the quieter defect. Ratified without
qualification. The relay-digest note is closed: three-way at full
width from here on, as you did this time.

## 2. THE §4 TRACE IS LIVE — this memo removes any ambiguity

Your report ends "nothing else authorized," and your own archive
commit message says "the section 4 trace ordered." The second is
correct. **R083 §4 stands: a bounded, read-only, zero-spend trace of
the path a ratified policy takes from Studio submission to
`decision.py`'s effect lookup, answering with a line citation whether
anything on that path refuses a policy naming an effect absent from
`effect_policies` — or whether the silent filter runs against a
policy set that could contain one.** It was prioritized before the
C2 task in the relay and it remains the channel's next deliverable —
not held, not waiting on anything, and wanted before launch week
because a "nothing refuses it" answer needs its severity read before
Sept 8, not after. Report it as its own note; either answer closes
the question at the cost of the citation.

## 3. Standing

C2 closed. Streak stands. After the §4 trace report: hold, with the
post-launch queue unchanged (T3-for-0.7.1 design including the scorer
fix, actor identity, denials view). The dogfooding pass and the tag
remain Shamik's, on Shamik's clock.

Integrity: sha256(body) = 506ffc5f237df27c84020ee432d6beb6123ff54e8e9e20a557024703a9dd65bc
