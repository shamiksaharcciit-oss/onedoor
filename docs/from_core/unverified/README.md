# Unverified memos — quarantine

**Currently empty.** Kept, with its record, because the protocol it documents is live.

Memos land here when they **fail integrity verification**. They are not part of the
archive and do not count toward its guarantee: `scripts/verify_memo.py` and
`tests/protocol/` deliberately do not scan this directory, because an archive whose
guarantee is "everything here verifies" dissolves the moment a quarantine counts
toward it. Files are deleted from here once core supplies bytes that verify.

## Resolved: Core → Forensics · Response 010

Quarantined 2026-08-21, resolved the same day. Now archived as
`../Core_to_Forensics_Response_010_2026-08-21.md` — body digest `a8ec3640…`,
whole-file `fdc68968…`. Renamed from forensics' `20260821` dateform to delivery's
`2026-08-21` convention; **the digest is the identity, not the filename**, and both
are recorded in `../INTEGRITY.md`.

### What resolved it

Not another rendering. Three deliveries of this memo arrived as text through the
lossy relay and **all three were byte-identical to each other** — including a zipped
"byte-exact re-issue" whose whole purpose was to defeat that path. What worked was a
disk copy of the file from the forensics repository's verified archive.

### What delivery got wrong, which is the part worth keeping

The reconstruction differed from core's bytes in **exactly one character**, on line 37:

```
mine:  ACJ rules duplicate keys — `malformed`, not
core:  ACJ rules duplicate keys ⇒ `malformed`, not
```

`⇒` (U+21D2) encodes as `E2 87 92` and collapses to the same bare `â` as an em dash,
so it was invisible at the corruption layer. The brute-force search that failed to
find it covered 1-, 2- and 3-character substitutions across all 15 ambiguous
positions — but over a **hand-picked** candidate set of eight characters (`—` `–` `→`
`…` and four curly quotes), assembled from what previous memos happened to contain.
U+2000–U+21FF alone holds 512 characters that collapse identically.

Worse: `⇒` appears **five times in this repository's own `CONFORMANCE.md`**, including
`non-UTF-8 ⇒ deny malformed` — the same implication-arrow construction core used. The
character was already here, in a semantically identical sentence, and still was not in
the search space.

This is `CLAUDE.md` discipline 4 turned on its author: *spot-checks find only the
violations you thought of.* A candidate set drawn from observed data reproduces the
bias of that data. It is the same failure as the nested-`additionalProperties` defect
surviving two independent probes of the manifest artifact.

### Why the quarantine was not pedantry

Had the reconstruction been archived as instructed, `docs/from_core/` would now hold a
memo whose normative sentence reads `duplicate keys — malformed` instead of
`duplicate keys ⇒ malformed`, certified as core's bytes. The meaning survives here by
luck. **The digest is the only reason anyone knows the reconstruction was wrong** — and
by extension, the only reason to believe the five that verified were right.

**Standing rule, reinforced:** never archive an unverified repair, and never treat
reconstruction as recovery. Reconstruction produces a *candidate*; the footer decides.
