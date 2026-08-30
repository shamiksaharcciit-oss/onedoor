"""`ND-056` / T2 — studio schema 3: the `state` column, and the upgrade that adds it.

The Studio store carries its OWN version (R047 §2). No enforcer migration number is
claimed here and none should be: `BACKLOG.md`'s register released `0019`+ for exactly
this reason — the enforcer's numbered sequence is the enforcer's history, and a column
in a different file that a different process owns does not belong in it.
"""

from __future__ import annotations

import sqlite3

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


def test_no_enforcer_migration_number_was_claimed_for_this() -> None:
    """The boundary, asserted against the register rather than remembered.

    `0019`+ stands released in `BACKLOG.md`. If a future change spends one of those
    numbers on a Studio table, this test is where that decision has to be argued.
    """
    from pathlib import Path

    backlog = Path(__file__).resolve().parents[2] / "BACKLOG.md"
    text = backlog.read_text(encoding="utf-8")
    assert "| `0019`+ | unclaimed" in text, (
        "the migration register no longer shows 0019+ as unclaimed; if a Studio column "
        "took an enforcer migration number, R047 §2's boundary was written out of the "
        "record"
    )
