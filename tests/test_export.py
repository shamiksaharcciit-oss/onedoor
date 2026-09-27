"""`python -m onedoor.export`: audit rows as stored, one JSON object per line.

Every check this covers, both directions: round-trip against the database row,
byte-identical repeat exports, the `.sha256` sidecar verifying, and `--since` filtering
exactly at the boundary.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.export import export_rows, main, write_export
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.store.db import Database
from tests.conftest import FROZEN_NOW, make_request


def _decide(conn: Connection, config: EngineConfig, *, when: object = FROZEN_NOW) -> None:
    decide_and_reserve(make_request("demo.toggle", {"x": 1}), conn=conn, config=config, now=when)  # type: ignore[arg-type]


def test_export_round_trips_every_row(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    for i in range(3):
        _decide(conn, config, when=FROZEN_NOW + timedelta(seconds=i))

    expected = [dict(row) for row in conn.execute("SELECT * FROM actions_audit ORDER BY id ASC")]
    assert len(expected) == 3
    # `resumes_audit_id` (migration 0025) is the one deliberate exception: omitted
    # by `canonical_row_record` whenever it is None, so an ordinary (non-resumption)
    # row's export matches what it would be without the column existing at all --
    # see that function's own docstring for why. None of these rows are resumptions.
    for row in expected:
        assert row.pop("resumes_audit_id") is None

    out = tmp_path / "export.jsonl"
    count = write_export(conn, out)
    assert count == 3

    exported = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert exported == expected, "every exported row must equal its database row, field for field"


def test_two_exports_of_the_same_data_are_byte_identical(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    for i in range(4):
        _decide(conn, config, when=FROZEN_NOW + timedelta(seconds=i))

    out1 = tmp_path / "a.jsonl"
    out2 = tmp_path / "b.jsonl"
    write_export(conn, out1)
    write_export(conn, out2)
    assert out1.read_bytes() == out2.read_bytes()


def test_the_sha256_sidecar_verifies(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    _decide(conn, config)
    out = tmp_path / "export.jsonl"
    write_export(conn, out)

    sidecar = tmp_path / "export.jsonl.sha256"
    assert sidecar.exists()
    digest, _, name = sidecar.read_text(encoding="utf-8").strip().partition("  ")
    assert name == out.name
    assert digest == hashlib.sha256(out.read_bytes()).hexdigest()


def test_since_filters_correctly_at_the_boundary(conn: Connection, config: EngineConfig) -> None:
    before = FROZEN_NOW
    boundary = FROZEN_NOW + timedelta(seconds=1)
    after = FROZEN_NOW + timedelta(seconds=2)
    _decide(conn, config, when=before)
    _decide(conn, config, when=boundary)
    _decide(conn, config, when=after)

    rows = export_rows(conn, since=boundary)
    assert len(rows) == 2, "the boundary row and everything after it, never the row before"
    kept_times = {row["created_at"] for row in rows}
    assert all(t >= boundary.isoformat() for t in kept_times)

    just_after_boundary = boundary + timedelta(microseconds=1)
    rows_after = export_rows(conn, since=just_after_boundary)
    assert len(rows_after) == 1, "one microsecond past the boundary row excludes it"


def test_since_orders_a_fractional_instant_after_the_same_whole_second(
    conn: Connection, config: EngineConfig
) -> None:
    """A row at `T` (no microseconds) and one at `T + 0.5s` (fractional, same second):
    the fractional row is chronologically later and must not be excluded by `--since T`,
    and `--since (T + 0.5s)` must exclude the whole-second row that preceded it."""
    whole_second = FROZEN_NOW.replace(microsecond=0)
    fractional = FROZEN_NOW.replace(microsecond=500_000)
    _decide(conn, config, when=whole_second)
    _decide(conn, config, when=fractional)

    assert len(export_rows(conn, since=whole_second)) == 2
    assert len(export_rows(conn, since=fractional)) == 1
    assert export_rows(conn, since=fractional)[0]["created_at"] == fractional.isoformat()


def test_cli_writes_export_and_sidecar(tmp_path: Path, config: EngineConfig) -> None:
    db_path = tmp_path / "cli.db"
    database = Database(str(db_path))
    database.init()
    conn = database.connect()
    try:
        _decide(conn, config)
    finally:
        conn.close()

    out = tmp_path / "cli-export.jsonl"
    rc = main(["--store", str(db_path), "--out", str(out)])
    assert rc == 0
    assert out.exists()
    assert (tmp_path / "cli-export.jsonl.sha256").exists()
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1


def test_no_float_ever_appears_in_an_exported_row(conn: Connection, config: EngineConfig) -> None:
    _decide(conn, config)
    for row in export_rows(conn):
        for value in row.values():
            assert not isinstance(value, float), f"a float leaked into an export row: {row!r}"


def test_missing_store_is_a_clear_argument_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--store", str(tmp_path / "does-not-exist.db"), "--out", str(tmp_path / "o.jsonl")])
