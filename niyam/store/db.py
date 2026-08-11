"""SQLite connection management (WAL) and explicit transaction control.

Connections run in autocommit mode (``isolation_level=None``) so the guardrail
executor can issue precise ``BEGIN IMMEDIATE`` transactions — it must take the
write lock up front to serialize cap accounting without deadlocking at commit.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(db_path: str) -> sqlite3.Connection:
    """Open a configured connection. Caller owns its lifecycle."""
    conn = sqlite3.connect(db_path, isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit IMMEDIATE transaction: BEGIN up front, COMMIT/ROLLBACK on exit.

    Taking the write lock immediately (rather than deferring to first write)
    serializes concurrent writers at entry, which is what makes cap
    check-and-reserve free of double-spend.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply any un-applied forward-only migrations. Returns applied filenames."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied: set[str] = {
        row["version"] for row in conn.execute("SELECT version FROM schema_migrations")
    }
    newly: list[str] = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        # DDL (triggers, tables) must run outside an explicit transaction block here;
        # executescript commits any pending transaction, so run each migration cleanly.
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
            (path.name,),
        )
        newly.append(path.name)
    return newly


class Database:
    """Thin handle bound to a db path. Hands out short-lived connections."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def init(self) -> list[str]:
        """Open a connection, run migrations, close. Returns applied migrations."""
        conn = self.connect()
        try:
            return run_migrations(conn)
        finally:
            conn.close()
