"""A resumption runs the full pipeline.

An approval satisfies the escalation that asked for a human. It does not skip
default-deny or dry-run, and a check the resumption did not evaluate never appears in
its trace -- least of all as pass.
"""

from __future__ import annotations

import json
from sqlite3 import Connection
from typing import Any

from onedoor.guardrail import approvals, policy_loader
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute, resume_approval
from onedoor.guardrail.models import Bounds, Caps, CheckId, Decision, Policy, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _spy(registry: ConnectorRegistry, action_type: str) -> list[Any]:
    called: list[Any] = []
    registry.register(action_type, lambda params: called.append(params) or {"ok": True})
    return called


def _state(conn: Connection, approval_id: int) -> str:
    return str(conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()[0])


def test_an_approved_dry_run_policy_rehearses_and_reserves_nothing(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.rehearse",
            tier=Tier.CONFIRM,
            dry_run=True,
            caps=Caps(daily_rate=1),
            bounds=Bounds(strict_params=False),
        ),
    )
    called = _spy(registry, "demo.rehearse")
    proposed = evaluate_and_execute(
        make_request("demo.rehearse"), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert proposed.approval_id is not None

    result = resume_approval(
        proposed.approval_id,
        "operator",
        conn=conn,
        registry=registry,
        config=config,
        now=FROZEN_NOW,
    )

    assert result.decision.decision == Decision.DRY_RUN
    assert called == [], "an approval does not turn a rehearsal into an execution"
    assert conn.execute("SELECT COUNT(*) FROM cap_reservations").fetchone()[0] == 0
    assert _state(conn, proposed.approval_id) == "consumed"


def test_an_approval_for_an_undeclared_action_is_denied_when_resumed(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """An approval can outlive the policy that made it possible -- one created before
    unlisted actions were denied, or for a policy since removed. Approving it resumes
    nothing: absence of policy is a denial on resumption too."""
    called = _spy(registry, "nobody.declared.this")
    with tx(conn):
        approval_id = approvals.create(
            conn, make_request("nobody.declared.this"), config.approval_ttl_seconds, FROZEN_NOW
        )

    result = resume_approval(
        approval_id, "operator", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )

    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.DEFAULT_DENY
    assert called == []
    assert _state(conn, approval_id) == "consumed"


def test_a_resumed_trace_records_only_the_checks_it_evaluated(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    """demo.confirm is tier 3 with no compensating command. The approval stands in for
    the human the tier asks for, so the reversibility and opaque-host escalations are
    not evaluated on resumption -- and so are not in its trace."""
    proposed = evaluate_and_execute(
        make_request("demo.confirm"), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert proposed.approval_id is not None
    result = resume_approval(
        proposed.approval_id,
        "operator",
        conn=conn,
        registry=registry,
        config=config,
        now=FROZEN_NOW,
    )
    assert result.executed is True

    row = conn.execute(
        "SELECT evaluation_trace_json FROM actions_audit "
        "WHERE kind='exec_intent' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    trace = json.loads(row[0])
    checks = [entry["check"] for entry in trace]
    assert "reversibility" not in checks, checks
    assert "opaque_host" not in checks, checks
    assert "default_deny" in checks and "dry_run" in checks, checks
    assert all(entry["result"] == "pass" for entry in trace), trace
