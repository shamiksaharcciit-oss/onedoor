# Memo archive — provenance and integrity

Core memos carry `Integrity: sha256(body) = <hex>` as their final line from Response
008 onward (`body` = every byte above that line). Check the archive with:

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

## The parsing trap, recorded because delivery walked into it

Response 008 **quotes its own footer format in its prose** (§1, describing the
protocol), so the marker string occurs twice in that file. A parser anchoring on the
first match truncates `body` at the quotation and reports a mismatch that looks
exactly like relay corruption. Anchor on the final line (`\Z`), never the first
match. `scripts/verify_memo.py` does; the docstring says why.
