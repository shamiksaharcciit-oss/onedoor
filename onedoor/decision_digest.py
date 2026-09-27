"""The canonical form of one `actions_audit` row, and its digest.

One function, imported by both the decide path (`onedoor.guardrail.decision`,
to compute a `decision_ref` at the moment a row is written) and the export
(`onedoor.export`, to compute the same digest later from the same row read
back) -- so the two can never quietly diverge into two different renderings
of "the same" row. Neither module re-derives this logic; both call it.

Stdlib-only on purpose: `onedoor.decision_ref`'s checker imports this module
too, and it must stay vendorable by a consumer (a onetrace console, say)
without pulling in onedoor's own dependency tree.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping


def canonical_row_record(row: sqlite3.Row | Mapping[str, object]) -> dict[str, object]:
    """Every column of an `actions_audit` row, exactly as stored -- no float ever
    allowed (E10: every numeric column on this table is an integer or an
    already-canonical decimal string inside a JSON-text column, so a float here
    is a bug in the row, not a formatting choice).
    """
    keys = row.keys()
    record: dict[str, object] = {}
    for key in keys:
        value = row[key]
        if isinstance(value, float):
            row_id = row["id"] if "id" in keys else "?"
            raise TypeError(
                f"actions_audit.{key} carries a float ({value!r}) on row id={row_id!r}; "
                "onedoor forbids floats on the evaluation path (E10) and this digest "
                "refuses to hash one into a decision record"
            )
        record[key] = value
    return record


def canonical_row_json(record: Mapping[str, object]) -> bytes:
    """RFC-8785-adjacent, but only as far as this table's own values need:
    sorted keys, no floats (checked by `canonical_row_record` before this ever
    runs), tight separators -- exactly what `python -m onedoor.export` writes
    for one line.
    """
    return json.dumps(dict(record), sort_keys=True, separators=(",", ":")).encode("utf-8")


def decision_digest(row: sqlite3.Row | Mapping[str, object]) -> str:
    """`sha256:<hex>` of the canonical JSON of one `actions_audit` row.

    Works whether chaining is on or off: chaining's own columns
    (`prev_hash`/`seq`/`row_hash`/`sig`/`key_id`/`alg`) are ordinary columns
    on this table like any other, NULL when chaining is not enabled -- this
    function renders whatever the row actually holds, never branching on
    whether chaining happens to be configured.
    """
    record = canonical_row_record(row)
    digest = hashlib.sha256(canonical_row_json(record)).hexdigest()
    return f"sha256:{digest}"
