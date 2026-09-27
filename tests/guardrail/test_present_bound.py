"""`present_bound` (AADP -03 §6): the audience URI a permit is bound to.

The three checks this covers, plus the fail-closed rule §6 itself states for a
PEP that does not implement audience presentation.
"""

from __future__ import annotations

import json
from sqlite3 import Connection

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import ActionResult, PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import Bounds, Policy, Source, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from tests.conftest import FROZEN_NOW, make_request

ACTION = "demo.present_bound"
AUDIENCE = "https://payments.example.com/audience"


def _policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            present_bound=AUDIENCE,
        ),
    )


def _request(audience: str | None) -> object:
    return make_request(ACTION, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"presented_audience": audience}
    )


def test_a_matching_audience_is_permitted(conn: Connection, config: EngineConfig) -> None:
    _policy(conn)
    result = decide_and_reserve(_request(AUDIENCE), conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    assert result.present_bound == AUDIENCE


def test_a_mismatched_audience_is_refused_with_a_stated_reason_and_appears_in_the_trace(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)
    result = decide_and_reserve(
        _request("https://wrong.example.com/"), conn=conn, config=config, now=FROZEN_NOW
    )
    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "denied"
    assert result.decision.reason_code.value == "present_bound"
    assert AUDIENCE in (result.decision.detail or "")

    row = conn.execute(
        "SELECT evaluation_trace_json FROM actions_audit WHERE id=?", (result.audit_id,)
    ).fetchone()
    trace = json.loads(row["evaluation_trace_json"])
    matching = [e for e in trace if e["check"] == "present_bound"]
    assert matching and matching[-1]["result"] == "fail"


def test_an_absent_audience_against_a_declared_bound_is_a_mismatch(
    conn: Connection, config: EngineConfig
) -> None:
    """No `presented_audience` at all is not a free pass -- it is simply not equal
    to the declared bound, and is refused the same way any other mismatch is."""
    _policy(conn)
    result = decide_and_reserve(_request(None), conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.decision.reason_code.value == "present_bound"


def test_an_action_with_no_bound_behaves_exactly_as_before(
    conn: Connection, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.no_bound",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    result = decide_and_reserve(
        make_request("demo.no_bound", {}, source=Source.LLM, now=FROZEN_NOW),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)
    assert result.present_bound is None

    row = conn.execute(
        "SELECT evaluation_trace_json FROM actions_audit WHERE id=?", (result.intent_audit_id,)
    ).fetchone()
    trace = json.loads(row["evaluation_trace_json"])
    assert "present_bound" not in [e["check"] for e in trace], (
        "an unset bound is a check that never ran and must not appear in the trace"
    )


# --- The fail-closed rule (-03 §6): a PEP that doesn't implement presentation ------


def test_the_in_process_executor_refuses_to_self_execute_a_bound_permit(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    _policy(conn)
    called = []
    registry.register(ACTION, lambda p: called.append(p) or {"ok": True})

    result = evaluate_and_execute(
        _request(AUDIENCE), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert not called, "the executor must never call the connector for a bound permit"
    assert result.decision.decision.value == "failed"
    assert result.connector_ok is None, "not_attempted carries NULL connector_ok, never False"

    row = conn.execute(
        "SELECT outcome FROM actions_audit WHERE kind='exec_result' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["outcome"] == "not_attempted"
