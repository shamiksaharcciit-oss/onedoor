"""0049 (shadow_decisions) was amended twice in place before this test
existed, each time argued safe because the table had never shipped. That
argument never addressed what matters here: `schema_migrations` tracks a
migration by filename only, never by content (see `onedoor/store/db.py`'s
`run_migrations`), so a store that had already applied the ORIGINAL 0049
would see its filename already recorded and silently skip the amended
version forever -- confirmed directly, not assumed, before this fix. 0049
is reverted to its original shape; `0050_shadow_decisions_coverage.sql`
adds the three columns forward-only instead, so it runs against any store
regardless of which shape of 0049 it already carries -- except the two
shapes 0049 itself briefly carried on this branch (see
`onedoor/store/migrations/UPGRADE_NOTES.md`), which these tests do not
cover since no supported upgrade path exists for them.

The three cases below are the ones a real store can actually be in: never
migrated past what any release ever shipped (`0.10.2`), migrated through
an earlier shape of 0049 (one that was identical in SQL to today's 0049 --
only its comment changed), or never migrated at all.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from onedoor.store.db import _MIGRATIONS_DIR, Database

_ORIGINAL_0049 = """
CREATE TABLE shadow_decisions (
    id              INTEGER PRIMARY KEY,
    request_id      TEXT NOT NULL,
    live_audit_id   INTEGER,
    action_type     TEXT NOT NULL,
    policy_label    TEXT NOT NULL,
    decision        TEXT NOT NULL,
    effective_tier  INTEGER NOT NULL,
    reason_code     TEXT,
    detail          TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (live_audit_id) REFERENCES actions_audit(id)
);
CREATE INDEX idx_shadow_decisions_request_id ON shadow_decisions(request_id);
CREATE INDEX idx_shadow_decisions_policy_label ON shadow_decisions(policy_label);
"""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_a_store_on_the_original_0049_shape_gains_the_new_columns_via_0050(
    tmp_path: Path,
) -> None:
    """Simulates a store that applied 0049 back when it still had its
    original shape -- the exact scenario the in-place amendments never
    proved safe for. A row written under that shape must survive, and the
    new columns must arrive with sane values, not an error and not silent
    absence."""
    path = str(tmp_path / "pre_0050.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for migration_path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            if migration_path.name >= "0050":
                continue
            if migration_path.name == "0049_shadow_decisions.sql":
                conn.executescript(_ORIGINAL_0049)
            else:
                conn.executescript(migration_path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (migration_path.name,),
            )
        conn.execute(
            "INSERT INTO shadow_decisions (request_id, action_type, policy_label, decision,"
            " effective_tier, reason_code, detail, created_at) VALUES"
            " ('r1', 'demo.toggle', 'old-policy', 'denied', 1, 'default_deny', '', 't0')"
        )
        conn.commit()
        assert "coverage" not in _columns(conn, "shadow_decisions")
    finally:
        conn.close()

    applied = Database(path).init()
    assert "0050_shadow_decisions_coverage.sql" in applied
    assert "0049_shadow_decisions.sql" not in applied  # already recorded, correctly skipped

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        columns = _columns(conn, "shadow_decisions")
        assert {"coverage", "live_reason_code", "comparison"} <= columns

        row = conn.execute(
            "SELECT coverage, live_reason_code, comparison FROM shadow_decisions WHERE request_id='r1'"
        ).fetchone()
        assert row["coverage"] == "limits-v1"  # backfilled by the column's own default
        assert row["live_reason_code"] is None
        assert row["comparison"] is None

        # A fresh row written after the upgrade states its own coverage explicitly,
        # the same as the backfilled default -- not a coincidence to rely on, just
        # the current value of `shadow.COVERAGE_ID` at the time either was written.
        conn.execute(
            "INSERT INTO shadow_decisions (request_id, action_type, policy_label, coverage,"
            " decision, effective_tier, reason_code, detail, live_reason_code, comparison,"
            " created_at) VALUES ('r2', 'demo.toggle', 'new-policy', 'limits-v1', 'denied', 1,"
            " 'default_deny', '', 'default_deny', 'agree', 't1')"
        )
        conn.commit()
    finally:
        conn.close()


def test_a_fresh_database_already_carries_both_migrations(tmp_path: Path) -> None:
    db = Database(str(tmp_path / "fresh.db"))
    applied = db.init()
    assert "0049_shadow_decisions.sql" in applied
    assert "0050_shadow_decisions_coverage.sql" in applied

    conn = db.connect()
    try:
        columns = _columns(conn, "shadow_decisions")
        assert {"coverage", "live_reason_code", "comparison"} <= columns
    finally:
        conn.close()


def test_a_0_10_2_shaped_store_upgrades_cleanly(tmp_path: Path) -> None:
    """A store that predates this feature entirely -- the last migration any
    released version ever shipped is `0032` -- gains every later migration
    including 0049 and 0050 on its first open against this code, the same
    as a real 0.10.2 database from PyPI would."""
    path = str(tmp_path / "0_10_2_shaped.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for migration_path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            if migration_path.name[:4] > "0032":
                continue
            conn.executescript(migration_path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (migration_path.name,),
            )
        conn.commit()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "shadow_decisions" not in tables  # 0.10.2 predates this feature entirely
    finally:
        conn.close()

    applied = Database(path).init()
    assert "0049_shadow_decisions.sql" in applied
    assert "0050_shadow_decisions_coverage.sql" in applied
    assert len(applied) == 18  # 0033 through 0050

    conn = sqlite3.connect(path)
    try:
        columns = _columns(conn, "shadow_decisions")
        assert {"coverage", "live_reason_code", "comparison"} <= columns
    finally:
        conn.close()
