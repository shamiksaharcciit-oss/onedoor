"""The MCP proxy exposes the decision reference of the last decision it acted
on, via `Proxy.last_decision_ref` -- a documented hook, since the proxy speaks
MCP's own wire format on both sides and cannot embed the reference inside a
downstream tool's own JSON-RPC response without conflating two different
messages.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from onedoor.mcp.proxy import Proxy

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
    propose_ref = proxy.last_decision_ref
    assert propose_ref is not None

    approval_id = int(
        proxy.conn.execute("SELECT id FROM approvals WHERE state='pending'").fetchone()[0]
    )
    proxy.handle_approve({"id": 2, "params": {"approval_id": approval_id}})
    resume_ref = proxy.last_decision_ref
    assert resume_ref is not None
    assert resume_ref.verdict == "permit"
    assert resume_ref.request_id != propose_ref.request_id
