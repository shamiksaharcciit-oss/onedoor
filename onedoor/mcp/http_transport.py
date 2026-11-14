"""The streamable-HTTP side of the same proxy: one endpoint,
`POST /mcp`, carrying exactly the JSON-RPC messages stdio carries on stdin/stdout.
`Proxy.handle_message` is the one place either transport calls -- this module adds
no guardrail behaviour of its own, only a second way to reach it.

Deliberately scoped: a single JSON-RPC message per request, answered with a single
JSON object per response (the streamable-HTTP transport's own spec allows this --
a server MAY reply with `application/json` directly rather than opening a
server-sent-events stream, for an exchange that needs no server-initiated message
mid-call, which is exactly what this gateway's synchronous decide-forward-report
pipeline is). No `Mcp-Session-Id` negotiation, no SSE stream, no batched array of
messages in one body: this proxy's state already lives in the one `Proxy` instance
behind the endpoint, not in a per-session object this round would need to invent.
Documented as a scope boundary, not silently as full streamable-HTTP coverage.

Binds to 127.0.0.1 only -- `run` refuses any other host outright, fail closed,
rather than trust a caller-supplied value.

Cross-origin, by design, not an oversight: binding to 127.0.0.1 does
not stop a page the user's browser has open from reaching this port -- a simple
cross-origin `POST` (no preflight) carries no `Origin` restriction of its own, and
DNS rebinding defeats a host-based check the same way. The streamable-HTTP
transport's own spec requires a server to validate `Origin`, so this endpoint:

- refuses any request carrying an `Origin` header unless it is in an allow-list
  that is empty by default -- `403`. A request with no `Origin` header at all
  (the ordinary case: an MCP host library, not a browser page) is unaffected.
- refuses a `Content-Type` other than `application/json` -- `415`. This is what
  forces a browser to preflight a real cross-origin request instead of sending it
  as a simple request the server never gets to see coming.
- requires a bearer token, compared in constant time, whenever one is configured
  at all -- `401` without one or with the wrong one, regardless of the allow-list's
  own state. A token given with an empty allow-list still protects the gateway
  from another process on the same machine; checking it only when the allow-list
  is non-empty would leave that token silently unused. A non-empty allow-list
  separately requires a token to be configured in the first place
  (`resolve_http_security` refuses to start otherwise) -- allow-listing an origin
  signals a deployment that expects browser-reachable traffic, which is the
  riskier case a token is the second factor for.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from onedoor.guardrail.audit import dumps_json_value
from onedoor.mcp.proxy import Proxy


def create_app(
    proxy: Proxy, *, origin_allow: frozenset[str] = frozenset(), token: str | None = None
) -> FastAPI:
    app = FastAPI(title="onedoor MCP gateway (streamable HTTP)")

    @app.post("/mcp")
    async def handle(request: Request) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and origin not in origin_allow:
            return JSONResponse({"error": "origin not allowed"}, status_code=403)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            return JSONResponse({"error": "content-type must be application/json"}, status_code=415)
        if token is not None or origin_allow:
            # A non-empty allow-list with no token configured at all is a
            # misconfiguration `resolve_http_security` refuses to start with --
            # defended here too, fail closed, rather than trusted to never be
            # reachable through a call that builds this app directly.
            auth = request.headers.get("authorization", "")
            presented = auth[len("Bearer ") :] if auth.startswith("Bearer ") else ""
            # `hmac.compare_digest` refuses a `str` argument with any character
            # outside ASCII (TypeError, not a mismatch) -- a header is decoded
            # permissively (any byte is valid Latin-1), so a non-ASCII byte in
            # a presented token must still compare, not crash, the request.
            if token is None or not hmac.compare_digest(presented.encode(), token.encode()):
                return JSONResponse({"error": "missing or incorrect bearer token"}, status_code=401)
        http_session_id = None
        if (
            token is not None
            and proxy.mapping is not None
            and proxy.mapping.session == "per_connection"
        ):
            # Onedoor 0.11: hashed, never the bearer token itself --
            # that value is a credential, and `sequence_events.session_id` is an
            # ordinary, unencrypted database column a store backup or an
            # export could expose. This gateway supports exactly one configured
            # token, so every successful request hashes to the same session --
            # a real limitation of a single-tenant token today, not a bug in
            # the hash (see questions.md).
            http_session_id = hashlib.sha256(presented.encode()).hexdigest()
        body = await request.body()
        try:
            raw_line = body.decode("utf-8")
        except UnicodeDecodeError:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}},
                status_code=400,
            )
        try:
            msg: Any = json.loads(raw_line, parse_float=Decimal)
        except (ValueError, TypeError):
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}},
                status_code=400,
            )
        resp = proxy.handle_message(msg, raw_line=raw_line, http_session_id=http_session_id)
        if resp is None:
            # A notification or a response-only message: no body, per the
            # streamable-HTTP spec's own rule for a request carrying nothing
            # that itself expects a reply.
            return Response(status_code=202)
        return Response(content=dumps_json_value(resp), media_type="application/json")

    return app


def run(
    proxy: Proxy,
    host: str,
    port: int,
    *,
    origin_allow: frozenset[str] = frozenset(),
    token: str | None = None,
) -> None:
    if host != "127.0.0.1":
        raise ValueError(
            f"refusing to bind {host!r}: this gateway listens on 127.0.0.1 only, never beyond it"
        )
    app = create_app(proxy, origin_allow=origin_allow, token=token)
    uvicorn.run(app, host=host, port=port, log_level="warning")
