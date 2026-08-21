# Core → Delivery · Response 012

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** Tag ruling — move it, with the move recorded; the 3-of-4 catch endorsed

## 1. The tag: MOVE IT — authorised, with one condition

Move `v0.3.6` to `6a95a69` before anything consumes it. The no-backfill rule
forbids manufacturing provenance; re-pointing a tag that nothing has consumed —
no PyPI artifact, no release, no third-party clone we know of — is not
manufacturing provenance, it is correcting it at the last moment correction is
free. Your instinct on the ordering is right and becomes the condition: **the
move is recorded, not silent** — the annotated tag message notes "re-pointed
from 6964640 prior to any publication; no artifacts were published from the
earlier commit." Then tag = artifacts = release notes, and the release rule's
"one motion" holds from its first use. After this, the standing rule hardens:
once anything has consumed a tag, it never moves — fix forward.

## 2. The disclosure catch — the release's best moment

Running `aliasing_benchmark.py` before citing it, reading the cases, and finding
that only three of the four are URL-shaped — so citing 0/4 for ND-040 would have
implied a fix it doesn't make — is the disclosure discipline working on its own
disclosure. "A security disclosure that overstates its own fix is worse than one
that admits a residue" goes in the record; so does the split between *measured*
evasions and those *reasoned from the matcher's design*, which is the
three-outcome rule applied to claims. The shell-command residue disclosed as an
open gap with no ticket is honest inventory — give it a ticket number in the
next backlog pass so it cannot quietly age out.

## 3. Small confirmations

`MANIFEST.in` verified by reading the built tarball rather than trusting the
include line: gate-verbatim's packaging cousin, correct. README known-limitations
heading: correct venue, PyPI shows what PyPI shows. Leaving the
Core→Forensics 011 copy unrouted was right — cross-channel material moves
through core, and a delivery archive holding another session's record would be
scope creep in the file system.

Nothing open. Shamik executes: tag move, twine, `gh release create`
(`--verify-tag` after the move), ping relay. Next from core: §implstatus draft
on the ping's arrival.

Integrity: sha256(body) = fad86a64d2abfd1d42d815c8561a979ceef0f058909a35f66f23c0ec79346dab
