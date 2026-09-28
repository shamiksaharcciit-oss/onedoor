"""Approver values stored as `key:` plus the first characters of an admin key are erased
from existing stores. Nothing else in `approvals` changes, and nothing in `actions_audit`
is touched: its rows are append-only and sealed, so a key prefix already written into a
sealed row's detail cannot be removed by any migration.
"""

from __future__ import annotations

from pathlib import Path

from onedoor.store.db import Database, run_migrations

KEPT = ["mcp-proxy-demo", "langchain-human", "mandate-authority", "sess-1", None]
LEAKED = ["key:akey", "key:admin-", "key:root"]


def _approval(conn, decided_by):  # type: ignore[no-untyped-def]
    conn.execute(
        "INSERT INTO approvals (request_json, action_type, state, created_at, expires_at, "
        "decided_by_session) VALUES ('{}', 'x.y', 'denied', 'a', 'b', ?)",
        (decided_by,),
    )


def test_stored_key_prefixes_are_erased_and_nothing_else_changes(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "old.db"))
    db.init()
    conn = db.connect()
    migration = conn.execute(
        "SELECT version FROM schema_migrations WHERE version LIKE '%approver_key_prefixes%'"
    ).fetchone()
    assert migration is not None, "the erasing migration exists and ran on a fresh store"

    # A store as it stood before the migration: rows already written, migration unapplied.
    conn.execute("DELETE FROM schema_migrations WHERE version = ?", (migration["version"],))
    for value in LEAKED + KEPT:
        _approval(conn, value)
    audit_before = conn.execute("SELECT COUNT(*) FROM actions_audit").fetchone()[0]

    assert run_migrations(conn) == [migration["version"]]

    values = [r[0] for r in conn.execute("SELECT decided_by_session FROM approvals ORDER BY id")]
    erased, kept = values[: len(LEAKED)], values[len(LEAKED) :]
    assert kept == KEPT
    for value in erased:
        assert value is not None and not value.startswith("key:"), value
    assert conn.execute("SELECT COUNT(*) FROM actions_audit").fetchone()[0] == audit_before


def test_the_erasing_migration_is_harmless_on_a_store_with_no_approvals(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "empty.db"))
    db.init()
    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
