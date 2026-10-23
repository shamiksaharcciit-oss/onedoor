"""`decision_digest` stays stable across the `/6` preimage bump (migrations 0030,
0031), and a mismatch in the two new columns is still DETECTED through
`onedoor.decision_ref.check` -- the two properties onetrace's and onedoor 0.9's
vectors both depend on.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from onedoor import decision_digest as decision_digest_module
from onedoor.decision_digest import decision_digest
from onedoor.decision_ref import FORMAT, check
from onedoor.export import export_rows, write_export
from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.store.db import _MIGRATIONS_DIR, run_migrations
from tests.conftest import make_request

ISSUER = "https://onedoor.example/test"


def _apply_migrations_up_to(conn: sqlite3.Connection, *, before: str) -> None:
    """The schema as it was right before migration `before` ran -- every
    migration whose filename sorts earlier, applied and recorded exactly as
    `run_migrations` does, so a later `run_migrations(conn)` call picks up
    only `before` and whatever comes after it.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if path.name >= before:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
            (path.name,),
        )


def _legacy_row(conn: sqlite3.Connection, *, request_id: str) -> None:
    """One row, inserted with exactly the columns a pre-`0030` build would have
    had available -- nothing from migrations `0030`/`0031` is named, so this
    fails loudly if the schema it runs against already has them required.
    """
    conn.execute(
        "INSERT INTO actions_audit "
        "(request_id, kind, action_type, source, params_json, decision, reason_code, "
        "nominal_tier, effective_tier, created_at, protocol) "
        "VALUES (?, 'exec_intent', 'demo.legacy', 'ui', '{}', 'executed', 'passed', 1, 1, "
        "'2026-07-05T12:00:00Z', 'aadp/0.2')",
        (request_id,),
    )


def test_a_pre_0030_row_keeps_its_decision_digest_after_0030_and_0031(
    tmp_path: Path,
) -> None:
    conn = sqlite3.connect(str(tmp_path / "legacy.db"))
    conn.row_factory = sqlite3.Row
    _apply_migrations_up_to(conn, before="0030_approval_resume_key.sql")

    columns_before = {r["name"] for r in conn.execute("PRAGMA table_info(actions_audit)")}
    assert "resume_digest_expected" not in columns_before, "schema is not actually pre-0030"

    request_id = str(uuid4())
    _legacy_row(conn, request_id=request_id)
    row_before = conn.execute(
        "SELECT * FROM actions_audit WHERE request_id=?", (request_id,)
    ).fetchone()
    digest_before = decision_digest(row_before)
    ref = {
        "format": FORMAT,
        "request_id": request_id,
        "decision_digest": digest_before,
        "verdict": "permit",
        "issuer": ISSUER,
    }

    applied = run_migrations(conn)
    assert "0030_approval_resume_key.sql" in applied
    assert "0031_resume_digest_mismatch.sql" in applied

    row_after = conn.execute(
        "SELECT * FROM actions_audit WHERE request_id=?", (request_id,)
    ).fetchone()
    assert row_after["resume_digest_expected"] is None
    assert row_after["resume_digest_actual"] is None
    digest_after = decision_digest(row_after)
    assert digest_after == digest_before, (
        "decision_digest moved when 0030/0031 only added NULL columns"
    )

    out = tmp_path / "export.jsonl"
    write_export(conn, out)
    exported = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    result = check(ref, exported)
    assert result.status == "matches", (
        f"a reference made before migrating no longer matches an export made after: {result.detail}"
    )
    conn.close()


def test_sabotage_without_the_none_omission_the_digest_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirms the assertion above actually depends on the None-omission list,
    not on a coincidence: with `resume_digest_expected`/`resume_digest_actual`
    removed from it, the same row's digest changes the moment the migration
    adds the (NULL) columns.
    """
    conn = sqlite3.connect(str(tmp_path / "legacy.db"))
    conn.row_factory = sqlite3.Row
    _apply_migrations_up_to(conn, before="0030_approval_resume_key.sql")
    request_id = str(uuid4())
    _legacy_row(conn, request_id=request_id)
    row_before = conn.execute(
        "SELECT * FROM actions_audit WHERE request_id=?", (request_id,)
    ).fetchone()
    digest_before = decision_digest(row_before)
    run_migrations(conn)
    row_after = conn.execute(
        "SELECT * FROM actions_audit WHERE request_id=?", (request_id,)
    ).fetchone()

    monkeypatch.setattr(
        decision_digest_module, "OMIT_WHEN_NONE", ("resumes_audit_id", "decide_principal")
    )
    digest_after_sabotaged = decision_digest(row_after)

    assert digest_after_sabotaged != digest_before, (
        "sabotage had no effect: the test does not actually exercise the omission list"
    )
    conn.close()


@pytest.fixture
def confirm_conn(tmp_path: Path):  # type: ignore[no-untyped-def]
    from onedoor.store.db import Database

    database = Database(str(tmp_path / "confirm.db"))
    database.init()
    conn = database.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.confirm6",
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(strict_params=False),
        ),
    )
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def confirm_config() -> EngineConfig:
    from zoneinfo import ZoneInfo

    return EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC"), issuer=ISSUER
    )


def test_v6_rows_with_and_without_resume_keys_both_match_and_tampering_is_caught(
    confirm_conn: sqlite3.Connection, confirm_config: EngineConfig
) -> None:
    conn, config = confirm_conn, confirm_config

    req_a = make_request("demo.confirm6", {"amount": "1"})
    outcome_a = decide_and_reserve(req_a, conn=conn, config=config, now=req_a.created_at)
    ref_a = outcome_a.decision_ref
    assert ref_a is not None

    req_b1 = make_request("demo.confirm6", {"amount": "10"})
    decide_and_reserve(
        req_b1,
        conn=conn,
        config=config,
        now=req_b1.created_at,
        thread_id="t-1",
        tool_call_id="c-1",
    )
    req_b2 = make_request("demo.confirm6", {"amount": "99"})
    outcome_b = decide_and_reserve(
        req_b2,
        conn=conn,
        config=config,
        now=req_b2.created_at,
        thread_id="t-1",
        tool_call_id="c-1",
    )
    ref_b = outcome_b.decision_ref
    assert ref_b is not None

    row_b = conn.execute(
        "SELECT resume_digest_expected, resume_digest_actual FROM actions_audit WHERE request_id=?",
        (str(req_b2.request_id),),
    ).fetchone()
    assert row_b["resume_digest_expected"] is not None
    assert row_b["resume_digest_actual"] is not None

    rows = export_rows(conn)
    ref_a_dict = ref_a.model_dump(mode="json")
    ref_b_dict = ref_b.model_dump(mode="json")

    assert check(ref_a_dict, rows).status == "matches"
    assert check(ref_b_dict, rows).status == "matches"

    for tampered_field in ("resume_digest_expected", "resume_digest_actual"):
        tampered_rows = [dict(r) for r in rows]
        for r in tampered_rows:
            if r.get("request_id") == str(req_b2.request_id):
                r[tampered_field] = "sha256:" + "0" * 64
        result = check(ref_b_dict, tampered_rows)
        assert result.status == "digest_mismatch", (
            f"tampering with {tampered_field} on an exported row was not detected: {result}"
        )


def test_sabotage_unconditional_omission_hides_tampering(
    confirm_conn: sqlite3.Connection, confirm_config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirms the tampering-detection assertion above is real: if the two
    mismatch columns were (wrongly) always dropped, not hashed when they carry
    a real value, altering one would not move `decision_digest` at all.
    """
    conn, config = confirm_conn, confirm_config
    req_b1 = make_request("demo.confirm6", {"amount": "10"})
    decide_and_reserve(
        req_b1,
        conn=conn,
        config=config,
        now=req_b1.created_at,
        thread_id="t-3",
        tool_call_id="c-3",
    )
    req_b2 = make_request("demo.confirm6", {"amount": "99"})
    decide_and_reserve(
        req_b2,
        conn=conn,
        config=config,
        now=req_b2.created_at,
        thread_id="t-3",
        tool_call_id="c-3",
    )
    rows = export_rows(conn)
    real_row = next(r for r in rows if r.get("request_id") == str(req_b2.request_id))
    assert real_row["resume_digest_actual"] is not None
    tampered_row = dict(real_row)
    tampered_row["resume_digest_actual"] = "sha256:" + "1" * 64

    # Without sabotage, tampering one byte of a hashed field must move the digest.
    assert decision_digest(real_row) != decision_digest(tampered_row)

    # Sabotage: always drop the two mismatch columns, not only when `None` --
    # the shape a column in `preimage.EXCLUDED` has, which is exactly wrong for
    # a column this project's own rule says must be hashed WHEN it is set.
    original_canon = decision_digest_module.canonical_row_record

    def _always_drops_mismatch_columns(row):  # type: ignore[no-untyped-def]
        record = original_canon(row)
        record.pop("resume_digest_expected", None)
        record.pop("resume_digest_actual", None)
        return record

    monkeypatch.setattr(
        decision_digest_module, "canonical_row_record", _always_drops_mismatch_columns
    )

    assert decision_digest(real_row) == decision_digest(tampered_row), (
        "sabotage had no effect: the test does not actually exercise detection of this tampering"
    )
