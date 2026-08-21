"""The `aadp/0.2` vocabulary and the protocol stamp (ND-002 / W4).

A rename is the easy half. The rules that survive a rename are the ones a test has to
hold: that the deprecated codes are *gone* rather than merely unused, that a reserved
code is not emitted before the check that justifies it exists, that every row this PDP
writes says which vocabulary it is written in, and that a row with no stamp is read
under the old one rather than assumed to be new.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from onedoor.guardrail import policy_loader
from onedoor.guardrail.audit import AADP_PROTOCOL
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    CheckId,
    Policy,
    Source,
    Tier,
)
from onedoor.store.db import Database

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
CONFIG = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC"))

DEPRECATED = {"cap_daily_rate", "cap_eur_day", "cap_eur_month"}


def test_the_deprecated_codes_are_gone_not_merely_unused() -> None:
    """Clean break, no dual emission (E1).

    Safe precisely because reason codes are AUDIT vocabulary: a PEP's behaviour is
    fixed by the verdict, never by the reason string, so a `-00` PEP that has never
    heard of `cap_value` still denies correctly. The break is audit-only.
    """
    live = {c.value for c in CheckId}
    assert not (live & DEPRECATED), f"a PDP at {AADP_PROTOCOL} must not carry {live & DEPRECATED}"
    assert {"cap_rate", "cap_value"} <= live


def test_sender_mismatch_is_reserved_and_never_emitted() -> None:
    """Reserved in one breaking increment; emitted only when ND-005 wires the check.

    The code exists so the vocabulary change is complete in a single release. Until
    the sender-binding check exists, emitting it would be a reason code for a check
    that never ran -- the gate-that-never-fired class, wearing a reason string.
    """
    assert CheckId.SENDER_MISMATCH.value == "sender_mismatch"
    emitted = _all_reason_codes_reachable_in_the_package()
    assert "sender_mismatch" not in emitted, (
        "sender_mismatch is emitted somewhere, but ND-005 has not wired the check it "
        "reports on. Reserve the code; ship the check later."
    )


def _all_reason_codes_reachable_in_the_package() -> set[str]:
    """Reason codes the engine can actually produce, by construction site."""
    import re
    from pathlib import Path

    package = Path(__file__).resolve().parents[2] / "onedoor"
    used: set[str] = set()
    for path in package.rglob("*.py"):
        if "_vendor" in path.parts:
            continue
        for match in re.finditer(r"CheckId\.([A-Z_]+)", path.read_text(encoding="utf-8")):
            used.add(CheckId[match.group(1)].value)
    return used


def test_every_row_this_pdp_writes_is_stamped_with_its_vocabulary(tmp_path) -> None:  # noqa: ANN001
    """E6: a PDP at aadp/0.2+ MUST stamp every row."""
    database = Database(str(tmp_path / "stamp.db"))
    database.init()
    conn = database.connect()
    try:
        policy_loader.upsert(
            conn,
            Policy(
                action_type="demo.rate",
                tier=Tier.AUTO_CAPPED,
                dry_run=False,
                compensating_command="demo.rate",
                caps=Caps(daily_rate=1),
                bounds=Bounds(strict_params=False),
            ),
        )
        for _ in range(2):
            decide_and_reserve(
                ActionRequest(
                    request_id=uuid4(),
                    action_type="demo.rate",
                    params={},
                    source=Source.UI,
                    rationale="stamp",
                    cost_eur=Decimal(0),
                    created_at=NOW,
                ),
                conn=conn,
                config=CONFIG,
                now=NOW,
            )
        rows = list(conn.execute("SELECT kind, protocol, reason_code FROM actions_audit"))
        assert rows, "the probe must actually write rows"
        assert all(r["protocol"] == AADP_PROTOCOL for r in rows), (
            f"unstamped rows: {[dict(r) for r in rows if r['protocol'] != AADP_PROTOCOL]}"
        )
        assert any(r["reason_code"] == "cap_rate" for r in rows), (
            "the rate cap must deny with the unit-neutral code"
        )
    finally:
        conn.close()


def test_an_unstamped_row_is_read_under_the_old_vocabulary(tmp_path) -> None:  # noqa: ANN001
    """The absent-value rule (E6), which is why the column is nullable.

    A row written before 0.4.0 carries no stamp. That absence is a FACT about when it
    was written, not a value to invent -- and it must resolve to `aadp/0.1`, under
    which `cap_eur_day` is a legitimate code rather than a corrupt one.
    """
    database = Database(str(tmp_path / "old.db"))
    database.init()
    conn = database.connect()
    try:
        conn.execute(
            "INSERT INTO actions_audit (request_id, kind, action_type, source, params_json,"
            " decision, reason_code, nominal_tier, effective_tier, created_at)"
            " VALUES ('legacy','decision','demo.x','ui','{}','denied','cap_eur_day',2,2,?)",
            (NOW.isoformat(),),
        )
        row = conn.execute("SELECT protocol, reason_code FROM actions_audit").fetchone()
        assert row["protocol"] is None
        assert protocol_of(row) == "aadp/0.1"
        assert row["reason_code"] in DEPRECATED, (
            "a legacy row keeps the code it was written with; history is not rewritten"
        )
    finally:
        conn.close()


def protocol_of(row: sqlite3.Row) -> str:
    """An evidence row with no `protocol` value MUST be read under `aadp/0.1` (E6)."""
    return row["protocol"] or "aadp/0.1"


def test_the_snapshot_schema_is_recorded_beside_the_policy_hash(tmp_path) -> None:  # noqa: ANN001
    """R019: a hash diff on upgrade must be attributable from the record.

    `100`, `100.00` and `1E+2` hashing identically is the point of the renderer; the
    cost is that an unchanged policy set gets a new hash once. Recording which
    canonicalisation produced the hash is what lets a reader tell "renderer changed,
    rules did not" from "rules changed" without remembering when the upgrade was.
    """
    database = Database(str(tmp_path / "snap.db"))
    database.init()
    conn = database.connect()
    try:
        policy_loader.upsert(
            conn,
            Policy(
                action_type="demo.x",
                tier=Tier.AUTO,
                dry_run=False,
                compensating_command="demo.x",
                bounds=Bounds(strict_params=False),
            ),
        )
        row = conn.execute(
            "SELECT version_hash, snapshot_schema FROM policy_versions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row["version_hash"], "a snapshot must be recorded"
        assert row["snapshot_schema"] == policy_loader.SNAPSHOT_SCHEMA
        assert row["snapshot_schema"].endswith("/2"), (
            "0.4.0 is schema 2; absent means schema 1, by the same rule as an "
            "unstamped protocol column meaning aadp/0.1"
        )
    finally:
        conn.close()
