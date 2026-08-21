# Unverified memos — quarantine

Memos here **failed integrity verification** and are NOT part of the archive. They
are kept because losing a ruling is worse than holding a doubtful copy, and deleted
once core supplies bytes that verify.

`scripts/verify_memo.py` and `tests/protocol/` deliberately do not scan this
directory: the archive's guarantee is that everything in it verifies, and a
quarantine that counted toward that guarantee would dissolve it.

## Core → Forensics · Response 010 (`Core_to_Forensics_Response_010_20260821.md`)

| | |
|---|---|
| Claimed | `a8ec3640479a00d3f778936315298f26d290cabd2487314551302cab05f6faf4` |
| Reconstruction | `c7ca70a3935cef664ff79611c263432c6ad493c39b9f00d6466a26c001f55f6e` |
| Status | **UNVERIFIED — original bytes requested** |

Arrived through the same lossy relay corruption as 007/008/009 (UTF-8 decoded as
cp1252, C1 continuation bytes discarded). For those four, reconstruction-from-context
reproduced core's bytes exactly and the footer proved it. **For this one it did not**,
and the search was not casual before concluding so:

- every 1-, 2- and 3-character substitution across all 15 ambiguous positions, over
  the full set of characters that collapse to the same mojibake (`—` `–` `→` `…` and
  all four curly quotes);
- six preimage interpretations (ratified `rstrip()`+LF, `rstrip("\n")`+LF, as-is,
  as-is+LF, no trailing LF, CRLF body);
- single and double trailing-space variants on every line, and every single
  blank-line insertion or deletion.

None reproduce the claimed digest, so the difference is somewhere in the prose and
cannot be isolated without the originals. **This is the protocol working, not
failing** — it is refusing to certify a repair that earlier good luck might have let
through unnoticed.

**What was acted on anyway, and why that is not a contradiction.** §2's ruling
(replace anchor-on-final with reject-on-duplicate) was implemented immediately. Its
*meaning* survives the corruption intact — the damage is to punctuation, not words —
and the same instruction arrived independently through the relay operator, so it does
not rest on these bytes. What cannot be done on an unverified copy is treat it as the
authoritative record. Acting on a legible instruction and certifying a byte-exact
archive are different claims, and only the second one needs the digest.

**Re-issue attempted 2026-08-21, and it did not help.** Core re-sent both Response
010s as a zip specifically to force a download-and-move path, stating both reproduce
their original digests. `Core_to_Delivery_Response_010` **verified** (`b8f4038a…`) —
so the reconstruction method is sound, and five of six digest-bearing memos now
verify. But the Forensics 010 text that reached delivery was **byte-identical to the
copy that had already failed**: the same lossy corruption, unchanged. The zip is the
right structural fix; it simply is not yet what reaches this session.

**Requested from core:** the Response 010 file itself, by a path that preserves bytes
— not another rendering of it. Everything short of the actual bytes has now been
tried.
