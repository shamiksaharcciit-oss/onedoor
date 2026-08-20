"""v0.2 decision/enforcement split: decide_and_reserve / report_result.

The split must preserve the executor's semantics exactly: terminal outcomes
carry no obligation; a PermittedIntent means caps are reserved and the intent
row exists before any enforcement; report_result appends the linked result and
controls the undo window.
"""

from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Decision
from tests.conftest import FROZEN_NOW, make_request


def test_permitted_intent_then_report_executes(conn: Connection, config: EngineConfig) -> None:
    req = make_request("demo.toggle", {"target": "demo.lamp", "state": "on"})
    outcome = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(outcome, PermittedIntent)
    assert outcome.undo_until is not None  # reversible Tier-1 gets an undo window

    # Intent row exists BEFORE enforcement — the obligation is already on the record.
    row = conn.execute(
        "SELECT kind FROM actions_audit WHERE id=?", (outcome.intent_audit_id,)
    ).fetchone()
    assert row["kind"] == "exec_intent"

    result = report_result(
        outcome, conn=conn, ok=True, payload={"done": True}, error=None, now=FROZEN_NOW
    )
    assert result.executed is True
    assert result.undo_available_until == outcome.undo_until


def test_terminal_outcome_is_a_result_not_an_obligation(
    conn: Connection, config: EngineConfig
) -> None:
    req = make_request("demo.toggle", {"target": "demo.lamp", "state": "sideways"})
    outcome = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(outcome, PermittedIntent)
    assert outcome.decision.decision == Decision.DENIED


def test_report_failure_marks_failed_and_no_undo(conn: Connection, config: EngineConfig) -> None:
    req = make_request("demo.toggle", {"target": "demo.lamp", "state": "on"})
    outcome = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(outcome, PermittedIntent)
    result = report_result(
        outcome, conn=conn, ok=False, payload=None, error="enforcement failed", now=FROZEN_NOW
    )
    assert result.executed is False
    assert result.decision.decision == Decision.FAILED
    assert result.undo_available_until is None


def test_replay_guard_runs_before_decide(conn: Connection, config: EngineConfig) -> None:
    req = make_request("demo.toggle", {"target": "demo.lamp", "state": "on"})
    outcome = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(outcome, PermittedIntent)
    report_result(outcome, conn=conn, ok=True, payload=None, error=None, now=FROZEN_NOW)
    # The same request_id resolves to the recorded result, not a second intent.
    replay = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(replay, PermittedIntent)


def test_executor_and_split_agree(conn: Connection, config: EngineConfig) -> None:
    """The in-process executor is now literally the split composed — same audit shape."""
    from onedoor.connectors import mock
    from onedoor.guardrail.executor import evaluate_and_execute

    req = make_request("demo.toggle", {"target": "demo.lamp", "state": "on"})
    result = evaluate_and_execute(
        req, conn=conn, registry=mock.build_registry(), config=config, now=FROZEN_NOW
    )
    assert result.executed is True
    kinds = [
        r["kind"]
        for r in conn.execute(
            "SELECT kind FROM actions_audit WHERE request_id=? ORDER BY id",
            (str(req.request_id),),
        )
    ]
    assert kinds == ["exec_intent", "exec_result"]
