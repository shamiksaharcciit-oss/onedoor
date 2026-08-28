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
| `Core_Forward_005_Seal_Test_Shape_2026-08-28.md` | `f3142274d08892e195217c53e082e8b5515a917667dd08b2b042bca194e02ba2` |
| `Core_to_Delivery_Response_001_2026-08-20.md` | none |
| `Core_to_Delivery_Response_002_2026-08-20.md` | none |
| `Core_to_Delivery_Response_003_2026-08-20.md` | none |
| `Core_to_Delivery_Response_004_2026-08-20.md` | none |
| `Core_to_Delivery_Response_005_2026-08-20.md` | none |
| `Core_to_Delivery_Response_006_2026-08-20.md` | none |
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
| `Core_to_Delivery_Response_017_2026-08-21.md` | `5098f0de6dd4134c840cdf7b9125b8f9dc966db49e30d706387734a95c70fa2d` |
| `Core_to_Delivery_Response_018_2026-08-21.md` | `28970b931f5b695b52989c2844869b2c59e69c8b9274280b5a90474731387757` |
| `Core_to_Delivery_Response_019_2026-08-21.md` | `8389336850ceec67b105da229bdf28605565c98bd911432a42dae1d353f9ad28` |
| `Core_to_Delivery_Response_020_2026-08-21.md` | `c2957c74e32cde0b4d83b8411a27b4f703a1ef7e0982a2ef31bafd0a981aed37` |
| `Core_to_Delivery_Response_021_2026-08-21.md` | `3e29ced8f6c73f12ff494bcd6441860f793b78f6891a1f648a045d4c4813ebe7` |
| `Core_to_Delivery_Response_022_2026-08-21.md` | `569c22ae3049483e4dcc98a0859d5e2d18a1c2492f68a1a6a6ac6e9a4df9acf6` |
| `Core_to_Delivery_Response_023_2026-08-22.md` | `a7ffd0608587efcc999ec644ba891b1ab47c101f0e2bfb6a987fe0c9a0d31950` |
| `Core_to_Delivery_Response_024_2026-08-22.md` | `3f0888f2c621c83f461ce7c07c8a79b202971008401cd50d4eddc319ebc2ffc8` |
| `Core_to_Delivery_Response_025_2026-08-22.md` | `d931e283a8a2526def3b92b16239fc9ba39708e4ae57d782b469dd50e438c5d0` |
| `Core_to_Delivery_Response_026_2026-08-22.md` | `45fac7f87442f8b22ccc003f6e2bb40b46d79c87d90916343cd08b8823560f75` |
| `Core_to_Delivery_Response_027_2026-08-22.md` | `a4eafe1c207feef97caac0c238a31d73c62e0d4cd694f7b2fbff65eac26f62bb` |
| `Core_to_Delivery_Response_028_2026-08-22.md` | `583f8603cd306f97e3f1414261a938cad920106121506f43d3f72d51d922088b` |
| `Core_to_Delivery_Response_029_2026-08-22.md` | `8fe0e87aec0fb74fd53a594eeda62932bb651ae584afa700148100e18c0af87b` |
| `Core_to_Delivery_Response_030_2026-08-22.md` | `4f25077e92eef7c4f7c14960b1bdaab852cd65ec44fada87f68dcab0bce3f49d` |
| `Core_to_Delivery_Response_031_2026-08-22.md` | `47953f3758165750efe219bc94ef01bec40fc3dde1c981ee02acc96c5f097379` |
| `Core_to_Delivery_Response_032_2026-08-22.md` | `6a59dafc33efcf2c12fe2605e6571e0d8455ba552f2ace89b481cbf72ea7c2fe` |
| `Core_to_Delivery_Response_033_2026-08-22.md` | `91f4a6608253f63d5a2d9d3076658c6588beac815e860c5abb493e8e31c48e1b` |
| `Core_to_Delivery_Response_034_2026-08-22.md` | `a1a1c9b9da9d7cf6b835ab1f483ee1f338456ca64c7fb145236d825a2da8ba57` |
| `Core_to_Delivery_Response_035_2026-08-22.md` | `7e9e952854fd91857f8c50215ad9b3679a2b1296578d319422c02e49631974aa` |
| `Core_to_Delivery_Response_036_2026-08-22.md` | `3fa5b06ae89bbc35c3508eaa00b8cc968339891d639293941f9922dce9013a5d` |
| `Core_to_Delivery_Response_037_2026-08-22.md` | `0ea90cdad3704507ddac40e3b749c09b0b4bb231545ccc3924c6281df9ed5947` |
| `Core_to_Delivery_Response_038_2026-08-22.md` | `a63ce43de43ed46024944f838e28c9314cf6c7165ec53ac4c3a662f0ec896617` |
| `Core_to_Delivery_Response_039_2026-08-22.md` | `ed4ff50453c11ace181359d3d8ffe5b064dd004732402b2d19ce7dcb71e59863` |
| `Core_to_Delivery_Response_040_2026-08-22.md` | `b266a42703ebd95847a4774f6f9d0f2a1f5268f918fd8ea17841e83510446b39` |
| `Core_to_Delivery_Response_041_2026-08-23.md` | `1f3f67e0c5f0d5822b4beca421e52bbea8e72a2de7ffc1defec9568d092b65d2` |
| `Core_to_Delivery_Response_042_2026-08-23.md` | `4b359332ff7a7ef8f335369646e423e4adf4be57b03c4390cfce8f9bd3256bfe` |
| `Core_to_Delivery_Response_043_2026-08-23.md` | `9d5746af7954ed8c36b12d1d9f16eaefc3996dd41c4677d7af86c324c4f5d4f3` |
| `Core_to_Delivery_Response_044_2026-08-23.md` | `6ff06c8ce1667c7ccdaa70b06fde140f65d46d965e2573a6d146db0f04b99608` |
| `Core_to_Delivery_Response_045_2026-08-23.md` | `db9d56e8ff775fd5f5ace4a885f6963cdc282de32e2a207040df37bae03a8449` |
| `Core_to_Delivery_Response_046_2026-08-23.md` | `8691ae39114181360e83b65b1ef0422fe4b31a15ce79582e2916216f4f1376d9` |
| `Core_to_Delivery_Response_047_2026-08-23.md` | `ab02d6b7ffc3850725135333566e2d3cf34f0180c7f7b82f2c762fbc4a2bd5a8` |
| `Core_to_Delivery_Response_048_2026-08-24.md` | `ae8d3028c44fefb7338a9c079ef28b3772584d09386ddb86e456126819944e02` |
| `Core_to_Delivery_Response_049_2026-08-24.md` | `d262c67dd6228b66203388319461aa25591ce1428e87f60f0dabd4effc96c8c9` |
| `Core_to_Delivery_Response_050_2026-08-24.md` | `61274c6360985b7878c5c3e172ee2c6bd950d75457cc3a6b1160906e88c60136` |
| `Core_to_Delivery_Response_051_2026-08-24.md` | `d07edfdb8c349eac1a8f3718273d910505b28213bd4fa3f386931494072e579a` |
| `Core_to_Delivery_Response_052_2026-08-27.md` | `d15901d865030a056879ec4d3fa68811cf4c231c55d6b7baa2a11ac6289aaa48` |
| `Core_to_Delivery_Response_053_2026-08-27.md` | `eb4c7e3a478c3d8e3f3bcca9e5cd795c87ccc1682ed202bbda53e7513c012051` |
| `Core_to_Delivery_Response_054_2026-08-27.md` | `f6610a9b4215277ffb34c04299d0fe75edd3208ab6a94421b473d3a19e5470ff` |
| `Core_to_Delivery_Response_055_2026-08-28.md` | `95dd6ea60cdb4e7f18a7531ec659cdc5af234488b43228cfb971f65297235bf5` |
| `Core_to_Delivery_Response_056_2026-08-28.md` | `6cf8948633ea584ab856729edce089ceef2316cff800ad69091d09a29d23acf0` |
| `Core_to_Delivery_Response_057_2026-08-28.md` | `053b793b448f25798f83aaa79800b39cdf88bab5c12e8a01b2a39fd2315ee013` |
| `Core_to_Delivery_Response_058_2026-08-28.md` | `76be21c52f557931e627980b4220c5c37cedaea41e164ebebab6d12fdfb79451` |
| `Core_to_Delivery_Response_059_2026-08-28.md` | `cc63903c9ccd2ec869ebffcdb05bbc3edc51a506db49a6439f1a4c0da25b1694` |
| `Core_to_Delivery_Response_060_2026-08-28.md` | `0bccc9914fe2ba61b7ee454d8ee36b0520c2ccd00fef5168e0b799988f2de7b4` |
| `Core_to_Delivery_Response_061_2026-08-28.md` | `92bc962a1a37670d5fd763c4ccb2e9674627044fce9adbc76b3242c929d2db3a` |
| `Core_to_Delivery_Response_062_2026-08-28.md` | `f28c1e4c28c2d6214ebb6c3e4189f0306a4ff3b07a277d0cb534743c52e7c1fb` |
| `Core_to_Delivery_Response_063_2026-08-28.md` | `774354fb3c10dffda6cb72b49a3a4e97cf7114aa765efb3dfef437e46a01e853` |
| `Core_to_Delivery_Response_064_2026-08-28.md` | `ec942c80e59f27095e6360175e2104f2758080fddb92969269f46495098133ec` |
| `Core_to_Forensics_Response_009_2026-08-21.md` | `e2790fdd3fe7bfd30b28bb53f75ed131ae7d852564c9bd9d4183d49541120c0e` |
| `Core_to_Forensics_Response_010_2026-08-21.md` | `a8ec3640479a00d3f778936315298f26d290cabd2487314551302cab05f6faf4` |
| `Core_to_Forensics_Response_012_2026-08-21.md` | `a354be63d598c884ca842d972a2eb32c6c62bb0ce079f2b0f4c25f7ac3f01846` |
| `Design_Note_Policy_Studio_V2_2026-08-28.md` | `118c61b3cc83712053820b76dc6320619141b3a2f49bb56f8fd3afbfd7a724ca` |
| `Forward_001_from_forensics_2026-08-21.md` | none |
| `Forward_002_from_forensics_2026-08-21.md` | none |
| `Policy_Studio_Design_Note_2026-08-22.md` | none |
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
| `Policy_Studio_Design_Note_2026-08-22.md` | Delivered alongside Response 029, which **is** footered and verifies. The note carries **no footer**, so under **R030 §2** it is **ABSENT — no integrity claim**: never rejected, and never blended with *unverifiable*, which would invent a claim nobody made. Note it does not predate the protocol (it is dated 2026-08-22), so absence here is about the artifact's kind rather than its age — a design note is not a memo. R029's footer covers the *instruction* to ticket it; it does not cover these bytes, and nothing does. **Observation, not a claim** (R030 §2: the register holds producer claims, the sidecar holds observations): observed sha256 `aa8cd7c50043c2ef1768d5658b0197750d3b883190e0ab0f6aa1fd1c9ade022b`, 2026-08-22 — computed by delivery over the copy in this directory, true of these bytes on that date and asserting nothing about who sealed them. It is here and not in the register precisely because the register's one meaning is *the producer sealed this*. |
| `oneview.html`, `ONEVIEW_DESIGN_SPEC.md` | Delivered in `docs/oneview/`, not here, and likewise unfootered. The spec is pinned instead by `onedoor/viewer/tokens.py` (`SPEC_DIGEST`, `SPEC_FENCE_DIGEST`) and a test proves the vendored copy is byte-identical to the delivered one — a different mechanism reaching the same guarantee for an artifact the build depends on. |

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
