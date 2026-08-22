# The onedoor row preimage — `onedoor/row-preimage/1`

**Normative.** This document defines the exact bytes that `actions_audit.row_hash`
is computed over. It is written so an implementer with no access to the Python source
can reproduce every digest from this text alone (P2-06), and
`tests/guardrail/test_row_preimage.py` holds a second implementation built from this
document rather than from the module.

**Ruled by R031 §1.** Frozen from the first chained row. An append-only table cannot
be re-hashed, so a defect here has no remedy — which is why the encoding is
adversarial rather than convenient: `params_json` is *received* data, and a caller may
be actively trying to make two different rows produce the same digest.

---

## 1. What the vendored artifact ratifies, and what it does not

R031 §1.2 directs delivery to *"follow the vendored artifact's uid-preimage convention
for the length encoding and concatenation discipline"* and, where the row's field set
needs more, to *"extend it explicitly and write the extension down."*

**Stated plainly, because building on a convention that is not there would be the
worst kind of quiet assumption: `reference/rederivable-manifest/` carries no
length-prefix dialect.** Its six frozen rules cover decimals, datetimes, strings, JSON,
digests and the RFC 6962 Merkle construction. There is no `struct`, no `to_bytes`, no
packing of any kind in the artifact — checked, not assumed. The programme's "uid-preimage
convention" is a **methodology** (implement the definition rather than fit the artifact;
drift-guard with a second route) and "Q-11 uids" is cited elsewhere as a past *instance*
of the ambiguous-preimage class, not as a dialect to copy.

So the extension below is the whole encoding, written down as R031 requires, and built
on the one byte-level discipline the artifact *does* ratify — **rule 6's
domain-separation tags** (`0x00`/`0x01` prefixes, RFC 6962 §2.1). The same idea, one
layer down: a tag byte that tells a reader what the following bytes are, so that two
different structures can never present the same octets.

Inherited unchanged from the artifact: **SHA-256, lowercase hex** (rule 5); decimals
(rule 1), datetimes (rule 2), strings-without-normalisation (rule 3) and JSON (rule 4)
wherever a *generated* field is rendered.

## 2. The encoding

The preimage is the concatenation, in the order of §3, of:

```
  MAGIC                                  the ASCII bytes  onedoor/row-preimage/1
  then, for each field in declared order:
      0x00                               ABSENT   — the column is SQL NULL. No payload.
      0x01  LEN(8)  BYTES                PRESENT  — LEN is len(BYTES)
```

- **`LEN` is 8 bytes, unsigned, big-endian.** Fixed width, so there is no varint to
  disagree about and no terminator to escape. Big-endian because it is what a verifier
  in another language reaches for first. Eight bytes exceeds any value SQLite can
  store, so the width never has to change.
- **ABSENT is a tag with no payload; an empty value is `0x01` + eight zero bytes.**
  NULL and `""` therefore differ in their first byte and in their length. This is the
  clause R031 §1.1 pinned, and it is load-bearing: `budget_json` NULL means *no budget
  was owed*, `""` would mean *a budget was produced and it was empty*, and R015 makes
  those different facts. Collapsing them would kill the null-versus-empty distinction
  precisely where an adversary would go looking for it.
- **`MAGIC` is domain separation.** A row preimage can never be mistaken for
  `ND-017`'s `E` preimage, a Merkle leaf, or a future revision of this document —
  which would be `onedoor/row-preimage/2` and would produce different bytes for the
  same row, visibly.
- **No delimiters, no separators, no terminators.** Length prefixes make them
  unnecessary, and anything a field could contain is something an attacker can choose.

## 3. Field order, and how each field's bytes are obtained

Order is fixed. **Reordering is a new preimage version, not a refactor.**

| # | Column | Discipline |
|---|---|---|
| 1 | `seq` | generated — decimal integer, ASCII, no padding, no sign for non-negative |
| 2 | `prev_hash` | generated — 64 lowercase hex ASCII, or the genesis sentinel |
| 3 | `request_id` | generated — the UUID's canonical lowercase hyphenated text |
| 4 | `kind` | generated — UTF-8 |
| 5 | `parent_id` | generated — decimal integer, ASCII |
| 6 | `action_type` | generated — UTF-8 |
| 7 | `source` | generated — UTF-8 |
| 8 | `params_json` | **received — VERBATIM bytes, exactly as frozen at ingress** |
| 9 | `decision` | generated — UTF-8 |
| 10 | `reason_code` | generated — UTF-8 |
| 11 | `nominal_tier` | generated — decimal integer, ASCII |
| 12 | `effective_tier` | generated — decimal integer, ASCII |
| 13 | `detail` | generated — UTF-8 |
| 14 | `connector_ok` | generated — `1` or `0`, ASCII |
| 15 | `error` | generated — UTF-8 |
| 16 | `payload_json` | **received-or-serialized — VERBATIM bytes as stored** |
| 17 | `approval_id` | generated — decimal integer, ASCII |
| 18 | `undo_until` | generated — the stored RFC3339 text |
| 19 | `undo_of` | generated — decimal integer, ASCII |
| 20 | `created_at` | generated — the stored RFC3339 text |
| 21 | `policy_version` | generated — 64 lowercase hex ASCII |
| 22 | `protocol` | generated — UTF-8 |
| 23 | `budget_json` | generated — the stored canonical JSON bytes |
| 24 | `outcome` | generated — UTF-8 |
| 25 | `params_provenance` | generated — UTF-8 |
| 26 | `payload_provenance` | generated — UTF-8 |
| 27 | `malformed_kind` | generated — UTF-8 |
| 28 | `canon_schema` | generated — UTF-8 |
| 29 | `opaque_class` | generated — UTF-8 |

**E10 at the boundary (R031 §1.4): the preimage performs no normalisation of its own.**
It seals what the row holds, exactly. A "generated" field was already canonicalised
when it was written — `budget_json` through the canonical renderer, decimals through
`canon_decimal`, datetimes through `canon_datetime` — and the preimage does not
re-render it. A "received" field enters as the bytes E10 froze at ingress and is never
touched. The discipline column above says *where the bytes came from*, not what the
preimage does to them, because the preimage does nothing to them.

`TEXT` values are encoded UTF-8; `INTEGER` values are their ASCII decimal spelling;
`BLOB` values enter as their bytes. A verifier reading the same SQLite row obtains the
same octets.

## 4. What is excluded, and why exclusion is a decision rather than an omission

| Column | Why it cannot be in the preimage |
|---|---|
| `id` | Assigned by the `INSERT`. The append-only triggers forbid `UPDATE`, so `row_hash` must exist *before* the row does. `seq` is the chain's ordinal for exactly this reason. |
| `row_hash` | It is the output. |
| `sig`, `key_id`, `alg` | `ND-015` signs the row hash. A signature inside its own preimage is circular. |
| `e_digest`, `i_digest`, `t_digest`, `v_digest` | `ND-017` computes these *from* the row. |
| `anchor_ref` | Assigned after anchoring, which under **X-8** happens only after verification — so it is later than the hash by construction. |

`tests/guardrail/test_row_preimage.py` asserts that **every column of `actions_audit`
is either in §3 or in this table**. A future migration that adds a column fails that
test until someone classifies it deliberately. A column that silently fell outside the
hash would be a field an attacker could edit without breaking the chain, and it would
be invisible in review — the schema would look complete and the hash would not cover
it.

## 5. Golden vectors (R031 §1.3)

Held in `tests/guardrail/test_row_preimage.py`, each named for the attack it refuses.

1. **Shift collision.** Fields `("a", "bc")` and `("ab", "c")` must not produce the
   same preimage. This is the classic failure of naive concatenation, and it is why
   the length prefix exists at all.
2. **Absent versus empty.** A row with `detail` NULL and the same row with `detail =
   ""` must differ. R031 §1.1's clause, as a vector.
3. **Header bytes inside a value.** A field whose *content* is the byte sequence
   `0x01` followed by eight bytes must not be confusable with a tag-plus-length
   header. Fixed-width prefixes make this structurally impossible; the vector proves
   it rather than asserting it.
4. **One-byte perturbation.** Changing a single byte of any field changes the digest.

## 6. Verifying a chain

`row_hash = sha256(preimage)`, lowercase hex. Row *n*'s `prev_hash` is row *n−1*'s
`row_hash`; the first chained row (**genesis**) carries `prev_hash` = 64 ASCII zeros
(R016 — an affirmative in-band statement that no predecessor exists, leaving NULL
exactly one meaning).

A walker reports **four** outcomes and never collapses them (R031 §2):

| Outcome | When |
|---|---|
| `verified` | every chained row's digest matches, and each links to its predecessor |
| `absent` | the row precedes genesis: never chained, because `ND-001` had not run |
| `unverifiable` | the chain fields are partly written — it ran and did not finish |
| `failed` | a digest does not match, or a link points at the wrong predecessor |

A log with an unchained prefix and an intact chain after genesis is **not** "verified"
and **not** "failed". It is both, stated per region.
