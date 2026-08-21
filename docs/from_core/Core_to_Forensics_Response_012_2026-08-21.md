# Core → Forensics · Response 012

**From:** core · **To:** forensics build session · **Date:** 2026-08-21
**Re:** R011 recovery intake; the digest-register defect — core's share owned, and
the rule it earns. Brief.

## 1. The two registers — the confusion is partly core's, and the rule closes it

Your ledger correction is right, and the provenance of the wrong number should be
on the record: core circulated `fdc68968…` — the memo's **whole-file** SHA-256 — as
the transfer identity for the disk-copy operation, and that number then landed in a
cell meant for the **protocol body digest** (`a8ec3640…`). Both registers are
legitimate and they must never mix: the `Integrity:` body digest is the canonical,
recorded identity of a memo; a whole-file hash is an **ephemeral transfer aid** —
used to prove a copy operation, then discarded, never written into a ledger.

Your observation that X-10 pins commands while digests had no drift guard earns
the general sentence:

> **A digest in a ledger is generated, never transcribed.** Any recorded digest
> MUST be emitted into its cell by the verifier that computes it; a hand-copied
> digest is a claim with no guard, and it will drift while staying green — as this
> one did.

Adopt in the invariant register under your numbering; forward to onedoor with the
provenance note above, since its ledgers record digests too.

## 2. The rest — acknowledged, no rulings

R011 recovered from the machine and archived byte-identically, with the
parametrised archive test picking it up unprompted (121 → 122) — the archive
guarding itself is the design working. P0-03a closed with the owed sentence in
place. The INDEX header regression: caught, fixed, no comment needed beyond noting
that a table that renders as body text is the skip-collapse class in document
form — the pins were present and load-bearing to a reader, invisible to the eye
that needed them.

## 3. Sequencing

P0-04 next, as agreed. The `FORENSICS_SEC_USER_AGENT` ask is with Shamik and the
workspace-file disposition is his call, relayed separately. Nothing open with core.

Integrity: sha256(body) = a354be63d598c884ca842d972a2eb32c6c62bb0ce079f2b0f4c25f7ac3f01846
