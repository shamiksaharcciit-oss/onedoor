"""The gateway resolves `_meta["onedoor/untrusted"]` (a tool-argument path)
to the onedoor param name the mapping already maps it onto, before the
`ActionRequest` is ever built."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from onedoor.mcp.proxy import Proxy

ROOT = Path(__file__).parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
DOWNSTREAM = f'"{sys.executable}" -m tests.mcp.fixtures.mismatched_demo_server'


def _policies(tmp_path: Path) -> Path:
    path = tmp_path / "policies.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "policies": [
                    {
                        "action_type": "mcp.send_payment",
                        "tier": 2,
                        "dry_run": False,
                        "compensating_command": "mcp.reverse_payment",
                        "bounds": {"strict_params": False},
                        "untrusted_params": {"deny": ["payee"]},
                    },
                    {"action_type": "mcp.reverse_payment", "tier": 3},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _proxy(tmp_path: Path) -> Proxy:
    return Proxy(
        DOWNSTREAM,
        _policies(tmp_path),
        str(tmp_path / "proxy.db"),
        mapping=FIXTURES / "mismatched_mapping.yaml",
    )


def _call(
    tool: str, arguments: dict[str, Any], *, untrusted: list[str] | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {"name": tool, "arguments": arguments}
    if untrusted is not None:
        params["_meta"] = {"onedoor/untrusted": untrusted}
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}


def _serve_one(proxy: Proxy, msg: dict[str, Any]) -> dict[str, Any]:
    out = io.StringIO()
    proxy.serve(io.StringIO(json.dumps(msg) + "\n"), out)
    return dict(json.loads(out.getvalue()))


def _text(reply: dict[str, Any]) -> str:
    return str(reply["result"]["content"][0]["text"])


def test_a_marked_tool_argument_path_resolves_through_the_mapping_and_is_denied(
    tmp_path: Path,
) -> None:
    proxy = _proxy(tmp_path)
    reply = _serve_one(
        proxy,
        _call(
            "wire_transfer",
            {"to": "acct-1", "amount": {"value": 10}},
            untrusted=["arguments.to"],
        ),
    )
    assert reply["result"]["isError"] is True
    assert "untrusted_input" in _text(reply)


def test_an_unmarked_call_forwards_normally(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path)
    reply = _serve_one(proxy, _call("wire_transfer", {"to": "acct-1", "amount": {"value": 10}}))
    assert reply["result"]["isError"] is False


def test_a_marked_path_absent_from_the_mapping_is_inert(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path)
    reply = _serve_one(
        proxy,
        _call(
            "wire_transfer",
            {"to": "acct-1", "amount": {"value": 10}},
            untrusted=["arguments.some_unrelated_field"],
        ),
    )
    assert reply["result"]["isError"] is False


def test_with_no_mapping_file_a_mark_applies_directly_to_the_params(tmp_path: Path) -> None:
    """With no mapping file at all (0.10's own default), params ARE the
    tool's own arguments, verbatim -- a mark on `arguments.<path>` must
    apply to `<path>` directly, not be silently dropped for lack of a
    mapping table to resolve it through."""
    policies_path = tmp_path / "policies.yaml"
    policies_path.write_text(
        yaml.safe_dump(
            {
                "policies": [
                    {
                        "action_type": "mcp.get_weather",
                        "tier": 1,
                        "dry_run": False,
                        "compensating_command": "mcp.noop",
                        "bounds": {"required": ["city"], "strict_params": True},
                        "untrusted_params": {"deny": ["city"]},
                    },
                    {
                        "action_type": "mcp.noop",
                        "tier": 1,
                        "dry_run": False,
                        "compensating_command": "mcp.noop",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    proxy = Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server', policies_path, str(tmp_path / "proxy.db")
    )
    reply = _serve_one(
        proxy, _call("get_weather", {"city": "Utrecht"}, untrusted=["arguments.city"])
    )
    assert reply["result"]["isError"] is True
    assert "untrusted_input" in _text(reply)


def test_a_malformed_untrusted_meta_value_refuses_the_call(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path)
    reply = _serve_one(
        proxy,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "wire_transfer",
                "arguments": {"to": "acct-1", "amount": {"value": 10}},
                "_meta": {"onedoor/untrusted": "arguments.to"},  # a string, not a list
            },
        },
    )
    assert "error" in reply
    assert reply["error"]["code"] == -32602
    assert "onedoor/untrusted" in reply["error"]["message"]


def test_a_malformed_untrusted_meta_entry_refuses_the_call(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path)
    reply = _serve_one(
        proxy,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "wire_transfer",
                "arguments": {"to": "acct-1", "amount": {"value": 10}},
                "_meta": {"onedoor/untrusted": ["arguments.to", 42]},  # a non-string entry
            },
        },
    )
    assert "error" in reply
    assert reply["error"]["code"] == -32602


def test_a_marked_tier_0_action_is_itself_denied_not_executed(tmp_path: Path) -> None:
    """`check_weather`'s own policy here is tier 0 (OBSERVE): a nominal
    tier-0 action used to return before this check ever ran, so a marked,
    denied path on a pure read executed unchecked -- it must be denied here
    exactly as any other tier's action would be."""
    path = tmp_path / "policies.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "policies": [
                    {
                        "action_type": "mcp.get_weather",
                        "tier": 0,
                        "untrusted_params": {"deny": ["city"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    proxy = Proxy(
        DOWNSTREAM, path, str(tmp_path / "proxy.db"), mapping=FIXTURES / "mismatched_mapping.yaml"
    )
    reply = _serve_one(
        proxy, _call("check_weather", {"location": "x"}, untrusted=["arguments.location"])
    )
    assert reply["result"]["isError"] is True
    assert "untrusted_input" in _text(reply)
