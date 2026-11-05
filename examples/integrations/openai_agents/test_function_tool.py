"""No model, no network: calls the tool through the framework's own
FunctionTool.on_invoke_tool, the same path a real Agent run would use, with
no Agent and no API key."""

from __future__ import annotations

import asyncio
import json
import tempfile

from agents.tool_context import ToolContext
from function_tool import PAID, configure, send_payment


def _invoke(args: dict) -> str:
    ctx = ToolContext(
        context=None,
        tool_name="send_payment",
        tool_call_id="c1",
        tool_arguments=json.dumps(args),
    )
    return asyncio.run(send_payment.on_invoke_tool(ctx, json.dumps(args)))


def test_a_permitted_call_executes() -> None:
    PAID.clear()
    configure(tempfile.mktemp(suffix=".db"))
    result = _invoke({"payee": "acme", "amount_eur": 42.0})
    assert result == "paid 42.0 to acme"
    assert PAID == [42.0]
