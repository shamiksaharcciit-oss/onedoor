"""AADP -03 section 6: an action type bound to an audience is not this
proxy's to exercise -- it forwards straight to a downstream tool, so it is
never the named audience, and a PEP that does not implement presentation
MUST refuse and report not_attempted (`PermittedIntent.present_bound`'s own
docstring).

Without any way to declare `presented_audience`, that refusal branch was
unreachable through the MCP proxy: a caller with no way to supply it always
hit the engine's OWN earlier, generic mismatch denial instead (`None does
not match the declared audience`), never the specific "this proxy cannot
present it" one. `PRESENTED_AUDIENCE_META` closes that gap, the same
declaration the HTTP service's `DecideBody.presented_audience` already
accepts from its caller -- "permits presented as the service presents them",
read narrowly: the gateway now accepts the same declaration the service
does, not that it gains the ability to forward one."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

from onedoor.mcp.proxy import PRESENTED_AUDIENCE_META, Proxy

FIXTURES = Path(__file__).parent / "fixtures"
AUDIENCE = "https://audience.example/consume"


def _proxy(db_path: Path) -> Proxy:
    return Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        FIXTURES / "present_bound_policy.yaml",
        str(db_path),
    )


def _serve_one(proxy: Proxy, msg: dict[str, Any]) -> dict[str, Any]:
    out = io.StringIO()
    proxy.serve(io.StringIO(json.dumps(msg) + "\n"), out)
    return dict(json.loads(out.getvalue()))


def _call(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    params: dict[str, Any] = {"name": "bound_demo", "arguments": arguments}
    if meta is not None:
        params["_meta"] = meta
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}


def test_without_declaring_an_audience_the_engine_denies_the_mismatch_outright(
    tmp_path: Path,
) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(proxy, _call())
    assert reply["result"]["isError"] is True
    text = reply["result"]["content"][0]["text"]
    assert "denied" in text
    assert "does not match the declared audience" in text
    assert AUDIENCE in text


def test_declaring_the_matching_audience_reaches_a_permit_the_proxy_still_refuses_to_forward(
    tmp_path: Path,
) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(proxy, _call({PRESENTED_AUDIENCE_META: AUDIENCE}))
    assert reply["result"]["isError"] is True
    text = reply["result"]["content"][0]["text"]
    assert "bound to audience" in text
    assert AUDIENCE in text
    assert "not attempted" in text
    # Reported, not silently dropped: a second identical call behaves the same
    # way rather than erroring on a dangling reservation, confirming
    # report_result's own NOT_ATTEMPTED release actually ran.
    reply2 = _serve_one(proxy, _call({PRESENTED_AUDIENCE_META: AUDIENCE}))
    assert reply2["result"]["isError"] is True
    assert "bound to audience" in reply2["result"]["content"][0]["text"]


def test_a_non_string_audience_evaluates_as_absent_never_as_a_type_error(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    reply = _serve_one(proxy, _call({PRESENTED_AUDIENCE_META: 12345}))
    assert reply["result"]["isError"] is True
    assert "does not match the declared audience" in reply["result"]["content"][0]["text"]
