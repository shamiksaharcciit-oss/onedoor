"""Approvals granted from the agent's side of the MCP proxy, before that side lost the
ability to approve, are retired on upgrade: an approval the agent gave itself must not
become presentable once the proxy honours approval references."""

from __future__ import annotations

from pathlib import Path

from onedoor.store.db import Database, run_migrations

ROWS = [
    ("approved", "mcp-proxy-demo"),  # the agent approved its own proposal
    ("approved", "operator"),
    ("executed", "mcp-proxy-demo"),
    ("pending", None),
]


def test_approvals_the_agent_gave_itself_are_retired_and_nothing_else_changes(
    tmp_path: Path,
) -> None:
    db = Database(str(tmp_path / "old.db"))
    db.init()
    conn = db.connect()
    migration = conn.execute(
        "SELECT version FROM schema_migrations WHERE version LIKE '%agent_self_approvals%'"
    ).fetchone()
    assert migration is not None, "the retiring migration exists and ran on a fresh store"

    conn.execute("DELETE FROM schema_migrations WHERE version = ?", (migration["version"],))
    for state, decided_by in ROWS:
        conn.execute(
            "INSERT INTO approvals (request_json, action_type, state, created_at, expires_at, "
            "decided_by_session) VALUES ('{}', 'mcp.send_payment', ?, 'a', 'b', ?)",
            (state, decided_by),
        )

    assert run_migrations(conn) == [migration["version"]]

    states = [r[0] for r in conn.execute("SELECT state FROM approvals ORDER BY id")]
    assert states[0] not in ("approved", "pending"), states
    assert states[1:] == ["approved", "executed", "pending"]
