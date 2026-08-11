"""Global kill switch — a single flag in the ``config`` table.

The executor reads this FIRST, before any policy lookup (invariant: kill switch
check is first). When engaged, every acting tier is clamped to propose-only.
M1 will mirror this flag to a Home Assistant ``input_boolean``; the executor keeps
reading exactly one source of truth here regardless.
"""

from __future__ import annotations

import sqlite3

from niyam.store.clock import now_utc, to_iso

_KEY = "kill_switch_engaged"


def is_engaged(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM config WHERE key=?", (_KEY,)).fetchone()
    return bool(row and row["value"] == "1")


def set_engaged(conn: sqlite3.Connection, engaged: bool, *, origin: str = "ui") -> None:
    """Set the flag. ``origin`` (ui/ha) is recorded for provenance."""
    conn.execute(
        "INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (_KEY, "1" if engaged else "0", to_iso(now_utc())),
    )
    conn.execute(
        "INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        ("kill_switch_origin", origin, to_iso(now_utc())),
    )
