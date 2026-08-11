from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection

import pytest
from onedoor.guardrail import policy_loader
from onedoor.guardrail.policy import PolicyStore
from tests.conftest import _CONFIG_DIR


def test_seed_file_is_idempotent(conn: Connection) -> None:
    before = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    policy_loader.load_file(conn, _CONFIG_DIR / "policies.yaml")
    after = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    assert before == after  # re-loading changes nothing


def test_tier1_without_compensation_is_rejected(conn: Connection, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "policies:\n  - action_type: bad.action\n    tier: 1\n    dry_run: false\n",
        encoding="utf-8",
    )
    count_before = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    with pytest.raises(ValueError, match="compensating_command"):
        policy_loader.load_file(conn, bad)
    # Fail-closed: nothing was written.
    count_after = conn.execute("SELECT COUNT(*) c FROM policies").fetchone()["c"]
    assert count_before == count_after


def test_bounds_and_caps_round_trip(conn: Connection) -> None:
    policy = PolicyStore().get(conn, "demo.toggle")
    assert policy.bounds.required == ["target", "state"]
    assert policy.compensating_command == "demo.restore"
    capped = PolicyStore().get(conn, "demo.capped")
    assert capped.caps.daily_rate == 2
