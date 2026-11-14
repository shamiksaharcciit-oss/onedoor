"""The signed-approval-link pages leak nothing: no referrer, no cache, no
cross-origin load, and the real token never reaches a log line -- on
success, on refusal, or on a forced crash.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import approval_link, approvals
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.service.app import create_app
from onedoor.store.clock import now_utc

ISSUER = "test-deployment"
REQUEST_DIGEST = approvals.resume_digest("money.transfer", {"amount_eur": 5})

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
        notify_config=NotifyConfig(
            approval_link_base_url="https://onedoor.example/links",
            approval_link_signing_keys=KEYS,
            approval_link_signing_key_id="k1",
            approval_link_issuer=ISSUER,
        ),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _propose(client: TestClient) -> int:
    r = client.post(
        "/v1/decide",
        json={"action_type": "money.transfer", "params": {"amount_eur": 5}},
        headers=_h("dkey"),
    )
    return int(r.json()["approval_id"])


def _token(approval_id: int, *, action: str = "approve") -> str:
    return approval_link.issue(
        approval_id=approval_id,
        action=action,  # type: ignore[arg-type]
        recipient="ops@example.test",
        now=now_utc(),
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer=ISSUER,
        request_digest=REQUEST_DIGEST,
    )


def _assert_leak_safety_headers(response: object) -> None:
    assert response.headers["Referrer-Policy"] == "no-referrer"  # type: ignore[attr-defined]
    assert response.headers["Cache-Control"] == "no-store"  # type: ignore[attr-defined]
    csp = response.headers["Content-Security-Policy"]  # type: ignore[attr-defined]
    assert "'none'" in csp


def test_the_get_route_carries_the_leak_safety_headers(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _token(approval_id)
    r = client.get(f"/v1/approvals/by-link/{token}")
    _assert_leak_safety_headers(r)


def test_the_post_route_carries_the_leak_safety_headers(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _token(approval_id)
    r = client.post(f"/v1/approvals/by-link/{token}")
    _assert_leak_safety_headers(r)


def test_an_invalid_tokens_get_still_carries_the_headers(client: TestClient) -> None:
    r = client.get("/v1/approvals/by-link/not-a-real-token")
    _assert_leak_safety_headers(r)


def test_the_access_log_never_holds_the_real_token_get(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    approval_id = _propose(client)
    token = _token(approval_id)
    with caplog.at_level(logging.INFO, logger="onedoor.service.approval_link"):
        client.get(f"/v1/approvals/by-link/{token}")
    messages = [r.getMessage() for r in caplog.records]
    assert any("<token>" in m for m in messages), messages
    assert not any(token in m for m in messages), "the real token leaked into a log line"


def test_the_access_log_never_holds_the_real_token_post(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    approval_id = _propose(client)
    token = _token(approval_id)
    with caplog.at_level(logging.INFO, logger="onedoor.service.approval_link"):
        client.post(f"/v1/approvals/by-link/{token}")
    messages = [r.getMessage() for r in caplog.records]
    assert any("<token>" in m for m in messages), messages
    assert not any(token in m for m in messages), "the real token leaked into a log line"


def test_a_forced_error_on_get_never_logs_the_real_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    approval_id = _propose(client)
    token = _token(approval_id)
    quiet_client = TestClient(client.app, raise_server_exceptions=False)
    with patch.object(approval_link, "verify", side_effect=RuntimeError("stand-in crash")):
        with caplog.at_level(logging.INFO, logger="onedoor.service.approval_link"):
            r = quiet_client.get(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 500
    _assert_leak_safety_headers(r)  # set by middleware now, not the handler's own call
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("<token>" in m and "failed" in m for m in messages), messages
    assert not any(token in m for m in messages), "the real token leaked into the error log"


def test_a_forced_error_on_post_never_logs_the_real_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    approval_id = _propose(client)
    token = _token(approval_id)
    quiet_client = TestClient(client.app, raise_server_exceptions=False)
    with patch.object(approval_link, "resolve", side_effect=RuntimeError("stand-in crash")):
        with caplog.at_level(logging.INFO, logger="onedoor.service.approval_link"):
            r = quiet_client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 500
    _assert_leak_safety_headers(r)  # set by middleware now, not the handler's own call
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("<token>" in m and "failed" in m for m in messages), messages
    assert not any(token in m for m in messages), "the real token leaked into the error log"


def test_a_409_refusal_on_post_still_carries_the_headers(client: TestClient) -> None:
    """An `HTTPException` the handler raises builds a
    fresh response that never carried the headers the handler's own
    `_set_link_page_headers(response)` call set on the now-discarded
    injected `Response` -- a second presentation of an already-used link
    is exactly this shape (409), reached without any forced crash."""
    approval_id = _propose(client)
    token = _token(approval_id)
    client.post(f"/v1/approvals/by-link/{token}")
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 409
    _assert_leak_safety_headers(r)


def test_a_routing_404_under_the_link_prefix_still_carries_the_headers(
    client: TestClient,
) -> None:
    """A path under the by-link prefix that no route matches at all --
    never reaches either handler, so neither handler's own call could
    ever have set anything here."""
    r = client.get("/v1/approvals/by-link/")
    assert r.status_code == 404
    _assert_leak_safety_headers(r)
