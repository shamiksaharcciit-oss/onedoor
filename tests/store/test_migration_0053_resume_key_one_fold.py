"""Migration `0053` recreates `idx_approvals_resume_key` with the same
no-principal fold `onedoor.guardrail.approvals.principal_matches` already
uses -- a NUL-prefixed string, not `0052`'s own plain text -- so a principal
can never share the no-principal bucket in one layer and not the other.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from onedoor.guardrail.approvals import _NO_PRINCIPAL
from onedoor.store.db import Database

THREAD = "one-fold-thread"
CALL = "one-fold-call"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    database = Database(str(tmp_path / "one_fold.db"))
    database.init()
    return database.connect()


def _insert(conn: sqlite3.Connection, *, proposed_by: str | None) -> None:
    conn.execute(
        "INSERT INTO approvals "
        "(request_json, action_type, state, created_at, expires_at, proposed_by, "
        "thread_id, tool_call_id) "
        "VALUES ('{}', 'demo.confirm', 'pending', '2026-01-01T00:00:00+00:00', "
        "'2099-01-01T00:00:00+00:00', ?, ?, ?)",
        (proposed_by, THREAD, CALL),
    )


def test_a_proposer_literally_named_the_sql_fold_still_collides_with_none(
    conn: sqlite3.Connection,
) -> None:
    """The exact string `principal_matches` folds `None` into -- `_NO_PRINCIPAL`
    decoded as text -- must be the same string the index folds a NULL
    `proposed_by` into. If it is, a row genuinely proposed by that literal
    text collides with a `NULL`-proposed row at the same key, because the
    index cannot tell them apart -- proving the two layers share one fold.
    """
    literal_fold = _NO_PRINCIPAL.decode("utf-8")
    _insert(conn, proposed_by=None)
    with pytest.raises(sqlite3.IntegrityError):
        _insert(conn, proposed_by=literal_fold)


def test_0052s_own_old_text_no_longer_folds_with_none(conn: sqlite3.Connection) -> None:
    """`0052`'s own former sentinel text is just an ordinary principal name
    now -- it must NOT collide with a `NULL`-proposed row, since the index
    no longer folds on it. (It never collided with a NULL row's SELECTION
    either; this only confirms the index's own fold changed.)
    """
    _insert(conn, proposed_by=None)
    _insert(conn, proposed_by="onedoor:no-principal-resume-key")  # 0052's old sentinel text
    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM approvals WHERE thread_id=? AND tool_call_id=?",
        (THREAD, CALL),
    ).fetchone()
    assert rows["n"] == 2


def test_two_genuinely_unauthenticated_proposals_still_collide(conn: sqlite3.Connection) -> None:
    """The one case `0052` exists for is unchanged by `0053`: two proposals
    that both name no principal still collide at one key.
    """
    _insert(conn, proposed_by=None)
    with pytest.raises(sqlite3.IntegrityError):
        _insert(conn, proposed_by=None)
