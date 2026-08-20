"""ND-024: the vestigial Sutradhar tables are retired, push_subscriptions is not.

Two things are asserted, and the second matters more than the first: a fresh
database must not carry the dead tables, AND an existing 0.3.5 database must
migrate forward without losing the append-only guarantees. A migration that
quietly dropped a trigger would be far worse than the dead schema it removes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from onedoor.store.db import Database

RETIRED = ("intake_policy", "preferences", "sessions")
KEPT = "push_subscriptions"


def _names(conn: sqlite3.Connection, kind: str) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type=?", (kind,))}


def test_fresh_database_has_no_vestigial_tables(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "fresh.db"))
    db.init()
    conn = db.connect()
    try:
        tables = _names(conn, "table")
        assert not (tables & set(RETIRED)), f"vestigial tables survived: {tables & set(RETIRED)}"
        assert KEPT in tables, "push_subscriptions is reserved for ND-026, not vestigial"
    finally:
        conn.close()


def test_existing_database_migrates_forward(tmp_path: Path) -> None:
    """A pre-0006 database upgrades cleanly and loses the dead table."""
    path = str(tmp_path / "upgrade.db")
    Database(path).init()

    conn = Database(path).connect()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO preferences (key) VALUES ('stale')")
        conn.execute("DELETE FROM schema_migrations WHERE version LIKE '0006%'")
        conn.commit()
        assert "preferences" in _names(conn, "table")
    finally:
        conn.close()

    applied = Database(path).init()
    assert any("0006" in name for name in applied), f"0006 did not re-apply: {applied}"

    conn = Database(path).connect()
    try:
        assert "preferences" not in _names(conn, "table")
    finally:
        conn.close()


def test_append_only_triggers_survive_the_migration(tmp_path: Path) -> None:
    """The migration must not disturb the structural append-only enforcement."""
    db = Database(str(tmp_path / "triggers.db"))
    db.init()
    conn = db.connect()
    try:
        triggers = _names(conn, "trigger")
        for required in (
            "actions_audit_no_update",
            "actions_audit_no_delete",
            "policy_versions_no_update",
            "policy_versions_no_delete",
        ):
            assert required in triggers, f"missing trigger after 0006: {required}"

        conn.execute(
            "INSERT INTO actions_audit (request_id, kind, action_type, source,"
            " params_json, decision, reason_code, nominal_tier, effective_tier,"
            " created_at) VALUES ('r','decision','a','llm','{}','denied','x',1,1,'t')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE actions_audit SET reason_code='y'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM actions_audit")
    finally:
        conn.close()
