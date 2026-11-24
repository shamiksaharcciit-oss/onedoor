"""onedoor 0.12 (README Roadmap): "an unknown tool outcome ... holds the
action until someone settles it, closing the duplicate-effect gap" -- a naive
retry after a tool timeout must not carry out the same action twice while the
first attempt's own outcome is still unreported.
"""

from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail.decision import (
    ActionResult,
    PermittedIntent,
    decide_and_reserve,
    report_result,
)
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import CheckId, Decision, Outcome
from tests.conftest import FROZEN_NOW, make_request

THREAD = "thread-outcome-1"
CALL = "call-outcome-1"


def _decide(conn: Connection, config: EngineConfig):  # type: ignore[no-untyped-def]
    req = make_request("demo.flaky")
    return decide_and_reserve(
        req, conn=conn, config=config, now=FROZEN_NOW, thread_id=THREAD, tool_call_id=CALL
    )


def test_a_retry_at_the_same_key_holds_while_the_first_attempts_outcome_is_unknown(
    conn: Connection, config: EngineConfig
) -> None:
    first = _decide(conn, config)
    assert isinstance(first, PermittedIntent), "demo.flaky auto-permits; nothing to report yet"

    # The caller never reports first's outcome -- exactly a crash or a timeout
    # between executing the tool and calling report_result.
    second = _decide(conn, config)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
    assert second.decision.reason_code == CheckId.OUTCOME_UNKNOWN_HOLD
    assert second.approval_id is not None

    rows = conn.execute(
        "SELECT kind FROM actions_audit WHERE resume_thread_id=? AND resume_tool_call_id=? "
        "ORDER BY id",
        (THREAD, CALL),
    ).fetchall()
    assert [r["kind"] for r in rows] == ["exec_intent", "decision"], (
        "the retry must not create a second exec_intent (no second execution risked)"
    )


def test_a_retry_at_the_same_key_proceeds_once_the_first_outcome_is_reported(
    conn: Connection, config: EngineConfig
) -> None:
    first = _decide(conn, config)
    assert isinstance(first, PermittedIntent)

    report_result(
        first, conn=conn, outcome=Outcome.SUCCESS, payload={"ok": True}, error=None, now=FROZEN_NOW
    )

    second = _decide(conn, config)
    assert isinstance(second, PermittedIntent), (
        "once the first attempt's outcome is settled, a fresh call at the same key "
        "must be decided on its own merits again, not held forever"
    )


def test_an_ordinary_call_with_no_resume_key_is_never_held_by_this_check(
    conn: Connection, config: EngineConfig
) -> None:
    first = decide_and_reserve(make_request("demo.flaky"), conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(first, PermittedIntent)
    second = decide_and_reserve(
        make_request("demo.flaky"), conn=conn, config=config, now=FROZEN_NOW
    )
    assert isinstance(second, PermittedIntent), "absent a resume key, this check never runs at all"


def test_a_float_valued_param_at_this_key_holds_rather_than_raising(
    conn: Connection, config: EngineConfig
) -> None:
    """0.12.1: this branch's own `approvals.create()` call used
    to raise `TypeError: floats are forbidden in canonical structures` the
    moment `request.params` carried a raw float -- `ActionRequest` now
    normalises it to `Decimal` before this ever runs, so the hold proceeds
    exactly as it does for any other params shape."""

    def _decide_with_amount() -> object:
        req = make_request("demo.flaky", {"amount_eur": 2400.0})
        return decide_and_reserve(
            req, conn=conn, config=config, now=FROZEN_NOW, thread_id=THREAD, tool_call_id=CALL
        )

    first = _decide_with_amount()
    assert isinstance(first, PermittedIntent)

    second = _decide_with_amount()
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
    assert second.decision.reason_code == CheckId.OUTCOME_UNKNOWN_HOLD
    assert second.approval_id is not None
