"""A repeated request_id reuses the pending approval
decide_and_reserve's own idempotency guard already produces -- the
/v1/decide route must not then mint and send a brand new link pair for
an approval this exact presentation did not create.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import policy_loader
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import ApprovalNotify, Bounds, Policy, Tier
from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
PAY = "demo.idempotent_notify"


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def sent_emails() -> list[tuple[str, str, str]]:
    return []


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, sent_emails: list[tuple[str, str, str]]) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
        notify_config=NotifyConfig(
            approval_link_base_url="https://onedoor.example/links",
            approval_link_signing_keys=KEYS,
            approval_link_signing_key_id="k1",
            approval_link_issuer="test-deployment",
        ),
        send_email=lambda to, subject, body: sent_emails.append((to, subject, body)),
    )
    engine = app.state.engine  # type: ignore[attr-defined]
    policy_loader.upsert(
        engine.conn,
        Policy(
            action_type=PAY,
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
            approval_notify=ApprovalNotify(channel="email", recipient="ops@example.test"),
        ),
    )
    return TestClient(app)


def test_a_repeated_request_id_sends_no_second_link_pair(
    client: TestClient, sent_emails: list[tuple[str, str, str]]
) -> None:
    request_id = str(uuid4())
    r1 = client.post(
        "/v1/decide",
        json={"action_type": PAY, "params": {}, "request_id": request_id},
        headers=_h("dkey"),
    )
    approval_id_1 = r1.json()["approval_id"]
    assert len(sent_emails) == 1

    r2 = client.post(
        "/v1/decide",
        json={"action_type": PAY, "params": {}, "request_id": request_id},
        headers=_h("dkey"),
    )
    assert r2.json()["approval_id"] == approval_id_1
    assert len(sent_emails) == 1  # still just the one pair, not a second


def test_a_different_request_id_still_sends_its_own_pair(
    client: TestClient, sent_emails: list[tuple[str, str, str]]
) -> None:
    client.post(
        "/v1/decide",
        json={"action_type": PAY, "params": {}, "request_id": str(uuid4())},
        headers=_h("dkey"),
    )
    client.post(
        "/v1/decide",
        json={"action_type": PAY, "params": {}, "request_id": str(uuid4())},
        headers=_h("dkey"),
    )
    assert len(sent_emails) == 2
