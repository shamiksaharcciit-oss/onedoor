"""The bytes `actions_audit.row_hash` is computed over (ND-001 / C1).

**The normative definition is `docs/row-preimage.md`.** This module implements it;
that document defines it, in words an implementer with no access to this file can
build from (P2-06). `tests/guardrail/test_row_preimage.py` holds a second
implementation written from the document rather than from this code — because an
implementation that agrees with itself has proved nothing, and the only way to find
out whether a definition is a definition is to have someone else build from it.

Ruled by R031 §1, and **frozen from the first chained row**. An append-only table
cannot be re-hashed: the triggers forbid `UPDATE`, so there is no migration that fixes
a defect here. That is why the encoding is adversarial rather than convenient —
`params_json` is *received* data, and a caller may be actively trying to make two
different rows produce one digest.

The shape, in one paragraph
---------------------------
A magic string for domain separation, then every field in a fixed order, each written
as either a single ABSENT tag (SQL NULL — no statement was made) or a PRESENT tag
followed by an 8-byte big-endian length and the bytes themselves. **NULL and the empty
string differ in their first byte**, which is the clause R031 §1.1 pinned and the one
this whole file exists to protect: `budget_json` NULL means *no budget was owed* and
`""` would mean *a budget was produced and it was empty*, and R015 makes those
different facts.

On "follow the vendored artifact's convention"
----------------------------------------------
R031 §1.2 says to follow the vendored `rederivable-manifest`'s uid-preimage convention
and to extend it explicitly where the row's field set needs more. **The artifact
carries no length-prefix dialect at all** — checked, not assumed: no `struct`, no
`to_bytes`, no packing anywhere in it. Its six frozen rules cover decimals, datetimes,
strings, JSON, digests and the RFC 6962 Merkle construction. So the extension here is
the entire encoding, written down in `docs/row-preimage.md` §1 as R031 requires, and
built on the one byte-level discipline the artifact *does* ratify: rule 6's
domain-separation tag bytes. Saying so beats quietly implying a dialect was followed.
"""

from __future__ import annotations

import hashlib
import sqlite3

MAGIC = b"onedoor/row-preimage/1"
"""Domain separation. A row preimage can never be read as `ND-017`'s `E` preimage, a
Merkle leaf, or a future revision -- which would be `/2` and would visibly produce
different bytes for the same row."""

ABSENT = b"\x00"
"""SQL NULL: no statement was made. A tag with no payload, never a zero-length value."""

PRESENT = b"\x01"
"""A value follows, as an 8-byte big-endian length and then that many bytes."""

LENGTH_BYTES = 8
"""Fixed width, so there is no varint to disagree about and no terminator to escape.
Eight bytes exceeds anything SQLite can store, so this never has to change."""

GENESIS_PREV_HASH = "0" * 64
"""R016's ruled sentinel: an affirmative in-band statement that no predecessor exists,
which leaves NULL exactly one meaning."""

FIELD_ORDER: tuple[str, ...] = (
    "seq",
    "prev_hash",
    "request_id",
    "kind",
    "parent_id",
    "action_type",
    "source",
    "params_json",
    "decision",
    "reason_code",
    "nominal_tier",
    "effective_tier",
    "detail",
    "connector_ok",
    "error",
    "payload_json",
    "approval_id",
    "undo_until",
    "undo_of",
    "created_at",
    "policy_version",
    "protocol",
    "budget_json",
    "outcome",
    "params_provenance",
    "payload_provenance",
    "malformed_kind",
    "canon_schema",
    "opaque_class",
)
"""Fixed. **Reordering is a new preimage version, not a refactor** -- every digest
already written was computed over this order, and the table forbids UPDATE."""

EXCLUDED: dict[str, str] = {
    "id": (
        "assigned by the INSERT, and the triggers forbid UPDATE, so row_hash must "
        "exist before the row does -- which is why `seq` is the chain's ordinal"
    ),
    "row_hash": "it is the output",
    "sig": "ND-015 signs the row hash; a signature inside its own preimage is circular",
    "key_id": "ND-015, with `sig`",
    "alg": "ND-015, with `sig`",
    "e_digest": "ND-017 computes it FROM the row",
    "i_digest": "ND-017 computes it FROM the row",
    "t_digest": "ND-017 computes it FROM the row",
    "v_digest": "ND-017 computes it FROM the row",
    "anchor_ref": (
        "assigned after anchoring, which under X-8 happens only after verification, "
        "so it is later than the hash by construction"
    ),
}
"""Every column NOT in the preimage, each with the reason.

`tests/guardrail/test_row_preimage.py` asserts every column of `actions_audit` is in
`FIELD_ORDER` or here, so a migration that adds a column fails until someone classifies
it deliberately. A column that silently fell outside the hash would be a field an
attacker could edit without breaking the chain, and it would look complete in review.
"""


def _field_bytes(value: object) -> bytes | None:
    """The octets a column contributes, or None for SQL NULL.

    No normalisation happens here, and that is R031 §1.4 rather than laziness: a
    generated column was canonicalised when it was WRITTEN -- `budget_json` through
    the canonical renderer, decimals through `canon_decimal` -- and a received column
    was frozen verbatim at ingress under E10. The preimage seals what the row holds,
    exactly. Re-rendering anything here would mean the sealed bytes and the stored
    bytes could differ, which is the one thing a receipt may never allow.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, bool):
        # Before the int branch: bool is a subclass of int, and `True` must render as
        # `1` rather than as `True`.
        return b"1" if value else b"0"
    if isinstance(value, int):
        return str(value).encode("ascii")
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError(
        f"a column of type {type(value).__name__} reached the preimage; every column "
        f"must have a declared byte form (docs/row-preimage.md §3)"
    )


def encode_field(value: object) -> bytes:
    """One field: an ABSENT tag, or PRESENT + 8-byte big-endian length + bytes."""
    raw = _field_bytes(value)
    if raw is None:
        return ABSENT
    return PRESENT + len(raw).to_bytes(LENGTH_BYTES, "big") + raw


def preimage(values: dict[str, object]) -> bytes:
    """The full preimage for a row, given its column values.

    Takes a mapping rather than a `sqlite3.Row` so the writer can compute a hash for a
    row that does not exist yet -- which it must, because the row cannot be updated
    after insertion.
    """
    missing = [name for name in FIELD_ORDER if name not in values]
    if missing:
        raise KeyError(f"preimage is missing declared fields: {missing}")
    return MAGIC + b"".join(encode_field(values[name]) for name in FIELD_ORDER)


def row_hash(values: dict[str, object]) -> str:
    """SHA-256 of the preimage, lowercase hex (artifact rule 5)."""
    return hashlib.sha256(preimage(values)).hexdigest()


def values_from_row(row: sqlite3.Row) -> dict[str, object]:
    """The preimage inputs read back off a stored row, for verification."""
    return {name: row[name] for name in FIELD_ORDER}


def row_hash_of(row: sqlite3.Row) -> str:
    """Recompute a stored row's hash from what the store actually holds."""
    return row_hash(values_from_row(row))
