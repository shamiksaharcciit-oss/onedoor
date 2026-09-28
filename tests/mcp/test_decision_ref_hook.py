"""The MCP proxy exposes the decision reference of the last decision it acted
on, via `Proxy.last_decision_ref` -- a documented hook, since the proxy speaks
MCP's own wire format on both sides and cannot embed the reference inside a
downstream tool's own JSON-RPC response without conflating two different
messages.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from onedoor.guardrail import approvals
from onedoor.mcp.proxy import Proxy
from onedoor.store.clock import now_utc
from onedoor.store.db import tx

ROOT = Path(__file__).parent.parent.parent
ISSUER = "https://onedoor.example/mcp-deployment"


def _proxy(*, issuer: str | None = ISSUER) -> Proxy:
    # The real demo downstream (onedoor/mcp/demo_server.py), the same one the
    # end-to-end demo drives -- it actually answers `tools/call`, which the
    # resumed-approval test below needs.
    return Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        ROOT / "config" / "mcp_policies.yaml",
        tempfile.mktemp(suffix=".db"),
        issuer=issuer,
    )


def test_no_issuer_configured_the_hook_stays_none() -> None:
    proxy = _proxy(issuer=None)
    assert proxy.last_decision_ref is None
    proxy.handle_tools_call(
        {
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "send_payment",
                "arguments": {"payee": "webshop", "amount_eur": 49.99},
            },
        }
    )
    assert proxy.last_decision_ref is None


def test_a_proposed_call_is_obtainable_through_the_hook() -> None:
    proxy = _proxy()
    assert proxy.last_decision_ref is None
    proxy.handle_tools_call(
        {
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "send_payment",
                "arguments": {"payee": "webshop", "amount_eur": 49.99},
            },
        }
    )
    ref = proxy.last_decision_ref
    assert ref is not None
    assert ref.verdict == "propose"
    assert ref.issuer == ISSUER


def test_a_resumed_approval_is_obtainable_through_the_hook() -> None:
    proxy = _proxy()
    # Decimal, as `serve` would hand it over: JSON numbers are parsed as Decimal there.
    call: dict[str, Any] = {
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "send_payment",
            "arguments": {"payee": "webshop", "amount_eur": Decimal("49.99")},
        },
    }
    proxy.handle_tools_call(call)
    propose_ref = proxy.last_decision_ref
    assert propose_ref is not None

    approval_id = int(
        proxy.conn.execute("SELECT id FROM approvals WHERE state='pending'").fetchone()[0]
    )
    # The operator approves outside the agent's channel; the agent then presents it.
    with tx(proxy.conn):
        approvals.cas_approve(proxy.conn, approval_id, "operator", now_utc())
    call["params"]["_meta"] = {"onedoor/approval_ref": approval_id}
    proxy.handle_tools_call({**call, "id": 2})
    resume_ref = proxy.last_decision_ref
    assert resume_ref is not None
    assert resume_ref.verdict == "permit"
    assert resume_ref.request_id != propose_ref.request_id


def test_serve_handles_one_call_at_a_time_so_last_decision_ref_is_safe() -> None:
    """`Proxy.last_decision_ref` is a single mutable attribute with no lock,
    which would be unsafe if two calls could be in flight together. They
    cannot: `serve` is a plain synchronous `for line in lines` loop over one
    stdin stream, and every step of handling a call -- deciding, forwarding
    to the downstream subprocess, reporting the outcome, writing the
    response -- blocks the same thread in order. Nothing in `proxy.py`
    imports threading or asyncio, and MCP-over-stdio gives the proxy exactly
    one input stream to read from, so there is no second call for one to
    race against.

    This is checked here, not merely asserted, by feeding `serve` two calls
    for two different cities in one input stream and confirming both that
    the two responses come back in order, matched to their own call, and
    that the hook ends up holding the SECOND call's own reference -- the
    shape a race would get wrong.
    """
    proxy = _proxy()
    lines = io.StringIO(
        json.dumps(
            {
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_weather", "arguments": {"city": "Amsterdam"}},
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_weather", "arguments": {"city": "Utrecht"}},
            }
        )
        + "\n"
    )
    out = io.StringIO()
    proxy.serve(lines, out)

    responses = [json.loads(line) for line in out.getvalue().splitlines()]
    assert len(responses) == 2
    assert responses[0]["id"] == 1
    assert "Amsterdam" in responses[0]["result"]["content"][0]["text"]
    assert responses[1]["id"] == 2
    assert "Utrecht" in responses[1]["result"]["content"][0]["text"]

    final_ref = proxy.last_decision_ref
    assert final_ref is not None
    row = proxy.conn.execute(
        "SELECT request_id FROM actions_audit WHERE kind='exec_intent' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert str(final_ref.request_id) == row["request_id"]
