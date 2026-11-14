"""The FIRST link vote sets `link_used_at`, not every
subsequent attempt -- a link vote that only records an insufficient
(two-person) vote must still mark the link as used; a later vote that
completes the approval through a DIFFERENT channel must not move that
timestamp.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import onedoor.service.app as app_module
from onedoor.guardrail import approval_link, approvals, policy_loader
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import ApprovalNotify, ApprovalPolicy, Bounds, Policy, Tier
from onedoor.service.app import create_app
from onedoor.store.clock import now_utc

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
PAY = "demo.first_vote_used_at"
RECIPIENT = "ops@example.test"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey1")
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
        notify_config=NotifyConfig(
            approval_link_base_url="https://onedoor.example/links",
            approval_link_signing_keys=KEYS,
            approval_link_signing_key_id="k1",
            approval_link_issuer="test-deployment",
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
            cost_param="amount_eur",
            approval=ApprovalPolicy(two_person_above_eur=Decimal("100")),
            approval_notify=ApprovalNotify(channel="email", recipient=RECIPIENT),
        ),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _propose(client: TestClient) -> int:
    r = client.post(
        "/v1/decide", json={"action_type": PAY, "params": {"amount_eur": 150}}, headers=_h("dkey")
    )
    return int(r.json()["approval_id"])


def _link(approval_id: int, action: str) -> str:
    return approval_link.issue(
        approval_id=approval_id,
        action=action,  # type: ignore[arg-type]
        recipient=RECIPIENT,
        now=now_utc(),
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer="test-deployment",
        request_digest=approvals.resume_digest(PAY, {"amount_eur": 150}),
    )


def test_the_insufficient_link_vote_sets_used_at_and_a_later_link_vote_leaves_it(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both votes stay in the link channel (a mixed link/
    admin-key pair is refused, so completing a two-person approval across channels
    is not a shape a real deployment could present): the approve link
    records an insufficient first vote and sets link_used_at; the
    separate deny link -- a different nonce, same approval -- then
    denies it, at a distinctly later server time (forced here, so an
    unguarded second write would be observably different, not just
    coincidentally identical), and must not move that timestamp."""
    approval_id = _propose(client)
    approve_token = _link(approval_id, "approve")

    t1 = now_utc()
    monkeypatch.setattr(app_module, "now_utc", lambda: t1)
    r1 = client.post(f"/v1/approvals/by-link/{approve_token}")
    assert r1.status_code == 202  # matches /grant's own answer
    assert r1.json()["status"] == "recorded"

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row1 = engine.conn.execute(
        "SELECT link_used_at FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row1["link_used_at"] is not None
    first_value = row1["link_used_at"]

    deny_token = _link(approval_id, "deny")
    t2 = t1 + timedelta(minutes=5)
    monkeypatch.setattr(app_module, "now_utc", lambda: t2)
    r2 = client.post(f"/v1/approvals/by-link/{deny_token}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "denied"

    row2 = engine.conn.execute(
        "SELECT link_used_at FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row2["link_used_at"] == first_value
