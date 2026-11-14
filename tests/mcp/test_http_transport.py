"""The streamable-HTTP transport ("stdio and streamable HTTP")
carries exactly the behaviour stdio does -- the same `Proxy.handle_message`
decides, forwards and reports either way. Driven with FastAPI's TestClient,
never a real socket: 127.0.0.1-only is enforced in `run`, exercised in its own
test below, not by actually binding a port here."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from onedoor.mcp.http_transport import create_app, run
from onedoor.mcp.proxy import Proxy

ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    proxy = Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        ROOT / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
    )
    return TestClient(create_app(proxy))


def _call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }


def _text(body: dict[str, Any]) -> str:
    return str(body["result"]["content"][0]["text"])


def test_an_allowed_call_is_forwarded_over_http(client: TestClient) -> None:
    resp = client.post("/mcp", json=_call("get_weather", {"city": "Utrecht"}))
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["isError"] is False
    assert "Weather in Utrecht" in _text(body)


def test_a_denied_call_names_the_reason_over_http(client: TestClient) -> None:
    resp = client.post("/mcp", json=_call("set_thermostat", {"temperature": 30}))
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["isError"] is True
    assert "above max 23" in _text(body)


def test_an_unmapped_tool_is_denied_over_http(client: TestClient) -> None:
    resp = client.post("/mcp", json=_call("delete_everything", {"really": True}))
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["isError"] is True
    assert "default_deny" in _text(body)


def test_a_notification_gets_a_bare_202_and_no_body_over_http(client: TestClient) -> None:
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp.status_code == 202
    assert resp.content == b""


def test_the_kill_switch_clamps_over_http_the_same_as_stdio(tmp_path: Path) -> None:
    from onedoor.guardrail import killswitch

    proxy = Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        ROOT / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
    )
    killswitch.set_engaged(proxy.conn, True, origin="operator")
    http_client = TestClient(create_app(proxy))
    # A read stays exempt (tier clamps to OBSERVE, which still executes);
    # the actuation is denied with reason kill_switch, same as stdio.
    resp = http_client.post("/mcp", json=_call("set_thermostat", {"temperature": 20}))
    body = resp.json()
    assert body["result"]["isError"] is True
    assert "kill_switch" in _text(body)


def test_refusing_to_bind_beyond_127_0_0_1(tmp_path: Path) -> None:
    proxy = Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        ROOT / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
    )
    with pytest.raises(ValueError, match="127.0.0.1"):
        run(proxy, "0.0.0.0", 8765)


# --- the Origin / Content-Type / bearer-token fix ----------------------------------


@pytest.fixture
def proxy(tmp_path: Path) -> Proxy:
    return Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        ROOT / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
    )


def test_a_request_with_no_origin_header_still_works_with_the_default_empty_allow_list(
    proxy: Proxy,
) -> None:
    client = TestClient(create_app(proxy))
    resp = client.post("/mcp", json=_call("get_weather", {"city": "Utrecht"}))
    assert resp.status_code == 200


def test_a_request_carrying_an_origin_header_is_refused_by_the_default_empty_allow_list(
    proxy: Proxy,
) -> None:
    client = TestClient(create_app(proxy))
    resp = client.post(
        "/mcp",
        json=_call("get_weather", {"city": "Utrecht"}),
        headers={"Origin": "http://example.com"},
    )
    assert resp.status_code == 403


def test_an_allow_listed_origin_with_no_token_configured_at_all_is_still_refused(
    proxy: Proxy,
) -> None:
    """A non-empty allow-list always requires a token -- allow-listing an
    origin is not itself sufficient, since that is exactly the condition a deployment
    with no `--token-file` would otherwise leave open to a matching cross-origin page."""
    client = TestClient(create_app(proxy, origin_allow=frozenset({"http://example.com"})))
    resp = client.post(
        "/mcp",
        json=_call("get_weather", {"city": "Utrecht"}),
        headers={"Origin": "http://example.com"},
    )
    assert resp.status_code == 401


def test_an_origin_not_in_the_allow_list_is_still_refused(proxy: Proxy) -> None:
    client = TestClient(create_app(proxy, origin_allow=frozenset({"http://example.com"})))
    resp = client.post(
        "/mcp",
        json=_call("get_weather", {"city": "Utrecht"}),
        headers={"Origin": "http://evil.example"},
    )
    assert resp.status_code == 403


def test_a_non_json_content_type_is_refused_with_415(proxy: Proxy) -> None:
    client = TestClient(create_app(proxy))
    resp = client.post(
        "/mcp",
        content=json.dumps(_call("get_weather", {"city": "Utrecht"})),
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 415


def test_a_json_content_type_with_a_charset_suffix_still_works(proxy: Proxy) -> None:
    client = TestClient(create_app(proxy))
    resp = client.post(
        "/mcp",
        content=json.dumps(_call("get_weather", {"city": "Utrecht"})),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert resp.status_code == 200


def test_a_non_empty_allow_list_requires_a_token_even_with_no_origin_header(
    proxy: Proxy,
) -> None:
    client = TestClient(
        create_app(proxy, origin_allow=frozenset({"http://example.com"}), token="s3cr3t")
    )
    resp = client.post("/mcp", json=_call("get_weather", {"city": "Utrecht"}))
    assert resp.status_code == 401


def test_a_non_empty_allow_list_refuses_a_wrong_token(proxy: Proxy) -> None:
    client = TestClient(
        create_app(proxy, origin_allow=frozenset({"http://example.com"}), token="s3cr3t")
    )
    resp = client.post(
        "/mcp",
        json=_call("get_weather", {"city": "Utrecht"}),
        headers={"Origin": "http://example.com", "Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_a_non_empty_allow_list_accepts_the_right_token(proxy: Proxy) -> None:
    client = TestClient(
        create_app(proxy, origin_allow=frozenset({"http://example.com"}), token="s3cr3t")
    )
    resp = client.post(
        "/mcp",
        json=_call("get_weather", {"city": "Utrecht"}),
        headers={"Origin": "http://example.com", "Authorization": "Bearer s3cr3t"},
    )
    assert resp.status_code == 200


def test_a_configured_token_is_required_even_with_an_empty_allow_list(proxy: Proxy) -> None:
    """A token given with an empty allow-list was being silently ignored,
    so it could not protect the gateway from another process on the same machine. A
    configured token must be checked on every request, whatever the allow-list."""
    client = TestClient(create_app(proxy, token="s3cr3t"))
    resp = client.post("/mcp", json=_call("get_weather", {"city": "Utrecht"}))
    assert resp.status_code == 401


def test_a_configured_token_with_an_empty_allow_list_accepts_the_right_token(
    proxy: Proxy,
) -> None:
    client = TestClient(create_app(proxy, token="s3cr3t"))
    resp = client.post(
        "/mcp",
        json=_call("get_weather", {"city": "Utrecht"}),
        headers={"Authorization": "Bearer s3cr3t"},
    )
    assert resp.status_code == 200


def test_a_non_ascii_authorization_header_gets_a_401_not_a_crash(proxy: Proxy) -> None:
    """`hmac.compare_digest` refuses a `str` argument with any character
    outside ASCII (`TypeError`, not a mismatch) -- a header is decoded
    permissively (any byte is valid Latin-1), so a non-ASCII byte in a
    presented token must still be answered, never raised."""
    client = TestClient(create_app(proxy, token="s3cr3t-and-long-enough"))
    resp = client.post(
        "/mcp",
        json=_call("get_weather", {"city": "Utrecht"}),
        headers={"Authorization": ("Bearer café").encode()},
    )
    assert resp.status_code == 401
