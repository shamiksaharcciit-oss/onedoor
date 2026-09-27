"""A database written by the real, released 0.8.0 (WO-D6 part 2's own condition
for merging): upgraded to this branch (migration 0025), every `decision_ref`
issued under 0.8.0 must still check `matches`, and every old `row_hash` must
still verify.

`tests/fixtures/upgrade_0.8.0.db` and its `_refs.json` sidecar are not generated
by this test suite -- built once by installing the actual released
`onedoor-0.8.0-py3-none-any.whl` (sha256 `e7adeb09…9b00`, the one core verified
on PyPI) into an isolated venv and running a small script against it: one
permitted, reported-success decision (issuing a `permit` decision_ref) and one
rate-denied decision (issuing a `deny` decision_ref), chaining enabled. A
regenerated fixture cannot show this -- it would be the new code testing
itself. Mirrors `tests/fixtures/chain_v2_61aaeed.db`'s own precedent exactly.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from onedoor.decision_ref import MATCHES, check
from onedoor.export import export_rows
from onedoor.guardrail import chain
from onedoor.guardrail.preimage import row_hash_of
from onedoor.store.db import Database, run_migrations

FIXTURE_DB = Path(__file__).resolve().parents[1] / "fixtures" / "upgrade_0.8.0.db"
FIXTURE_REFS = Path(__file__).resolve().parents[1] / "fixtures" / "upgrade_0.8.0_refs.json"


def _copy(tmp_path: Path) -> Database:
    target = tmp_path / "upgrade_0.8.0_copy.db"
    shutil.copy(FIXTURE_DB, target)
    return Database(str(target))


def test_the_fixture_is_genuinely_pre_0025(tmp_path: Path) -> None:
    """Sanity: the fixture must actually predate migration 0025, or the rest of
    this file proves nothing about an upgrade."""
    conn = _copy(tmp_path).connect()
    try:
        applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        assert not any(v.startswith("0025") for v in applied)
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(actions_audit)")}
        assert "resumes_audit_id" not in columns
        rows = list(conn.execute("SELECT preimage_version FROM actions_audit"))
        assert rows, "the fixture must actually carry rows"
        assert all(r["preimage_version"] == "onedoor/row-preimage/3" for r in rows)
    finally:
        conn.close()


def test_every_old_row_hash_still_verifies_after_the_upgrade(tmp_path: Path) -> None:
    conn = _copy(tmp_path).connect()
    try:
        applied = run_migrations(conn)
        assert any(v.startswith("0025") for v in applied), (
            "the upgrade must actually apply 0025, or this test checks nothing new"
        )
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(actions_audit)")}
        assert "resumes_audit_id" in columns

        rows = list(conn.execute("SELECT * FROM actions_audit ORDER BY id"))
        assert len(rows) == 3
        for row in rows:
            assert row_hash_of(row) == row["row_hash"], (
                f"row id={row['id']} no longer reproduces its own stored row_hash "
                f"after the 0025 upgrade"
            )

        report = chain.verify_chain(conn)
        assert report.sound, (
            f"the chain no longer verifies after the upgrade: "
            f"{[(r.status.value, r.detail) for r in report.regions]}"
        )
    finally:
        conn.close()


def test_every_0_8_0_decision_ref_still_matches_after_the_upgrade(tmp_path: Path) -> None:
    conn = _copy(tmp_path).connect()
    try:
        run_migrations(conn)
        refs = json.loads(FIXTURE_REFS.read_text(encoding="utf-8"))
        assert len(refs) == 2, "the fixture must carry both issued references"
        exported = list(export_rows(conn))
        for ref in refs:
            result = check(ref, exported)
            assert result.status == MATCHES, (
                f"decision_ref for request_id={ref['request_id']} no longer matches "
                f"after the upgrade: {result.detail}"
            )
    finally:
        conn.close()


def test_sabotage_a_changed_byte_no_longer_verifies(tmp_path: Path) -> None:
    """The positive tests above are not vacuous: corrupting one stored row after
    the same upgrade shows both checks catch it. `actions_audit` is append-only
    (a trigger refuses UPDATE), so the trigger is dropped and recreated around
    the one deliberate corruption, the same dance the codebase's own existing
    sabotage tests use for this table."""
    conn = _copy(tmp_path).connect()
    try:
        run_migrations(conn)
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute(
            "UPDATE actions_audit SET row_hash=? WHERE id=1",
            ("0" * 64,),
        )
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only: UPDATE forbidden'); END"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM actions_audit WHERE id=1").fetchone()
        assert row_hash_of(row) != row["row_hash"]

        report = chain.verify_chain(conn)
        assert not report.sound, "a tampered row must not verify"

        refs = json.loads(FIXTURE_REFS.read_text(encoding="utf-8"))
        exported = list(export_rows(conn))
        permit_ref = next(r for r in refs if r["verdict"] == "permit")
        result = check(permit_ref, exported)
        assert result.status != MATCHES
    finally:
        conn.close()
