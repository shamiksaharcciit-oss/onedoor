"""An unknown tool is denied at the proxy, in words the agent can act on, and parks nothing."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from onedoor.mcp.proxy import Proxy

ROOT = Path(__file__).parent.parent.parent


def test_an_unknown_tool_is_denied_with_a_reason_and_parks_no_approval(tmp_path: Path) -> None:
    proxy = Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        ROOT / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
    )
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "delete_everything", "arguments": {"really": True}},
    }
    out = io.StringIO()
    proxy.serve(io.StringIO(json.dumps(call) + "\n"), out)
    reply = json.loads(out.getvalue())

    text = reply["result"]["content"][0]["text"]
    assert reply["result"]["isError"] is True
    assert "denied (reason: default_deny" in text
    assert "declare" in text
    assert proxy.conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
