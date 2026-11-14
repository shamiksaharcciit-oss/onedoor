"""The gateway gives a session via `_meta["onedoor/session_id"]`, or via the
mapping file's own `session: per_connection`, without relying on the caller."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from onedoor.mcp.proxy import Proxy

FIXTURES = Path(__file__).parent / "fixtures"
DOWNSTREAM = f'"{sys.executable}" -m tests.mcp.fixtures.mismatched_demo_server'


def _policies(tmp_path: Path) -> Path:
    path = tmp_path / "policies.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "policies": [
                    {
                        "action_type": "mcp.get_weather",
                        "tier": 0,
                        "sequence": {"tag_as": "untrusted_content"},
                    },
                    {
                        "action_type": "mcp.send_payment",
                        "tier": 2,
                        "dry_run": False,
                        "compensating_command": "mcp.reverse_payment",
                        "bounds": {"strict_params": False},
                        "sequence": {
                            "rules": [
                                {
                                    "after_tag": "untrusted_content",
                                    "within_seconds": 3600,
                                    "effect": "hold",
                                }
                            ]
                        },
                    },
                    {"action_type": "mcp.reverse_payment", "tier": 3},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _proxy(tmp_path: Path, *, mapping: str = "mismatched_mapping.yaml") -> Proxy:
    return Proxy(
        DOWNSTREAM,
        _policies(tmp_path),
        str(tmp_path / "proxy.db"),
        mapping=FIXTURES / mapping,
    )


def _call(tool: str, arguments: dict[str, Any], *, session_id: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"name": tool, "arguments": arguments}
    if session_id is not None:
        params["_meta"] = {"onedoor/session_id": session_id}
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}


def _serve_one(proxy: Proxy, msg: dict[str, Any]) -> dict[str, Any]:
    out = io.StringIO()
    proxy.serve(io.StringIO(json.dumps(msg) + "\n"), out)
    return dict(json.loads(out.getvalue()))


def _text(reply: dict[str, Any]) -> str:
    return str(reply["result"]["content"][0]["text"])


def test_a_meta_session_id_ties_a_tagged_read_to_a_later_held_send(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path)
    r1 = _serve_one(proxy, _call("check_weather", {"location": "x"}, session_id="s1"))
    assert r1["result"]["isError"] is False
    r2 = _serve_one(
        proxy,
        _call("wire_transfer", {"to": "acct-1", "amount": {"value": 10}}, session_id="s1"),
    )
    assert r2["result"]["isError"] is True
    assert (
        "sequence_rule" in _text(r2)
        or "proposed" in _text(r2).lower()
        or "waiting" in _text(r2).lower()
    )


def test_a_different_meta_session_id_is_not_held(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path)
    _serve_one(proxy, _call("check_weather", {"location": "x"}, session_id="s-a"))
    r2 = _serve_one(
        proxy,
        _call("wire_transfer", {"to": "acct-1", "amount": {"value": 10}}, session_id="s-b"),
    )
    assert r2["result"]["isError"] is False


def test_no_session_id_at_all_is_inert_for_a_tag_only_policy(tmp_path: Path) -> None:
    """`check_weather`'s own policy carries `sequence.tag_as` but no `rules`
    -- so the check itself has nothing to evaluate, whatever tier the action
    runs at -- a missing session is inert for it either way, the same as
    before this feature existed."""
    proxy = _proxy(tmp_path)
    r1 = _serve_one(proxy, _call("check_weather", {"location": "x"}))
    assert r1["result"]["isError"] is False


def test_no_session_id_against_a_policy_with_rules_is_held_through_the_gateway(
    tmp_path: Path,
) -> None:
    """`wire_transfer`'s own policy declares `sequence.rules` (non-empty) --
    a caller must not be able to avoid it just by sending no session at all
    (through the gateway, no `_meta`, and the mapping's default `session:
    none`): held, not forwarded."""
    proxy = _proxy(tmp_path)
    r2 = _serve_one(proxy, _call("wire_transfer", {"to": "acct-1", "amount": {"value": 10}}))
    assert r2["result"]["isError"] is True
    assert "sequence_no_session" in _text(r2)


def test_session_optional_exempts_a_mapped_action_through_the_gateway(tmp_path: Path) -> None:
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
                        "sequence": {
                            "session_optional": True,
                            "rules": [
                                {
                                    "after_tag": "untrusted_content",
                                    "within_seconds": 3600,
                                    "effect": "hold",
                                }
                            ],
                        },
                    },
                    {"action_type": "mcp.reverse_payment", "tier": 3},
                ]
            }
        ),
        encoding="utf-8",
    )
    proxy = Proxy(
        DOWNSTREAM, path, str(tmp_path / "proxy.db"), mapping=FIXTURES / "mismatched_mapping.yaml"
    )
    r2 = _serve_one(proxy, _call("wire_transfer", {"to": "acct-1", "amount": {"value": 10}}))
    assert r2["result"]["isError"] is False


def test_session_per_connection_ties_two_calls_with_no_meta_at_all(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path, mapping="mismatched_mapping_per_connection.yaml")
    r1 = _serve_one(proxy, _call("check_weather", {"location": "x"}))
    assert r1["result"]["isError"] is False
    r2 = _serve_one(proxy, _call("wire_transfer", {"to": "acct-1", "amount": {"value": 10}}))
    assert r2["result"]["isError"] is True


def test_a_tier_0_read_through_the_gateway_is_forwarded_with_no_report_result_call(
    tmp_path: Path,
) -> None:
    """`mcp.get_weather`'s own policy here is tier 0 (OBSERVE): the gateway
    forwards the call and returns the downstream result directly -- there
    is no intent to settle, so `report_result` must never be called for it
    (CHANGELOG, 0.11's own Fixed entry for the gap this round found)."""
    proxy = _proxy(tmp_path)
    with patch("onedoor.mcp.proxy.report_result") as mock_report_result:
        reply = _serve_one(proxy, _call("check_weather", {"location": "x"}))
    assert reply["result"]["isError"] is False
    mock_report_result.assert_not_called()


def test_a_tier_0_mapped_action_is_itself_held_by_a_matching_sequence_rule(
    tmp_path: Path,
) -> None:
    """`check_weather`'s own policy here is tier 0 (OBSERVE), and itself
    declares a `sequence.rules` entry -- the gateway must hold it exactly as
    it would a higher-tier action, not forward it: a nominal tier-0 action
    used to return before any sequence rule was ever consulted at all."""
    path = tmp_path / "policies.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "policies": [
                    {
                        "action_type": "mcp.get_weather",
                        "tier": 0,
                        "sequence": {"tag_as": "untrusted_content"},
                    },
                    {
                        "action_type": "mcp.set_thermostat",
                        "tier": 0,
                        "bounds": {"strict_params": False},
                        "sequence": {
                            "rules": [
                                {
                                    "after_tag": "untrusted_content",
                                    "within_seconds": 3600,
                                    "effect": "hold",
                                }
                            ]
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    proxy = Proxy(
        DOWNSTREAM, path, str(tmp_path / "proxy.db"), mapping=FIXTURES / "mismatched_mapping.yaml"
    )
    r1 = _serve_one(proxy, _call("check_weather", {"location": "x"}, session_id="s1"))
    assert r1["result"]["isError"] is False
    r2 = _serve_one(proxy, _call("adjust_temp", {"settings": {"target_c": 20}}, session_id="s1"))
    assert r2["result"]["isError"] is True
    assert "sequence_rule" in _text(r2)


def test_session_per_connection_is_its_own_session_from_a_second_proxy_instance(
    tmp_path: Path,
) -> None:
    """Two separate `Proxy` instances are two separate stdio connections --
    `per_connection` must not leak a tag from one into the other."""
    proxy_a = _proxy(tmp_path, mapping="mismatched_mapping_per_connection.yaml")
    _serve_one(proxy_a, _call("check_weather", {"location": "x"}))
    proxy_b = _proxy(tmp_path, mapping="mismatched_mapping_per_connection.yaml")
    r2 = _serve_one(proxy_b, _call("wire_transfer", {"to": "acct-1", "amount": {"value": 10}}))
    assert r2["result"]["isError"] is False
