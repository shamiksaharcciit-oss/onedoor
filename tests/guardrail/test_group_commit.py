"""Group-commit for result rows: throughput without weakening what matters.

Intent rows are NEVER buffered — invariant 9 requires the intent durable before
the permit is returned. Result rows are buffered only when an operator asks for
it, because losing one on a crash leaves an intent with no result: the
recoverable, detectable state the invariant already demands, never a permit that
looks discharged.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from sqlite3 import Connection
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from onedoor.guardrail import audit, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_raw, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Policy, Tier
from tests.conftest import FROZEN_NOW


def _cfg(batch: int) -> EngineConfig:
    return EngineConfig(
        approval_ttl_seconds=3600,
        connector_timeout_seconds=1.0,
        tz=ZoneInfo("Europe/Amsterdam"),
        audit_group_commit=batch,
    )


@pytest.fixture
def seeded(conn: Connection) -> Connection:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="gc.act",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="gc.undo",
            bounds=Bounds(strict_params=False),
        ),
    )
    return conn


def _permit(conn: Connection, config: EngineConfig) -> PermittedIntent:
    out = decide_raw(
        {
            "request_id": str(uuid4()),
            "action_type": "gc.act",
            "params": {},
            "source": "llm",
            "rationale": "gc",
            "cost_eur": Decimal(0),
            "created_at": FROZEN_NOW,
        },
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(out, PermittedIntent)
    return out


def _rows(conn: Connection, kind: str) -> int:
    return conn.execute("SELECT count(*) c FROM actions_audit WHERE kind=?", (kind,)).fetchone()[
        "c"
    ]


def test_intent_rows_are_never_buffered(seeded: Connection) -> None:
    config = _cfg(10)
    for _ in range(3):
        _permit(seeded, config)
    assert _rows(seeded, "exec_intent") == 3, "an intent was buffered — invariant 9 broken"


def test_results_are_written_when_the_batch_fills(seeded: Connection) -> None:
    config = _cfg(3)
    intents = [_permit(seeded, config) for _ in range(3)]
    for i, intent in enumerate(intents):
        report_result(
            intent,
            conn=seeded,
            config=config,
            ok=True,
            payload=None,
            error=None,
            now=FROZEN_NOW,
        )
        expected = 3 if i == 2 else 0
        assert _rows(seeded, "exec_result") == expected


def test_flush_writes_a_partial_batch(seeded: Connection) -> None:
    config = _cfg(100)
    intent = _permit(seeded, config)
    report_result(
        intent, conn=seeded, config=config, ok=True, payload=None, error=None, now=FROZEN_NOW
    )
    assert _rows(seeded, "exec_result") == 0
    assert audit.flush(seeded) == 1
    assert _rows(seeded, "exec_result") == 1


def test_duplicate_report_still_rejected_while_buffered(seeded: Connection) -> None:
    """Exactly-once must not depend on reaching the database."""
    config = _cfg(100)
    intent = _permit(seeded, config)
    report_result(
        intent, conn=seeded, config=config, ok=True, payload=None, error=None, now=FROZEN_NOW
    )
    with pytest.raises(sqlite3.IntegrityError):
        report_result(
            intent,
            conn=seeded,
            config=config,
            ok=True,
            payload=None,
            error=None,
            now=FROZEN_NOW,
        )


def test_buffered_rows_keep_policy_version_and_parent(seeded: Connection) -> None:
    config = _cfg(1)
    intent = _permit(seeded, config)
    report_result(
        intent, conn=seeded, config=config, ok=True, payload=None, error=None, now=FROZEN_NOW
    )
    row = seeded.execute(
        "SELECT parent_id, policy_version, decision FROM actions_audit WHERE kind='exec_result'"
    ).fetchone()
    assert row["parent_id"] == intent.intent_audit_id
    assert row["policy_version"] == policy_loader.current_version(seeded)
    assert row["decision"] == "executed"


def test_default_is_off(seeded: Connection) -> None:
    """Buffering trades durability for throughput; that is an operator's choice."""
    config = _cfg(0)
    intent = _permit(seeded, config)
    report_result(
        intent, conn=seeded, config=config, ok=True, payload=None, error=None, now=FROZEN_NOW
    )
    assert _rows(seeded, "exec_result") == 1, "results must be durable by default"


def test_crash_before_flush_leaves_an_unresolved_intent(seeded: Connection) -> None:
    """The failure direction: 'we do not know yet', never 'this was authorized'."""
    config = _cfg(100)
    intent = _permit(seeded, config)
    report_result(
        intent, conn=seeded, config=config, ok=True, payload=None, error=None, now=FROZEN_NOW
    )
    # simulate the process dying: the buffer is lost, the database is not
    delattr(seeded, "_audit_buffer")
    orphans = seeded.execute(
        "SELECT count(*) c FROM actions_audit a WHERE a.kind='exec_intent' "
        "AND NOT EXISTS (SELECT 1 FROM actions_audit b WHERE b.kind='exec_result' "
        "AND b.request_id=a.request_id)"
    ).fetchone()["c"]
    assert orphans == 1
