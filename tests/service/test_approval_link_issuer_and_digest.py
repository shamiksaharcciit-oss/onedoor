"""A link's claims bind the issuing deployment and the
approval's own request digest -- a validly signed token (same key, same
signature) naming a different deployment, or an approval id that reused
a different request since, is refused regardless.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import approval_link, approvals, policy_loader
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.service.app import create_app
from onedoor.store.clock import now_utc

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
PAY = "demo.link_issuer_digest"
ISSUER = "test-deployment"


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
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _propose(client: TestClient, *, amount: int = 5) -> int:
    r = client.post(
        "/v1/decide",
        json={"action_type": PAY, "params": {"amount_eur": amount}},
        headers=_h("dkey"),
    )
    return int(r.json()["approval_id"])


def _link(approval_id: int, *, issuer: str, request_digest: str) -> str:
    return approval_link.issue(
        approval_id=approval_id,
        action="approve",
        recipient="ops@example.test",
        now=now_utc(),
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer=issuer,
        request_digest=request_digest,
    )


def _real_digest(amount: int = 5) -> str:
    return approvals.resume_digest(PAY, {"amount_eur": amount})


def test_a_link_with_the_right_issuer_and_digest_is_accepted(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _link(approval_id, issuer=ISSUER, request_digest=_real_digest())
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_a_token_claiming_a_different_issuer_is_refused(client: TestClient) -> None:
    """Same signing key, same signature, same real request digest -- only
    the claimed issuer differs, as it would for a token replayed from a
    different deployment's restored backup sharing a signing key."""
    approval_id = _propose(client)
    token = _link(approval_id, issuer="a-different-deployment", request_digest=_real_digest())
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 409
    assert r.json()["detail"] == "link can't be used"

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["state"] == "pending"


def test_a_token_claiming_a_stale_digest_is_refused(client: TestClient) -> None:
    """The real issuer, but a digest for a different request than the one
    this approval id currently names -- as it would be for an approval id
    reused for a different request after a restore."""
    approval_id = _propose(client)
    stale_digest = _real_digest(amount=999)  # not what this approval actually names
    token = _link(approval_id, issuer=ISSUER, request_digest=stale_digest)
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 409
    assert r.json()["detail"] == "link can't be used"

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["state"] == "pending"


def test_the_real_notify_path_issues_a_token_that_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through the actual propose -> notify -> by-link path,
    not a hand-built token: the issuer and digest the service itself
    computes must be the ones its own by-link route then accepts."""
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    from onedoor.guardrail.models import ApprovalNotify

    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
        notify_config=NotifyConfig(
            approval_link_base_url="https://onedoor.example/links",
            approval_link_signing_keys=KEYS,
            approval_link_signing_key_id="k1",
            approval_link_issuer=ISSUER,
        ),
        send_email=lambda to, subject, body: sent.append((to, subject, body)),
    )
    engine = app.state.engine  # type: ignore[attr-defined]
    policy_loader.upsert(
        engine.conn,
        Policy(
            action_type=PAY,
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
            approval_notify=ApprovalNotify(channel="email", recipient="ops@example.test"),
        ),
    )
    client = TestClient(app)
    client.post(
        "/v1/decide", json={"action_type": PAY, "params": {"amount_eur": 5}}, headers=_h("dkey")
    )
    _to, _subject, body = sent[0]
    approve_line = next(line for line in body.splitlines() if line.startswith("Approve:"))
    token = approve_line.split("/links/", 1)[1]
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
