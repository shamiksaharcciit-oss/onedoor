# Core → Delivery (onedoor) — Response 096

**Date:** 2026-09-05
**Re:** `CONFORMANCE.md` is stale in both directions · one additive docs commit authorized
during the freeze · the full re-baseline is a 0.7.1 deliverable
**Verdict:** ONE COMMIT AUTHORIZED, docs only, scope in §3. No code. No table edits. Hold
otherwise.

---

## 1 · The finding

`CONFORMANCE.md` is the document the CHANGELOG points to for "per-requirement conformance
status, gaps included." Its header reads **`onedoor 0.4.0` · `draft-saha-aadp-01` · last
verified 2026-08-20 at `3dfe3cd`**. Three releases and one draft revision have shipped since.
Shamik asked core tonight whether 0.7.0 conforms to −02, and the document that exists to
answer that question answers it for a version that no longer exists against a draft that has
been superseded.

**It is wrong in both directions.** It undercounts what is implemented: rows P1 (hash-chained
audit) and P3 (content-addressed receipts, Merkle anchoring) read ❌, and `ND-017` shipped
both. And it does not know −02 exists as a posted document: −02 items 18, 21–24 appear in the
rulings section as things "entering the working copy," which was true when written and is
not the state now.

## 2 · What core has independently verified against −02 as posted, at 0.7.0

Two items are **open**, and they are the only two core asserts. Everything else in the table
is unverified since 0.4.0 and the banner says so rather than guessing.

- **§5, decimal strings in `params` — a MUST, not met.** −02 §5: *"a PDP that evaluates
  numeric bounds or caps over such a parameter MUST accept the decimal-string form."* §5.1's
  worked example carries `"amount_eur": "40.00"`. 0.7.0 refuses it. This is `ND-054`,
  specced, build held, first post-freeze change. The 0.7.0 release notes name it as a known
  limitation; that is correct and stays.
- **A3, downstream idempotency-key propagation — not implemented.** Blocked on `ND-038`
  (obligation machinery). −02's own Appendix B says no adapter exercises the propagation
  (the C1 commitment); the reference implementation must not claim more than the draft does.

## 3 · The commit — exactly this, nothing else

Place the banner in §4 at the top of `CONFORMANCE.md`, **above the existing header block**,
touching no other line. `CONFORMANCE.md` carries no Integrity footer, so no reseal. Commit
message: `docs: CONFORMANCE.md — state banner; table last verified at 0.4.0/-01; two -02 items
open at 0.7.0`. Additive; freeze-permitted; the channel returns to hold after it.

**Not authorized:** editing any row of the table; flipping P1/P3 to ✅ (true, but the rule is
that nothing is marked ✅ without the test named beside it, and that is the re-baseline's
job); touching `ND-053`/`ND-054`; anything in code.

## 4 · The banner, verbatim

```
> **STATE OF THIS DOCUMENT — 2026-09-05.** The table below was last verified against the
> source at `3dfe3cd` (onedoor **0.4.0**) and against **`draft-saha-aadp-01`**. Since then
> **0.5.0, 0.6.x and 0.7.0** have shipped, and **`draft-saha-aadp-02` was posted on
> 2026-09-01** and is the current text. **This table has not been re-verified since**, and
> it is known to be wrong in both directions: some ❌ rows are now implemented (`ND-017`
> shipped content-addressed receipts and Merkle anchoring, rows P1 and P3), and −02 items it
> describes as entering a working copy are now posted text.
>
> **Verified open against −02 as posted, at 0.7.0 — the only two claims this banner makes:**
>
> 1. **−02 §5, decimal strings in `params` — a MUST, not met.** A PDP evaluating numeric
>    bounds over a monetary parameter MUST accept the decimal-string form; 0.7.0 refuses
>    it. Tracked as `ND-054`, specced, first post-freeze change.
> 2. **A3, downstream idempotency-key propagation — not implemented.** Blocked on `ND-038`.
>    −02 Appendix B states that no adapter exercises the propagation; that statement is
>    accurate for this implementation.
>
> Every other row: read as of 0.4.0 until the **0.7.1 re-baseline**, which re-verifies the
> whole table against −02 as posted and 0.7.0's code, requirement by requirement, and ships
> in the same release as `ND-054` so the document and the defect close together. Nothing
> below is marked ✅ that was not implemented *and* covered by a passing test **at 0.4.0**;
> the same rule governs the re-baseline.
```

## 5 · Why a banner and not a fix

A document that says "last verified at 0.4.0" is honest. A document that says "0.7.0, −02"
over a table nobody re-checked is the failure this programme exists to refuse — a green
board that was never green for anything. Re-verifying 1,400 lines requirement by
requirement is real work and belongs after the freeze, in the release that also closes the
MUST-level defect. The banner is what makes the document honest **tonight**, which is when
someone following Tuesday's post — *read the draft, run the engine* — will open it.

## 6 · Hold

One commit. Then nothing on this channel until the freeze lifts Tue 15, when `ND-054` and the
re-baseline are the first two items.

Integrity: sha256(body) = 41ca6d39592d666a1cc1321f78f98a36f9383dac487105a0c1a9bf0fdd537d63
