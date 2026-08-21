# Memo archive — provenance and integrity

Core memos carry `Integrity: sha256(body) = <hex>` as their final line from Response
008 onward. The preimage was undefined when the footer shipped — a digest a verifier
must brute-force is verifiable only by luck — and was ratified by Response 009 after
the forensics session tried sixty candidates to find the true one:

> **The integrity preimage.** `body` = every byte of the file strictly before the
> **FINAL** line beginning `Integrity:`, with all trailing whitespace (including
> newlines) stripped, followed by exactly one LF (0x0A). Bytes as stored, UTF-8.
> SHA-256 over `body`, lowercase hex. The blank separator line before the
> `Integrity:` line is **not** part of the preimage.

`scripts/verify_memo.py` implements exactly that, FINAL included. Check the archive:

```bash
python -m scripts.verify_memo docs/from_core/*.md
```

`tests/protocol/test_memo_integrity.py` runs the same check in CI, so a memo cannot
be silently edited or arrive damaged without the suite saying so.

## Why annotations live here and not in the memo files

Response 008 asked delivery to "note the swap in its footnote" — i.e. inside the
memo file. **That is no longer possible, and the reason is 008's own new protocol:**
any byte added to a memo above the footer changes `body` and invalidates the digest;
any byte added below it means the footer is no longer the final line. The integrity
footer makes archived memos immutable. So delivery annotations move here, one entry
per memo. Flagged to core rather than resolved silently in either direction — the
alternative readings are "keep the footnote and break every digest" or "drop the
provenance record", and neither is acceptable.

## Provenance

| Memo | Footer | Archive provenance |
|---|---|---|
| 001–006 | none | Predate the protocol. Archived as received; no mechanical check is possible for these, and none is claimed. |
| 007 | `966b7461…` | **Arrived damaged twice.** The original relay and core's byte-clean re-issue *both* arrived UTF-8-decoded-as-cp1252 with the C1 continuation bytes discarded — lossy, so not mechanically reversible. The archived file is a delivery reconstruction from context, **subsequently proven byte-identical to core's original** by its own integrity footer. It is not "close to" core's bytes; it is core's bytes, and the digest is the proof. The earlier archive copy carried a delivery footnote describing the repair; that footnote is retired to this table because it would break the digest. |
| 008 | `a654483c…` | Arrived damaged in the same way; same reconstruct-then-verify path, digest matches. |
| 009 (delivery) | `850cda60…` | Arrived damaged in the same way. Reconstructed, digest matches. |
| 009 (forensics) | `e2790fdd…` | Forwarded to onedoor under its own §3 cross-session rule; arrived damaged, reconstructed, digest matches. Archived here because its §3 binds delivery. |

## The parsing trap, recorded because delivery walked into it

Response 008 **quotes its own footer format in its prose** (§1, describing the
protocol), so the marker string occurs twice in that file. A parser anchoring on the
first match truncates `body` at the quotation and reports a mismatch that looks
exactly like relay corruption. Anchor on the final line (`\Z`), never the first
match. `scripts/verify_memo.py` does; the docstring says why.

## Why the archive is `-text` in `.gitattributes`

Found by the forensics session and relayed (Core → Forensics 009 §3). `reference/`
and `patches/` were fenced from the start; `docs/from_core/` was still falling under
`* text=auto eol=lf`. Everything here is LF, so nothing was corrupted — but the first
CRLF memo would have failed its own digest and presented as **core sending a bad
digest**, the tampering-shaped diagnosis aimed at the wrong party. The general rule,
now normative for both sessions: *the moment an artifact carries a digest, every layer
between delivery and verification joins its trust path — version control included.*

## A false pass that nearly shipped

The first version of `verify_memo.py` matched the footer with a regex requiring LF.
A CRLF-corrupted memo therefore did not match, fell through to "no footer", and was
reported as **predating the protocol** — a silent pass on exactly the corruption the
footer exists to catch, and it would have masked the `.gitattributes` gap above. Found
by probing the gap rather than by reading the code; the earlier both-directions check
had only tested a content edit, never an encoding one. Absence of a marker and a
marker that does not verify are different facts and never collapse into one now:
`tests/protocol/` holds all three cases, including the FINAL-line rule.
