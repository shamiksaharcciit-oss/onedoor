"""A link's own claimed recipient must equal the policy's currently
configured `approval_notify.recipient`: a signing key
that leaked, or a `approval_notify.recipient` changed since a link was
issued, must not let an old or forged token still act -- its signature
alone is not enough, once an authoritative current policy exists to check
it against.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import approval_link, approvals, policy_loader
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import ApprovalNotify, Bounds, Policy, Tier
from onedoor.service.app import create_app
from onedoor.store.clock import now_utc

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
PAY = "demo.link_recipient_match"
CONFIGURED_RECIPIENT = "ops@example.test"
ISSUER = "test-deployment"
REQUEST_DIGEST = approvals.resume_digest(PAY, {})


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
    engine = app.state.engine  # type: ignore[attr-defined]
    policy_loader.upsert(
        engine.conn,
        Policy(
            action_type=PAY,
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
            approval_notify=ApprovalNotify(channel="email", recipient=CONFIGURED_RECIPIENT),
        ),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _propose(client: TestClient) -> int:
    r = client.post("/v1/decide", json={"action_type": PAY, "params": {}}, headers=_h("dkey"))
    return int(r.json()["approval_id"])


def _link(approval_id: int, recipient: str) -> str:
    return approval_link.issue(
        approval_id=approval_id,
        action="approve",
        recipient=recipient,
        now=now_utc(),
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer=ISSUER,
        request_digest=REQUEST_DIGEST,
    )


def test_a_link_matching_the_configured_recipient_is_accepted(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _link(approval_id, CONFIGURED_RECIPIENT)
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_a_link_claiming_a_different_recipient_is_refused(client: TestClient) -> None:
    """A validly signed token (same key, same signature) naming a
    recipient the policy did not configure -- a leaked key minting its own
    recipient, or a policy's recipient changed after the link was issued."""
    approval_id = _propose(client)
    token = _link(approval_id, "attacker@evil.test")
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 409
    # the reason is not in the response, only "can't be used"
    assert r.json()["detail"] == "link can't be used"

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["state"] == "pending"
