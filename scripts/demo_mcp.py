"""Drive the onedoor MCP proxy end to end — an agent's-eye view.

Spawns the proxy (which spawns the toy downstream server) and speaks MCP's
stdio JSON-RPC to it, exactly as an agent host would. Shows: a permitted read,
a bounded actuation, a bounds denial, money waiting for approval, the approval
releasing it, an unknown tool default-denying, and the kill switch.

Run:  python -m scripts.demo_mcp
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent


class Client:
    def __init__(self) -> None:
        db = tempfile.mktemp(suffix=".db")
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "onedoor.mcp.proxy",
                "--downstream",
                f"{sys.executable} -m onedoor.mcp.demo_server",
                "--policies",
                str(ROOT / "config" / "mcp_policies.yaml"),
                "--db",
                db,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=ROOT,
        )
        self._id = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def call(self, tool: str, **args: object) -> str:
        resp = self.request("tools/call", {"name": tool, "arguments": args})
        content = resp["result"]["content"][0]["text"]
        flag = "ERR " if resp["result"].get("isError") else "ok  "
        return f"{flag} {content}"


def main() -> None:
    c = Client()
    c.request(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "demo-agent", "version": "0"},
        },
    )
    tools = [t["name"] for t in c.request("tools/list")["result"]["tools"]]
    print(f"downstream tools: {tools}\n")

    print("1) A read, in policy, passes through and is audited:")
    print("  ", c.call("get_weather", city="Amsterdam"))

    print("2) A bounded actuation within limits auto-executes:")
    print("  ", c.call("set_thermostat", temperature=21))

    print("3) Out of bounds: denied by the proxy, never reaches the tool:")
    print("  ", c.call("set_thermostat", temperature=30))

    print("4) Money is Tier 3 — proposed, not forwarded:")
    out = c.call("send_payment", payee="webshop", amount_eur=49.99)
    print("  ", out)
    approval_id = int(out.rsplit("approval_id=", 1)[1].split(")")[0])

    print("5) A human approves — only then is the call forwarded:")
    resp = c.request("onedoor/approve", {"approval_id": approval_id})
    print("   ok  ", resp["result"]["content"][0]["text"])

    print("6) An unknown tool default-denies to a human:")
    print("  ", c.call("delete_everything", really=True))

    print("7) Kill switch engaged — even the in-policy read now needs a human:")
    c.request("onedoor/kill", {"engaged": True})
    print("  ", c.call("get_weather", city="Utrecht"))

    print("\nOne door — installed on someone else's doorway.")


if __name__ == "__main__":
    main()
