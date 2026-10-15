"""`ND-056` / T2 — studio schema 3: the `state` column, and the upgrade that adds it.

The Studio store carries its OWN version. No enforcer migration number is claimed
here and none should be: a table in `studio.db` that a different process owns does
not belong in the enforcer's numbered migration sequence. `test_no_numbered_
migration_touches_a_studio_table` below holds that boundary against its real
invariant, not a frozen next-free-number snapshot.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from onedoor.guardrail.models import Policy, Tier
from onedoor.store.clock import now_utc
from onedoor.studio import store


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {str(r["name"]) for r in conn.execute("PRAGMA table_info(policy_candidates)")}


def test_a_fresh_store_is_version_three_with_the_state_column(tmp_path) -> None:
    conn = store.open_store(tmp_path / "studio.db")
    assert conn.execute("SELECT version FROM studio_schema").fetchone()["version"] == 3
    assert "state" in _columns(conn)


def test_a_version_two_store_gains_the_column_on_open(tmp_path) -> None:
    """The upgrade that `CREATE TABLE IF NOT EXISTS` cannot perform.

    This is the defect the explicit ALTER exists to prevent: applying the current schema
    to an existing table is a NO-OP, so a v2 store would have kept its old shape while
    the version stamp claimed v3 — a store that says it has a column it does not have,
    which is the failure direction that hurts.
    """
    path = tmp_path / "studio.db"
    # A genuine v2 store, built with the v2 DDL, rather than a v3 store with a column
    # dropped. Faithful to what an operator upgrading actually has on disk — and SQLite
    # refuses `DROP COLUMN` on this table anyway, so the mangled-v3 route was never the
    # same thing as the case being tested.
    seed = sqlite3.connect(path)
    seed.executescript(
        """
        CREATE TABLE studio_schema (version INTEGER NOT NULL);
        INSERT INTO studio_schema (version) VALUES (2);
        CREATE TABLE policy_candidates (
            draft_id     TEXT PRIMARY KEY,
            title        TEXT NOT NULL,
            body_json    TEXT NOT NULL,
            base_version TEXT,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );
        INSERT INTO policy_candidates VALUES
            ('old-1', 'written under v2', '{"policies":[],"effects":[]}', NULL, 'then', 'then');
        """
    )
    seed.commit()
    seed.close()

    reopened = store.open_store(path)
    assert "state" in _columns(reopened), "the upgrade did not add the column"
    assert reopened.execute("SELECT version FROM studio_schema").fetchone()["version"] == 3
    # And the row written under v2 survives, reading as the earliest state.
    survivor = store.load(reopened, "old-1")
    assert survivor is not None
    assert survivor.title == "written under v2"
    assert survivor.state == store.DRAFT


def test_a_row_written_before_the_column_reads_as_draft(tmp_path) -> None:
    """NULL predates the column, and the earliest state is `draft`.

    The same absent-value rule the enforcer uses for an unstamped `protocol`. Reading it
    as anything else would invent a history the row does not have — and reading it as
    `submitted` would claim a human had been asked when nobody was.
    """
    conn = store.open_store(tmp_path / "studio.db")
    draft = store.create(conn, title="old", policies=[], base_version=None, now=now_utc())
    conn.execute("UPDATE policy_candidates SET state=NULL WHERE draft_id=?", (draft.draft_id,))
    assert store.load(conn, draft.draft_id).state == store.DRAFT


def test_a_store_from_the_future_is_still_refused(tmp_path) -> None:
    path = tmp_path / "studio.db"
    conn = store.open_store(path)
    conn.execute("UPDATE studio_schema SET version=99")
    conn.commit()
    conn.close()
    with pytest.raises(store.StudioStoreError, match="schema version 99"):
        store.open_store(path)


def test_the_upgrade_is_idempotent(tmp_path) -> None:
    path = tmp_path / "studio.db"
    for _ in range(3):
        conn = store.open_store(path)
        conn.execute("UPDATE studio_schema SET version=2")
        conn.commit()
        conn.close()
    assert "state" in _columns(store.open_store(path))


# --- the state machine, and where it stops ---------------------------------------------


def test_submitted_is_the_furthest_a_draft_can_go(tmp_path) -> None:
    """There is deliberately no `ratified` state.

    Ratification is an event in the enforcer's store with a receipt. A flag here claiming
    it would be a second, unreceipted record of the one thing this product exists to
    receipt — and the two would disagree the first time anything went wrong.
    """
    conn = store.open_store(tmp_path / "studio.db")
    draft = store.create(conn, title="t", policies=[], base_version=None, now=now_utc())

    assert store.DRAFT_STATES == ("draft", "submitted")
    assert store.set_state(conn, draft.draft_id, state=store.SUBMITTED).submitted is True

    with pytest.raises(store.StudioStoreError, match="no ratified state"):
        store.set_state(conn, draft.draft_id, state="ratified")


def test_editing_a_submitted_draft_returns_it_to_draft(tmp_path) -> None:
    """A submission is about a SPECIFIC candidate; changing it un-asks the question.

    Leaving the flag up would let an edit ride into a ceremony under a submission that
    was made about different rules.
    """
    conn = store.open_store(tmp_path / "studio.db")
    draft = store.create(conn, title="t", policies=[], base_version=None, now=now_utc())
    store.set_state(conn, draft.draft_id, state=store.SUBMITTED)
    assert store.load(conn, draft.draft_id).submitted is True

    store.save(
        conn,
        draft.draft_id,
        policies=[Policy(action_type="a.b", tier=Tier.CONFIRM)],
        now=now_utc(),
    )
    assert store.load(conn, draft.draft_id).state == store.DRAFT


def test_setting_the_state_of_a_draft_that_is_not_there_is_refused(tmp_path) -> None:
    conn = store.open_store(tmp_path / "studio.db")
    with pytest.raises(store.StudioStoreError, match="no draft"):
        store.set_state(conn, "nope", state=store.SUBMITTED)


def _studio_table_names() -> frozenset[str]:
    """Every table the Studio's own schema module declares -- read from the schema
    string `open_store` actually applies to `studio.db`, not a hand-maintained list
    that could drift from it. Several (`policy_candidates`, `descriptions`,
    `derivation_records`) do not carry a `studio_` prefix, so a naming convention
    cannot stand in for this."""
    return frozenset(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", store._SCHEMA))


def _migrations_dir() -> Path:
    from onedoor.store import db as db_module

    return Path(db_module.__file__).parent / "migrations"


def claimed_studio_tables(migrations_dir: Path, studio_tables: frozenset[str]) -> list[str]:
    """Every `<migration file>: <table>` pair where a numbered migration's SQL
    creates, alters or drops a table that belongs to the Studio, not the enforcer.
    Reads each migration's actual text -- a migration touching a Studio table by
    name is the real boundary violation, regardless of which number it claims."""
    pattern = re.compile(
        r"\b(?:CREATE TABLE(?:\s+IF NOT EXISTS)?|ALTER TABLE|DROP TABLE(?:\s+IF EXISTS)?)"
        r"\s+(\w+)",
        re.IGNORECASE,
    )
    hits = []
    for path in sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        text = path.read_text(encoding="utf-8")
        for table in pattern.findall(text):
            if table in studio_tables:
                hits.append(f"{path.name}: {table}")
    return hits


def migration_number_gaps(migrations_dir: Path) -> list[str]:
    """Problems with the numbered sequence itself: a gap, or two files claiming the
    same number. Checked separately from which TABLE a migration touches -- a
    contiguous, duplicate-free sequence is its own property, unrelated to whether
    any one file is well-formed."""
    numbers = [int(p.name[:4]) for p in migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")]
    problems = []
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        problems.append(f"duplicate migration number(s): {duplicates}")
    expected = set(range(1, max(numbers) + 1)) if numbers else set()
    missing = sorted(expected - set(numbers))
    if missing:
        problems.append(f"missing migration number(s): {missing}")
    return problems


def test_no_numbered_migration_touches_a_studio_table() -> None:
    """The boundary's real invariant: a table in `studio.db`
    that a different process owns must never be created, altered or dropped by a
    numbered enforcer migration, whatever number it claims. The earlier version of
    this test asserted "no file numbered 0029 or above exists" -- a frozen snapshot
    of the next free number, not an assertion about Studio tables at all, which
    would have refused a legitimate new enforcer migration just as readily as a
    real violation. This checks the thing the boundary is actually about.
    """
    hits = claimed_studio_tables(_migrations_dir(), _studio_table_names())
    assert not hits, (
        f"a numbered enforcer migration touches a Studio table: {hits}; a table in "
        f"the Studio's own file (versioned separately, in studio_schema.version) "
        f"must not be written into the enforcer's numbered history"
    )


def test_the_numbered_migrations_have_no_gap_and_no_duplicate() -> None:
    """Contiguous from 0001, with nothing skipped and nothing claimed twice --
    independent of which table any one of them touches."""
    problems = migration_number_gaps(_migrations_dir())
    assert not problems, problems


def test_sabotage_a_migration_touching_a_studio_table_is_caught(tmp_path: Path) -> None:
    (tmp_path / "0001_init.sql").write_text(
        "CREATE TABLE actions_audit (id INTEGER);\n", encoding="utf-8"
    )
    (tmp_path / "0002_studio_leak.sql").write_text(
        "ALTER TABLE policy_candidates ADD COLUMN sabotage TEXT;\n", encoding="utf-8"
    )
    hits = claimed_studio_tables(tmp_path, _studio_table_names())
    assert hits == ["0002_studio_leak.sql: policy_candidates"]


def test_sabotage_a_gap_in_the_migration_numbers_is_caught(tmp_path: Path) -> None:
    (tmp_path / "0001_init.sql").write_text("CREATE TABLE a (id INTEGER);\n", encoding="utf-8")
    (tmp_path / "0003_skips_two.sql").write_text("CREATE TABLE b (id INTEGER);\n", encoding="utf-8")
    problems = migration_number_gaps(tmp_path)
    assert problems == ["missing migration number(s): [2]"]
