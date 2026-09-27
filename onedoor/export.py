"""`python -m onedoor.export` — decision records, one JSON object per line (WO-D1 step 3).

    python -m onedoor.export --store <db> --out <file> [--since <utc>]

Writes every row of ``actions_audit``, in ``id`` order (the table's own append
order — the order rows were written in), as one JSON object per line: the row's
own columns, with no reinterpretation of any column's stored value. A column
already holding serialized JSON (``params_json``, ``payload_json``,
``budget_json``) is written out as the *string* onedoor stored, never re-parsed
into a nested object — the export shows what is in the row, not a redigested
view of it. No field is invented that the row does not already carry.

Keys are sorted within each line and no float ever appears: every numeric
column on this table is an integer (tier, ids, counts) or already a canonical
decimal string inside a JSON-text column, so a float surfacing here would be a
bug in the row, not a formatting choice, and this module refuses to paper over
one.

A ``<file>.sha256`` is written beside the export, one line, in the form
``sha256sum`` reads: ``<hex>  <basename>``.

Read-only against the store. See ``docs/EXPORT.md`` for the field list, their
meanings, and the ordering guarantee.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from onedoor.decision_digest import canonical_row_json, canonical_row_record
from onedoor.store.clock import from_iso
from onedoor.store.db import Database


def export_rows(
    conn: sqlite3.Connection, *, since: datetime | None = None
) -> list[dict[str, object]]:
    """Every ``actions_audit`` row, in ``id`` order, as stored.

    Filtering by ``since`` parses ``created_at`` back to a ``datetime`` and
    compares that, rather than filtering in SQL against the stored string.
    Lexicographic comparison of ``to_iso``'s output happens to order correctly
    here (a fractional second always sorts after the same whole second, since
    ``.`` > ``+`` in ASCII) — but the export's correctness should not depend on
    a reader re-deriving that from the storage format, so it compares the
    values a `datetime` actually means.
    """
    cursor = conn.execute("SELECT * FROM actions_audit ORDER BY id ASC")
    rows = [canonical_row_record(row) for row in cursor.fetchall()]
    if since is None:
        return rows
    return [row for row in rows if from_iso(str(row["created_at"])) >= since]


def write_export(conn: sqlite3.Connection, out: Path, *, since: datetime | None = None) -> int:
    """Write the export and its ``.sha256`` sidecar. Returns the row count.

    Each line is exactly `canonical_row_json` of that row -- the same
    rendering `onedoor.decision_digest.decision_digest` hashes, so a
    `decision_ref` computed at decide time and a digest recomputed later from
    this file can never disagree about what "the row" was.
    """
    rows = export_rows(conn, since=since)
    lines = [canonical_row_json(row).decode("utf-8") for row in rows]
    text = "".join(line + "\n" for line in lines)
    out.write_bytes(text.encode("utf-8"))
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    sidecar = out.with_name(out.name + ".sha256")
    sidecar.write_bytes(f"{digest}  {out.name}\n".encode())
    return len(rows)


def _parse_since(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m onedoor.export",
        description="Export actions_audit as one JSON object per line. Read-only.",
    )
    parser.add_argument(
        "--store", required=True, type=Path, help="path to the onedoor SQLite store"
    )
    parser.add_argument("--out", required=True, type=Path, help="file to write the export to")
    parser.add_argument(
        "--since",
        default=None,
        type=_parse_since,
        help="only rows with created_at >= this UTC instant (ISO-8601, inclusive)",
    )
    args = parser.parse_args(argv)

    if not args.store.is_file():
        parser.error(f"no store at {args.store}")

    database = Database(str(args.store))
    conn = database.connect()
    try:
        count = write_export(conn, args.out, since=args.since)
    finally:
        conn.close()
    print(f"wrote {count} row(s) to {args.out} ({args.out.name}.sha256 alongside)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
