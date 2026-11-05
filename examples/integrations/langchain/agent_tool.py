"""A LangChain tool whose call goes through onedoor's shipped middleware.

A denial returns to the agent as the tool's own result, with its reason
code, so the model can read it and carry on -- it is never an exception the
agent has to recover from.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.integrations.langchain_middleware import OneDoorMiddleware
from onedoor.store.db import Database

PAID: list[float] = []


@tool
def pay_invoice(invoice_id: str, amount_eur: float) -> str:
    """Pay a supplier invoice."""
    PAID.append(amount_eur)
    return f"paid {amount_eur} for {invoice_id}"


def build_engine(db_path: str) -> tuple[object, EngineConfig]:
    database = Database(db_path)
    database.init()
    conn = database.connect(check_same_thread=False)
    policy_loader.upsert(
        conn,
        Policy(
            action_type="tool.pay_invoice",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="tool.pay_invoice",
            bounds=Bounds(strict_params=False),
        ),
    )
    config = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC")
    )
    return conn, config


def build_middleware(db_path: str) -> OneDoorMiddleware:
    conn, config = build_engine(db_path)
    return OneDoorMiddleware(conn, config)
