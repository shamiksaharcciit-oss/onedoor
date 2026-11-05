from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tool_wrapper import guarded

from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.store.db import Database

NOW = datetime(2026, 11, 5, tzinfo=UTC)


def _engine():
    db = Database(tempfile.mktemp(suffix=".db"))
    db.init()
    conn = db.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.greet",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.ungreet",
            bounds=Bounds(strict_params=False),
        ),
    )
    config = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=30.0, tz=ZoneInfo("UTC")
    )
    return conn, config


def test_a_permitted_call_runs_the_tool_and_reports() -> None:
    conn, config = _engine()
    calls = []

    @guarded("demo.greet", conn=conn, config=config, now=lambda: NOW)
    def greet(name: str) -> dict:
        calls.append(name)
        return {"greeting": f"hello {name}"}

    result = greet(name="ada")
    assert result == {"status": "executed", "result": {"greeting": "hello ada"}}
    assert calls == ["ada"]


def test_a_denied_action_never_calls_the_tool() -> None:
    conn, config = _engine()
    calls = []

    @guarded("demo.unlisted", conn=conn, config=config, now=lambda: NOW)
    def act(**_: object) -> dict:
        calls.append(1)
        return {}

    result = act()
    assert result["status"] == "denied"
    assert calls == []
