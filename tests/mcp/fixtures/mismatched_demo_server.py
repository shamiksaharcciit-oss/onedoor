"""A stand-in downstream MCP tool server whose own argument shapes deliberately
differ from onedoor's canonical param names and nest one level deep -- the
mapping file's own job is to bridge exactly this gap. No SDK, no network: a
test fixture only, spoken to over stdio by the proxy under test, the same way
onedoor/mcp/demo_server.py is."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from typing import Any

from onedoor.guardrail.audit import dumps_json_value

TOOLS = [
    {
        "name": "check_weather",
        "description": "Current weather for a place (canned).",
        "inputSchema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    },
    {
        "name": "adjust_temp",
        "description": "Set a target temperature (°C), nested under settings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "settings": {
                    "type": "object",
                    "properties": {"target_c": {"type": "number"}},
                }
            },
            "required": ["settings"],
        },
    },
    {
        "name": "wire_transfer",
        "description": "Move money (simulated); the amount is a nested object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "amount": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}, "currency": {"type": "string"}},
                },
            },
            "required": ["to", "amount"],
        },
    },
    {
        "name": "delete_everything",
        "description": "Not in any mapping, on purpose.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _tool_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "check_weather":
        return _tool_result(f"Weather in {args.get('location', '?')}: 19C, light rain.")
    if name == "adjust_temp":
        target = (args.get("settings") or {}).get("target_c")
        return _tool_result(f"Target set to {float(target):.1f}C.")
    if name == "wire_transfer":
        amount = (args.get("amount") or {}).get("value")
        # Echoes the exact arguments received, as JSON, after the human-readable
        # text -- so a test can confirm the downstream tool got the call's own
        # original shape, not just that it ran at all.
        return _tool_result(
            f"Sent EUR {float(amount):.2f} to {args.get('to', '?')} (simulated).\n"
            f"received_arguments={dumps_json_value(args)}"
        )
    if name == "delete_everything":
        return _tool_result("deleted (simulated) -- this tool should never be reached")
    return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line, parse_float=Decimal)
        mid = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            result: dict[str, Any] = {
                # Echoes whatever the host sent; this fixture has no protocol
                # version of its own to default to, and none of these tests
                # ever omit one.
                "protocolVersion": msg.get("params", {}).get("protocolVersion", ""),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "onedoor-mismatched-demo-downstream", "version": "0.1.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = msg.get("params", {})
            result = _call(params.get("name", ""), params.get("arguments", {}) or {})
        elif method == "notifications/initialized":
            continue
        else:
            sys.stdout.write(
                dumps_json_value(
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {"code": -32601, "message": "no such method"},
                    }
                )
                + "\n"
            )
            sys.stdout.flush()
            continue
        sys.stdout.write(dumps_json_value({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
