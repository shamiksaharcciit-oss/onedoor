from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail import killswitch
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import CheckId, Decision, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import make_request

TOGGLE = {"target": "demo.lamp", "state": "on"}


def _engage(conn: Connection) -> None:
    with tx(conn):
        killswitch.set_engaged(conn, True)


def _run(conn, registry, config, action, params=None):  # type: ignore[no-untyped-def]
    req = make_request(action, params)
    return evaluate_and_execute(
        req, conn=conn, registry=registry, config=config, now=req.created_at
    )


def test_engaged_clamps_tier1_to_propose(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    _engage(conn)
    result = _run(conn, registry, config, "demo.toggle", TOGGLE)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.KILL_SWITCH
    assert result.decision.effective_tier == Tier.CONFIRM


def test_engaged_clamps_tier2_to_propose(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    _engage(conn)
    assert _run(conn, registry, config, "demo.tier2").decision.decision == Decision.PROPOSED


def test_reads_exempt_from_kill_switch(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    _engage(conn)
    result = _run(conn, registry, config, "demo.read")
    assert result.decision.decision == Decision.EXECUTED
    assert result.decision.reason_code == CheckId.OBSERVE


def test_checked_before_policy_lookup(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    # Unknown type + kill engaged is still PROPOSED (kill switch reason wins over default-deny).
    _engage(conn)
    result = _run(conn, registry, config, "totally.unknown")
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.KILL_SWITCH


def test_disengage_restores_execution(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    _engage(conn)
    assert (
        _run(conn, registry, config, "demo.toggle", TOGGLE).decision.decision == Decision.PROPOSED
    )
    with tx(conn):
        killswitch.set_engaged(conn, False)
    assert _run(conn, registry, config, "demo.toggle", TOGGLE).executed is True
