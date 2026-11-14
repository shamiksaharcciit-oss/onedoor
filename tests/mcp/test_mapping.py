"""The mapping file bridges a tool's own argument shape to onedoor's action
types and param names; a tool absent from it is denied before any decision is
made, and never reaches the downstream server."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

from onedoor.mcp.proxy import Proxy

ROOT = Path(__file__).parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
DOWNSTREAM = f'"{sys.executable}" -m tests.mcp.fixtures.mismatched_demo_server'


def _proxy(db_path: Path) -> Proxy:
    return Proxy(
        DOWNSTREAM,
        ROOT / "config" / "mcp_policies.yaml",
        str(db_path),
        mapping=FIXTURES / "mismatched_mapping.yaml",
    )


def _call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }


def _serve_one(proxy: Proxy, msg: dict[str, Any]) -> dict[str, Any]:
    out = io.StringIO()
    proxy.serve(io.StringIO(json.dumps(msg) + "\n"), out)
    return dict(json.loads(out.getvalue()))


def _text(reply: dict[str, Any]) -> str:
    return str(reply["result"]["content"][0]["text"])


def test_a_flat_arg_maps_through_a_renamed_path_and_forwards(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(proxy, _call("check_weather", {"location": "Amsterdam"}))
    assert reply["result"]["isError"] is False
    assert "Weather in Amsterdam" in _text(reply)


def test_a_nested_arg_maps_through_a_dotted_path_and_forwards(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(proxy, _call("adjust_temp", {"settings": {"target_c": 21.0}}))
    assert reply["result"]["isError"] is False
    assert "Target set to 21.0" in _text(reply)


def test_a_mapped_but_out_of_bounds_value_is_denied_by_the_existing_policy(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(proxy, _call("adjust_temp", {"settings": {"target_c": 30.0}}))
    assert reply["result"]["isError"] is True
    assert "above max 23" in _text(reply)


def test_two_nested_paths_in_one_call_map_into_the_tier_3_money_policy(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(
        proxy,
        _call("wire_transfer", {"to": "webshop", "amount": {"value": 49.99, "currency": "EUR"}}),
    )
    assert reply["result"]["isError"] is True  # tier 3: parked for approval, not an error forwarded
    assert "requires approval" in _text(reply)
    assert proxy.conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1


def test_a_tool_absent_from_the_mapping_is_denied_and_never_reaches_the_downstream(
    tmp_path: Path,
) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(proxy, _call("delete_everything", {}))
    assert reply["result"]["isError"] is True
    text = _text(reply)
    assert "not in the gateway's mapping" in text
    assert "refused" in text  # the unmapped-tool note: one consistent wording,
    # never "denied (reason: ...)" -- that phrasing belongs to a policy verdict,
    # and an unmapped tool never reaches one.
    assert "never reached" not in text  # the downstream's own tell-tale string
    assert "should never be reached" not in text
    # fails closed through the ordinary engine path, same as an unknown action
    # always has -- still audited, not a silent short-circuit.
    assert proxy.conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0


def test_an_unmapped_tool_stays_refused_even_if_a_tier_0_policy_names_its_synthetic_type(
    tmp_path: Path,
) -> None:
    """The unmapped-tool note: belt and suspenders. `mcp.unmapped.<tool>` should
    never match a policy rule at all, but if one somehow names that exact
    synthesized type at tier 0 (OBSERVE), the gateway's own guarantee -- never
    forwarded, one consistent refusal -- must hold anyway. Tier 0 is the sharpest
    case: `Decision.EXECUTED` otherwise forwards straight through with no
    reservation and no later check to catch it."""
    proxy = Proxy(
        DOWNSTREAM,
        FIXTURES / "unmapped_tier0_policy.yaml",
        str(tmp_path / "proxy.db"),
        mapping=FIXTURES / "mismatched_mapping.yaml",
    )
    reply = _serve_one(proxy, _call("delete_everything", {}))
    assert reply["result"]["isError"] is True
    text = _text(reply)
    assert text == "onedoor: 'delete_everything' refused: not in the gateway's mapping."
    assert "never reached" not in text
    assert "should never be reached" not in text
    assert proxy.conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0


def test_an_unmapped_tool_stays_refused_even_if_a_tier_3_policy_names_its_synthetic_type(
    tmp_path: Path,
) -> None:
    """Same edge case at tier 3: the answer must never say "requires approval",
    and the call must never be forwarded, whatever `decide_and_reserve` decided."""
    proxy = Proxy(
        DOWNSTREAM,
        FIXTURES / "unmapped_tier3_policy.yaml",
        str(tmp_path / "proxy.db"),
        mapping=FIXTURES / "mismatched_mapping.yaml",
    )
    reply = _serve_one(proxy, _call("delete_everything", {}))
    assert reply["result"]["isError"] is True
    text = _text(reply)
    assert text == "onedoor: 'delete_everything' refused: not in the gateway's mapping."
    assert "requires approval" not in text


def test_an_unmapped_tool_never_consumes_a_granted_approval(tmp_path: Path) -> None:
    """The deeper half of the same NOTE: a policy naming `mcp.unmapped.<tool>` at
    tier 3 still proposes an ordinary pending approval (this stays audited, like
    any other action onedoor ever decides). An operator who approves it anyway,
    not knowing it can never be forwarded, must not have that approval burned by
    the caller's retry -- `approval_ref.resolve` consumes the moment it finds a
    matching, approved row, before the gateway's own "unmapped" refusal ever
    runs. Proven here by retrying with the ref and checking the row is still
    `approved`, not `consumed`."""
    from onedoor.guardrail import approvals
    from onedoor.mcp.proxy import APPROVAL_REF_META
    from onedoor.store.clock import now_utc

    proxy = Proxy(
        DOWNSTREAM,
        FIXTURES / "unmapped_tier3_policy.yaml",
        str(tmp_path / "proxy.db"),
        mapping=FIXTURES / "mismatched_mapping.yaml",
    )
    first = _serve_one(proxy, _call("delete_everything", {}))
    assert "requires approval" not in _text(first)  # still the consistent refusal
    row = proxy.conn.execute("SELECT id, state FROM approvals").fetchone()
    assert row is not None
    assert row["state"] == "pending"
    approval_id = int(row["id"])

    approvals.cas_approve(proxy.conn, approval_id, "test-operator", now_utc())
    proxy.conn.commit()

    retry = _serve_one(
        proxy,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "delete_everything",
                "arguments": {},
                "_meta": {APPROVAL_REF_META: approval_id},
            },
        },
    )
    assert retry["result"]["isError"] is True
    text = _text(retry)
    assert text == "onedoor: 'delete_everything' refused: not in the gateway's mapping."

    state = proxy.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()[
        "state"
    ]
    assert state == "approved"  # never consumed -- the retry never reached `resolve`


def test_a_missing_required_path_is_simply_omitted_and_the_policy_denies_it_as_missing(
    tmp_path: Path,
) -> None:
    """The mapping layer never raises on a missing path -- it omits the key, and
    the engine's own `bounds.required` denies exactly as it would a plain
    pass-through call missing the same key. One fail-closed path, not two."""
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(proxy, _call("check_weather", {}))  # no "location" at all
    assert reply["result"]["isError"] is True
    assert "required" in _text(reply) or "missing" in _text(reply)


def test_tools_list_is_filtered_to_only_mapped_tools_when_the_mapping_says_so(
    tmp_path: Path,
) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    listing = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    reply = _serve_one(proxy, listing)
    names = {t["name"] for t in reply["result"]["tools"]}
    assert names == {"check_weather", "adjust_temp", "wire_transfer"}
    assert "delete_everything" not in names


def test_without_a_mapping_file_every_tool_is_implicitly_mapped_as_before(tmp_path: Path) -> None:
    """Back-compat: `mapping=None` is the default, and behaves exactly as onedoor
    0.10.x's proxy always has -- action type `mcp.<tool>`, params passed through."""
    proxy = Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        ROOT / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
    )
    reply = _serve_one(proxy, _call("get_weather", {"city": "Rotterdam"}))
    assert reply["result"]["isError"] is False
    assert "Weather in Rotterdam" in _text(reply)
