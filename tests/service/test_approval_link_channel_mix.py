"""A link vote and an admin-key vote are two different identity spaces that
can never be equal as strings: the link route records
`claims.recipient` (an email or webhook URL), `/approve`/`/grant` record
the admin key's own fingerprint. Before this fix, one person voting once
by link and once by admin key completed a two-person approval alone.
"""

from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import approval_link, approvals, policy_loader
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import ApprovalNotify, ApprovalPolicy, Bounds, Policy, Tier
from onedoor.service.app import create_app
from onedoor.store.clock import now_utc

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
PAY = "demo.link_key_mix"
RECIPIENT = "ops@example.test"
ISSUER = "test-deployment"
REQUEST_DIGEST = approvals.resume_digest(PAY, {"amount_eur": 150})


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey1,akey2")
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
            cost_param="amount_eur",
            approval=ApprovalPolicy(two_person_above_eur=Decimal("100")),
            approval_notify=ApprovalNotify(channel="email", recipient=RECIPIENT),
        ),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _propose(client: TestClient, *, amount: int = 150) -> int:
    r = client.post(
        "/v1/decide",
        json={"action_type": PAY, "params": {"amount_eur": amount}},
        headers=_h("dkey"),
    )
    return int(r.json()["approval_id"])


def _link(approval_id: int) -> str:
    return approval_link.issue(
        approval_id=approval_id,
        action="approve",
        recipient=RECIPIENT,
        now=now_utc(),
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer=ISSUER,
        request_digest=REQUEST_DIGEST,
    )


def test_a_link_vote_then_an_admin_key_vote_is_refused_as_a_mixed_pair(
    client: TestClient,
) -> None:
    approval_id = _propose(client)
    token = _link(approval_id)

    r1 = client.post(f"/v1/approvals/by-link/{token}")
    assert r1.status_code == 202  # matches /grant's own answer
    assert r1.json() == {
        "status": "recorded",
        "approval_id": approval_id,
        "recorded": 1,
        "required": 2,
    }

    r2 = client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey1"))
    assert r2.status_code == 409
    assert "different" in r2.json()["detail"]

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT state, approvers_json FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["state"] == "pending"
    assert len(json.loads(row["approvers_json"])) == 1


def test_an_admin_key_vote_then_a_link_vote_is_refused_as_a_mixed_pair(
    client: TestClient,
) -> None:
    approval_id = _propose(client)
    r1 = client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey1"))
    assert r1.status_code == 202

    token = _link(approval_id)
    r2 = client.post(f"/v1/approvals/by-link/{token}")
    assert r2.status_code == 409
    assert "different" in r2.json()["detail"]

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT state, link_used_at FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["state"] == "pending"
    # the link's own token verified cleanly -- the mixed-channel
    # refusal happens afterward, in cas_approve -- so both the nonce and
    # link_used_at are already spent/set despite the vote itself never
    # being recorded.
    assert row["link_used_at"] is not None
    r3 = client.post(f"/v1/approvals/by-link/{token}")
    assert r3.status_code == 409
    assert r3.json()["detail"] == "link can't be used"


def test_two_admin_key_votes_are_unaffected(client: TestClient) -> None:
    approval_id = _propose(client)
    client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey1"))
    r = client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey2"))
    assert r.status_code == 200
    assert r.json()["decision"] == "dry_run"


def test_a_link_vote_then_a_library_vote_is_refused_as_a_mixed_pair(client: TestClient) -> None:
    """A vote through `executor.resume_approval` now carries
    `channel="library"`, the same way a key vote and a link vote already
    carry their own channel -- a link vote is one recipient, one vote, and
    cannot complete a two-person approval by pairing with a DIFFERENT
    channel's vote either, library included."""
    approval_id = _propose(client)
    token = _link(approval_id)
    r1 = client.post(f"/v1/approvals/by-link/{token}")
    assert r1.status_code == 202

    engine = client.app.state.engine  # type: ignore[attr-defined]
    with pytest.raises(approvals.ApprovalError, match="different"):
        approvals.cas_approve(engine.conn, approval_id, "operator-1", now_utc(), channel="library")

    row = engine.conn.execute(
        "SELECT state, approvers_json FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["state"] == "pending"
    assert len(json.loads(row["approvers_json"])) == 1
