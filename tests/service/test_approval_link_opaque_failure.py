"""The design note's links section and migration 0045
already say a failed link states no reason beyond that it failed -- the
same anti-probing posture `approval_ref`/`plan_ref` already have. The GET
body and the POST's 409 detail used to name exactly which of unknown_key,
bad_signature, expired or consumed, which lets anyone enumerate key ids.
The real reason is logged, never answered.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import approval_link, approvals
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.service.app import create_app
from onedoor.store.clock import now_utc

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
ISSUER = "test-deployment"
REQUEST_DIGEST = approvals.resume_digest("money.transfer", {"amount_eur": 5})


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


def _token(approval_id: int, **kw: object) -> str:
    kw.setdefault("recipient", "ops@example.test")
    kw.setdefault("now", now_utc())
    kw.setdefault("ttl_seconds", 3600)
    kw.setdefault("signing_keys", KEYS)
    kw.setdefault("key_id", "k1")
    kw.setdefault("action", "approve")
    kw.setdefault("issuer", ISSUER)
    kw.setdefault("request_digest", REQUEST_DIGEST)
    return approval_link.issue(approval_id=approval_id, **kw)  # type: ignore[arg-type]


def test_get_with_a_malformed_token_says_only_invalid_not_why(client: TestClient) -> None:
    r = client.get("/v1/approvals/by-link/not-a-real-token")
    assert r.status_code == 200
    assert r.json() == {"valid": False}


def test_get_with_an_expired_token_says_only_invalid_not_why(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _token(approval_id, now=now_utc() - timedelta(hours=2), ttl_seconds=60)
    r = client.get(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    assert r.json() == {"valid": False}


def test_post_with_a_malformed_token_gives_only_the_opaque_reason(client: TestClient) -> None:
    r = client.post("/v1/approvals/by-link/not-a-real-token")
    assert r.status_code == 409
    assert r.json() == {"detail": "link can't be used"}


def test_post_with_an_already_used_token_gives_only_the_opaque_reason(
    client: TestClient,
) -> None:
    approval_id = _propose(client)
    token = _token(approval_id)
    client.post(f"/v1/approvals/by-link/{token}")
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 409
    assert r.json() == {"detail": "link can't be used"}


def test_the_real_reason_is_logged_even_though_not_answered(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    approval_id = _propose(client)
    token = _token(approval_id)
    client.post(f"/v1/approvals/by-link/{token}")
    with caplog.at_level(logging.INFO, logger="onedoor.service.approval_link"):
        r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 409
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("consumed" in m for m in messages), messages
