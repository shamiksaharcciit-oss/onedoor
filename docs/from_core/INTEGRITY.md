# Memo archive — provenance and integrity

Core memos carry `Integrity: sha256(body) = <hex>` as their final line from Response
008 onward. The preimage was undefined when the footer shipped — a digest a verifier
must brute-force is verifiable only by luck — and was ratified by Response 009 after
the forensics session tried sixty candidates to find the true one:

> **The integrity preimage.** `body` = every byte of the file strictly before **the**
> line beginning `Integrity:`, with all trailing whitespace (including newlines)
> stripped, followed by exactly one LF (0x0A). Bytes as stored, UTF-8. SHA-256,
> lowercase hex. The blank separator line before the footer is **not** part of the
> preimage.

**Exactly one line may begin with `Integrity:`** — a producer obligation; quotations
are indented or kept mid-line. A verifier seeing more than one **MUST reject the file
as malformed**. Response 009 had amended the preimage to anchor on the *final* such
line; Response 010 **superseded that**, because the forensics session's independent
verifier raised instead — and two checkers returning different verdicts on one file is
the E005 defect class reproduced inside the memo protocol. The grounding was already
ours: ACJ rules duplicate keys `malformed`, never last-one-wins.

```bash
python -m scripts.verify_memo docs/from_core/*.md      # check
python -m scripts.verify_memo --table docs/from_core/*.md   # regenerate the register below
```

`tests/protocol/test_memo_integrity.py` runs both in CI: the archive must verify, and
the register below must match what the verifier emits.

## The digest register — generated, never transcribed

**R012:** *a digest in a ledger is generated, never transcribed.* Every digest below
was emitted into its cell by the verifier that computed it. A hand-copied digest is a
claim with no guard, and it will drift while staying green. Do not edit this block by
hand; regenerate it.

**The two registers must never mix.** The `Integrity:` **body digest** below is a
memo's canonical recorded identity. A **whole-file** hash is an *ephemeral transfer
aid* — used to prove a copy operation, then discarded, **never written into a ledger**.
This ledger previously recorded the whole-file hash of Core→Forensics 010 beside its
body digest; core circulated that number as the transfer identity for the disk-copy
operation and it landed in a cell meant for the other register. Removed — and the
value is deliberately not repeated here, because a hand-typed digest in a ledger is
the very thing the rule forbids, even when it is quoted as an example of the mistake.

<!-- BEGIN GENERATED digests: python -m scripts.verify_memo --table docs/from_core/*.md -->
| Memo | Body digest (`Integrity:` register) |
|---|---|
| `Core_Forward_003_Protocol_Clarification_2026-08-21.md` | `a3f0170a11508c8a5b432c7bf12c2493d5048b956ea707be8f16d01aab96253e` |
| `Core_Forward_004_Gate_Execution_2026-08-21.md` | `7960e78acc1485c403684849bdf4e896d9b3e34c87cb9c68baab7a28ccb7cde2` |
| `Core_Forward_004a_Exit_Codes_Travel_Badly_2026-08-21.md` | `7a375526ed54952a39f4252c6a0fa8d35ea5e264522b95df4689c53483f7aaf1` |
| `Core_to_Delivery_Response_001_2026-08-20.md` | none (predates the footer) |
| `Core_to_Delivery_Response_002_2026-08-20.md` | none (predates the footer) |
| `Core_to_Delivery_Response_003_2026-08-20.md` | none (predates the footer) |
| `Core_to_Delivery_Response_004_2026-08-20.md` | none (predates the footer) |
| `Core_to_Delivery_Response_005_2026-08-20.md` | none (predates the footer) |
| `Core_to_Delivery_Response_006_2026-08-20.md` | none (predates the footer) |
| `Core_to_Delivery_Response_007_2026-08-21.md` | `966b7461f2d1a727ad4ed645eaac32e0be03cd780342194022e1d8ec53b43631` |
| `Core_to_Delivery_Response_008_2026-08-21.md` | `a654483ce16c2a83def1254484699b5fc653e2b1c6d41d1c8a670042df7c8d80` |
| `Core_to_Delivery_Response_009_2026-08-21.md` | `850cda608c7ce3b9290791b182dd914c62d0359ae02be628593024bc544f86b1` |
| `Core_to_Delivery_Response_010_2026-08-21.md` | `b8f4038ad0b207c4d112de3d8ccee62f58c927cf7fc1a504712840f0f060c127` |
| `Core_to_Delivery_Response_011_2026-08-21.md` | `fd7b0a049ccd20de78a68f5fa4e25055bf5c37c5e70bfe184b1cf26fb16142be` |
| `Core_to_Delivery_Response_012_2026-08-21.md` | `fad86a64d2abfd1d42d815c8561a979ceef0f058909a35f66f23c0ec79346dab` |
| `Core_to_Delivery_Response_013_2026-08-21.md` | `a79efa6a4ca38ea663963f6e32167f655a6ef04bf286bfec9b536051b83d4748` |
| `Core_to_Delivery_Response_014_2026-08-21.md` | `597539e6d0bc900f29b733a29114a1474797c0874f410dc68a20d8bd6f6abd5e` |
| `Core_to_Delivery_Response_015_2026-08-21.md` | `4a4c5636248c939dbff7d7c2e750a4d7e9edc88b3cb873b6df26161e0c5c6c61` |
| `Core_to_Delivery_Response_016_2026-08-21.md` | `8cdbc4a2076c0f091e53282528b7352632b9e058dd16f638101fdd3afb85a14d` |
| `Core_to_Forensics_Response_009_2026-08-21.md` | `e2790fdd3fe7bfd30b28bb53f75ed131ae7d852564c9bd9d4183d49541120c0e` |
| `Core_to_Forensics_Response_010_2026-08-21.md` | `a8ec3640479a00d3f778936315298f26d290cabd2487314551302cab05f6faf4` |
| `Core_to_Forensics_Response_012_2026-08-21.md` | `a354be63d598c884ca842d972a2eb32c6c62bb0ce079f2b0f4c25f7ac3f01846` |
| `Forward_001_from_forensics_2026-08-21.md` | none (predates the footer) |
| `Forward_002_from_forensics_2026-08-21.md` | none (predates the footer) |
<!-- END GENERATED digests -->

## Provenance notes

Keyed by memo name, not by digest — the register above owns the digests.

| Memo | Note |
|---|---|
| 001–006 | Predate the protocol. Archived as received; no mechanical check is possible for these, and none is claimed. |
| 007 | **Arrived damaged twice.** The original relay and core's byte-clean re-issue *both* arrived UTF-8-decoded-as-cp1252 with the C1 continuation bytes discarded — lossy, so not mechanically reversible. The archived file is a delivery reconstruction from context, **subsequently proven byte-identical to core's original** by its own integrity footer. |
| 008 | Arrived damaged the same way; same reconstruct-then-verify path. Note it **quotes its own footer format in prose** — mid-line, so it stays well-formed, and it is why the FINAL-line trap existed. |
| 009 (delivery, forensics) | Both arrived damaged, both reconstructed and verified. The forensics one was forwarded under its own §3 and binds delivery. |
| 010 (delivery) | Arrived damaged; reconstructed, verified. |
| 010 (forensics) | **The one reconstruction that was wrong.** Three text deliveries arrived byte-identical to each other, including a zipped "byte-exact re-issue"; the reconstruction differed from core's bytes in a single character — `⇒` (U+21D2) where delivery guessed `—`, both collapsing to the same mojibake. Resolved only by a **disk copy** from the forensics repository. See `unverified/README.md`. |
| 011, 012 | **Arrived zipped and on disk, clean UTF-8, LF-only, verified first try.** No reconstruction. The relay fix works. |
| Forward 001, 002 | Forensics → onedoor, relayed via core. Carry **no footer by design**, so they are *absent*, not *unverifiable* — the three-outcome rule is why they are archived while 010-forensics was quarantined. Arrived only on the third attempt. |

## Why annotations live here and not in the memo files

Response 008 asked delivery to note an archive swap "in its footnote" — inside the
memo. **008's own protocol makes that impossible:** any byte above the footer changes
`body`, any byte below means the footer is not final. The integrity footer makes
archived memos immutable, and Response 009 §3 ratified the sidecar as the rule for
both sessions.

## Why the archive is `-text` in `.gitattributes`

Found by the forensics session and relayed (Core → Forensics 009 §3). `reference/`
and `patches/` were fenced from the start; `docs/from_core/` was still falling under
`* text=auto eol=lf`. Everything here is LF, so nothing was corrupted — but the first
CRLF memo would have failed its own digest and presented as **core sending a bad
digest**, the tampering-shaped diagnosis aimed at the wrong party. The general rule,
now normative for both sessions: *the moment an artifact carries a digest, every layer
between delivery and verification joins its trust path — version control included.*

## A false pass that nearly shipped

The first version of `verify_memo.py` matched the footer with a regex requiring LF, so
a CRLF-corrupted memo did not match, fell through to "no footer", and was reported as
**predating the protocol** — a silent pass on exactly the corruption the footer exists
to catch. Found by probing the gap rather than by reading the code; the earlier
both-directions check had only tested a content edit, never an encoding one. Absence
of a marker and a marker that does not verify are different facts and never collapse
now: `tests/protocol/` holds all three cases.

## What the relay has taught

Four failure modes, each found the hard way:

1. **Missing attachments** — Forwards 001 and 002 took three attempts.
2. **Lossy encoding** — UTF-8 decoded as cp1252, C1 continuation bytes discarded;
   `→`, `—` and `⇒` all collapse to the same byte and are unrecoverable.
3. **A re-issue can arrive identically corrupted** — the fix must change the *path*,
   not the intent. A zip pasted as text is still text.
4. **Reconstruction can be confidently wrong** — one character, invisible at the
   corruption layer. *Reconstruction produces a candidate; the footer decides.*

**What works: copy the file to disk, zipped.** `docs/incoming/` is fenced `-text` for
it. Memos 011 and 012 arrived that way and verified first try.
