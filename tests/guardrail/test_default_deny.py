"""An action type no policy declares is denied, with reason `default_deny`.

Absence of policy is a denial, never a permission and never a question for a human: an
unlisted action creates no approval, reaches no connector, and says in its refusal what
would allow it.
"""

from __future__ import annotations

import json
from sqlite3 import Connection

from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import CheckId, Decision
from onedoor.guardrail.registry import ConnectorRegistry
from tests.conftest import make_request


def test_an_unlisted_action_is_denied_with_default_deny_and_creates_no_approval(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    req = make_request("totally.unknown.action")
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )

    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.DEFAULT_DENY
    assert result.approval_id is None
    assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    assert "declare" in (result.decision.detail or ""), "the refusal says what would allow it"

    row = conn.execute(
        "SELECT evaluation_trace_json FROM actions_audit WHERE id=?", (result.audit_id,)
    ).fetchone()
    trace = json.loads(row[0])
    assert trace[-1]["check"] == "default_deny"
    assert trace[-1]["result"] == "fail"


def test_unlisted_action_never_touches_connector(conn: Connection, config: EngineConfig) -> None:
    called: list[str] = []
    registry = ConnectorRegistry()
    registry.register("spy.action", lambda params: called.append("x") or {"ok": True})

    req = make_request("spy.action")
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )

    # spy.action has a connector but no policy: denied, and its connector never runs.
    assert result.decision.decision == Decision.DENIED
    assert called == []


def test_an_empty_policy_table_denies_everything(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    conn.execute("DELETE FROM policies")
    req = make_request("demo.toggle", {"target": "demo.lamp", "state": "on"})
    result = evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.DEFAULT_DENY
