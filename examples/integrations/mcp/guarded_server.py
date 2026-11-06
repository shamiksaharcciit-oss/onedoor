"""An MCP server (the ``mcp`` package's server API) whose tool handler calls
onedoor before acting. A gateway in front of any MCP server is planned, not
shipped -- this is the handler-level pattern instead.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Bounds, Outcome, Policy, Source, Tier
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

PAID: list[float] = []
_ENGINE: tuple[Any, EngineConfig] | None = None


def configure(db_path: str) -> None:
    global _ENGINE
    db = Database(db_path)
    db.init()
    conn = db.connect(check_same_thread=False)
    policy_loader.upsert(
        conn,
        Policy(
            action_type="tool.send_payment",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="tool.send_payment",
            bounds=Bounds(strict_params=False),
        ),
    )
    config = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC")
    )
    _ENGINE = (conn, config)


server = MCPServer("onedoor-demo")


@server.tool()
def send_payment(payee: str, amount_eur: float) -> str:
    """Send a payment to a payee."""
    if _ENGINE is None:
        raise RuntimeError("call configure(db_path) first")
    conn, config = _ENGINE
    now = now_utc()
    request = ActionRequest(
        request_id=uuid4(),
        action_type="tool.send_payment",
        params={"payee": payee, "amount_eur": amount_eur},
        source=Source.LLM,
        rationale="mcp example",
        created_at=now,
    )
    outcome = decide_and_reserve(request, conn=conn, config=config, now=now)
    if not isinstance(outcome, PermittedIntent):
        d = outcome.decision
        return f"onedoor: {d.decision.value} ({d.reason_code.value})"
    PAID.append(amount_eur)
    report_result(
        outcome,
        conn=conn,
        config=config,
        outcome=Outcome.SUCCESS,
        payload={},
        error=None,
        now=now_utc(),
    )
    return f"paid {amount_eur} to {payee}"
