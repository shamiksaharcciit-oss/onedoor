"""A deliberately tiny downstream MCP tool server (stdio, newline-delimited JSON-RPC).

Three tools with three risk profiles, so the proxy has something honest to govern:
a read (`get_weather`), a bounded actuation (`set_thermostat`), and a money move
(`send_payment`). No SDK, no network — this exists so `scripts/demo_mcp.py` can
demonstrate the proxy end to end with zero external dependencies.
"""

from __future__ import annotations

import json
import sys
from typing import Any

TOOLS = [
    {
        "name": "get_weather",
        "description": "Current weather for a city (canned).",
        "inputSchema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
    {
        "name": "set_thermostat",
        "description": "Set the thermostat target temperature (°C).",
        "inputSchema": {
            "type": "object",
            "properties": {"temperature": {"type": "number"}},
            "required": ["temperature"],
        },
    },
    {
        "name": "send_payment",
        "description": "Send a payment to a payee (simulated).",
        "inputSchema": {
            "type": "object",
            "properties": {"payee": {"type": "string"}, "amount_eur": {"type": "number"}},
            "required": ["payee", "amount_eur"],
        },
    },
]

_STATE = {"thermostat": 19.0}


def _tool_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "get_weather":
        return _tool_result(f"Weather in {args.get('city', '?')}: 19°C, light rain (of course).")
    if name == "set_thermostat":
        _STATE["thermostat"] = float(args["temperature"])
        return _tool_result(f"Thermostat set to {_STATE['thermostat']:.1f}°C.")
    if name == "send_payment":
        return _tool_result(
            f"Sent €{float(args['amount_eur']):.2f} to {args.get('payee', '?')} (simulated)."
        )
    return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        mid = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "niyam-demo-downstream", "version": "0.2.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = msg.get("params", {})
            result = _call(params.get("name", ""), params.get("arguments", {}) or {})
        elif method == "notifications/initialized":
            continue  # notification: no response
        else:
            sys.stdout.write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "no such method"}}
                )
                + "\n"
            )
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
