"""The proxy's own CLI surface: --mapping and --transport/--host/--port are new
this round; --transport http never defaults its host away from 127.0.0.1."""

from __future__ import annotations

from pathlib import Path

from onedoor.mcp.proxy import build_arg_parser, resolve_http_security


def _parse(*argv: str):  # type: ignore[no-untyped-def]
    return build_arg_parser().parse_args(list(argv))


def test_defaults_are_stdio_with_no_mapping() -> None:
    args = _parse("--downstream", "cmd", "--policies", "p.yaml")
    assert args.transport == "stdio"
    assert args.mapping is None
    assert args.host == "127.0.0.1"


def test_mapping_and_http_transport_parse() -> None:
    args = _parse(
        "--downstream",
        "cmd",
        "--policies",
        "p.yaml",
        "--mapping",
        "m.yaml",
        "--transport",
        "http",
        "--port",
        "9100",
    )
    assert args.mapping == Path("m.yaml")
    assert args.transport == "http"
    assert args.port == 9100


def test_an_unknown_transport_is_rejected_by_the_parser() -> None:
    import pytest

    with pytest.raises(SystemExit):
        _parse("--downstream", "cmd", "--policies", "p.yaml", "--transport", "carrier-pigeon")


def test_origin_allow_defaults_empty_and_is_repeatable() -> None:
    args = _parse("--downstream", "cmd", "--policies", "p.yaml")
    assert args.origin_allow is None
    args = _parse(
        "--downstream",
        "cmd",
        "--policies",
        "p.yaml",
        "--origin-allow",
        "http://a.example",
        "--origin-allow",
        "http://b.example",
    )
    assert args.origin_allow == ["http://a.example", "http://b.example"]


def test_token_file_defaults_none_and_parses_as_a_path() -> None:
    args = _parse("--downstream", "cmd", "--policies", "p.yaml")
    assert args.token_file is None
    args = _parse("--downstream", "cmd", "--policies", "p.yaml", "--token-file", "t.txt")
    assert args.token_file == Path("t.txt")


def test_origin_allow_without_a_token_file_is_refused_before_anything_binds(
    tmp_path: Path,
) -> None:
    import pytest

    args = _parse(
        "--downstream",
        "cmd",
        "--policies",
        "p.yaml",
        "--origin-allow",
        "http://a.example",
    )
    with pytest.raises(SystemExit, match="--token-file"):
        resolve_http_security(args)


def test_origin_allow_with_a_token_file_resolves_both(tmp_path: Path) -> None:
    token_file = tmp_path / "t.txt"
    token_file.write_text("s3cr3t-and-long-enough\n", encoding="utf-8")
    args = _parse(
        "--downstream",
        "cmd",
        "--policies",
        "p.yaml",
        "--origin-allow",
        "http://a.example",
        "--token-file",
        str(token_file),
    )
    origin_allow, token = resolve_http_security(args)
    assert origin_allow == frozenset({"http://a.example"})
    assert token == "s3cr3t-and-long-enough"


def test_no_origin_allow_resolves_an_empty_set_even_when_a_token_file_is_also_given(
    tmp_path: Path,
) -> None:
    token_file = tmp_path / "t.txt"
    token_file.write_text("unused-but-long-enough\n", encoding="utf-8")
    args = _parse("--downstream", "cmd", "--policies", "p.yaml", "--token-file", str(token_file))
    origin_allow, token = resolve_http_security(args)
    assert origin_allow == frozenset()
    assert token == "unused-but-long-enough"


# --- an empty or short token file is refused at start-up, naming it ----------------


def test_an_empty_token_file_refuses_to_start(tmp_path: Path) -> None:
    import pytest

    token_file = tmp_path / "empty.txt"
    token_file.write_text("", encoding="utf-8")
    args = _parse("--downstream", "cmd", "--policies", "p.yaml", "--token-file", str(token_file))
    with pytest.raises(SystemExit, match=str(token_file).replace("\\", "\\\\")):
        resolve_http_security(args)


def test_a_whitespace_only_token_file_refuses_to_start(tmp_path: Path) -> None:
    import pytest

    token_file = tmp_path / "blank.txt"
    token_file.write_text("   \n\n", encoding="utf-8")
    args = _parse("--downstream", "cmd", "--policies", "p.yaml", "--token-file", str(token_file))
    with pytest.raises(SystemExit):
        resolve_http_security(args)


def test_a_short_token_file_refuses_to_start(tmp_path: Path) -> None:
    import pytest

    token_file = tmp_path / "short.txt"
    token_file.write_text("too-short\n", encoding="utf-8")  # 9 chars, under the 16 minimum
    args = _parse("--downstream", "cmd", "--policies", "p.yaml", "--token-file", str(token_file))
    with pytest.raises(SystemExit, match="shorter than 16"):
        resolve_http_security(args)


def test_a_valid_length_token_file_resolves(tmp_path: Path) -> None:
    token_file = tmp_path / "ok.txt"
    token_file.write_text("exactly-sixteen!\n", encoding="utf-8")  # 17 chars after strip
    args = _parse("--downstream", "cmd", "--policies", "p.yaml", "--token-file", str(token_file))
    _, token = resolve_http_security(args)
    assert token == "exactly-sixteen!"


def test_a_valid_token_with_no_authorization_header_is_refused(tmp_path: Path) -> None:
    """A configured valid-length token still means every request needs it --
    checked again here, end to end through resolve_http_security + create_app, not only
    through create_app's own direct-token tests."""
    import sys
    from pathlib import Path as P

    from fastapi.testclient import TestClient

    from onedoor.mcp.http_transport import create_app
    from onedoor.mcp.proxy import Proxy

    token_file = tmp_path / "t.txt"
    token_file.write_text("a-perfectly-valid-token\n", encoding="utf-8")
    args = _parse("--downstream", "cmd", "--policies", "p.yaml", "--token-file", str(token_file))
    _, token = resolve_http_security(args)
    root = P(__file__).parent.parent.parent
    proxy = Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        root / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
    )
    client = TestClient(create_app(proxy, token=token))
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_weather", "arguments": {"city": "Utrecht"}},
        },
    )
    assert resp.status_code == 401
