"""The service's own `/approve` and `/grant` answer a recorded-but-insufficient
two-person vote with `202` and `recorded`/`required` fields, never `409`.
`409` stays for an actual refusal: the
proposer, the same identity twice, expired, not pending.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import ApprovalPolicy, Bounds, Policy, Tier
from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey1,akey2")
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
    )
    engine = app.state.engine  # type: ignore[attr-defined]
    policy_loader.upsert(
        engine.conn,
        Policy(
            action_type="demo.two_person_http",
            tier=Tier.CONFIRM,
            dry_run=True,
            cost_param="amount_eur",
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
            approval=ApprovalPolicy(two_person_above_eur=Decimal("100")),
        ),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _propose(client: TestClient, *, amount: int = 150) -> int:
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.two_person_http", "params": {"amount_eur": amount}},
        headers=_h("dkey"),
    )
    return int(r.json()["approval_id"])


def test_approve_records_the_first_vote_as_202_not_409(client: TestClient) -> None:
    approval_id = _propose(client)
    r = client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey1"))
    assert r.status_code == 202
    body = r.json()
    assert body == {
        "status": "recorded",
        "approval_id": approval_id,
        "recorded": 1,
        "required": 2,
    }


def test_approve_resumes_once_a_second_different_identity_approves(client: TestClient) -> None:
    approval_id = _propose(client)
    client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey1"))
    r = client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey2"))
    assert r.status_code == 200
    assert r.json()["decision"] == "dry_run"


def test_approve_still_refuses_the_same_identity_twice_with_409(client: TestClient) -> None:
    approval_id = _propose(client)
    client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey1"))
    r = client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey1"))
    assert r.status_code == 409
    assert "already approved" in r.json()["detail"]


def test_grant_records_the_first_vote_as_202_not_409(client: TestClient) -> None:
    approval_id = _propose(client)
    r = client.post(f"/v1/approvals/{approval_id}/grant", headers=_h("akey1"))
    assert r.status_code == 202
    assert r.json() == {
        "status": "recorded",
        "approval_id": approval_id,
        "recorded": 1,
        "required": 2,
    }


def test_grant_reaches_approved_once_a_second_different_identity_grants(
    client: TestClient,
) -> None:
    approval_id = _propose(client)
    client.post(f"/v1/approvals/{approval_id}/grant", headers=_h("akey1"))
    r = client.post(f"/v1/approvals/{approval_id}/grant", headers=_h("akey2"))
    assert r.status_code == 200
    assert r.json() == {"status": "approved", "approval_id": approval_id}
    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row[0] == "approved"


def test_grant_still_refuses_the_same_identity_twice_with_409(client: TestClient) -> None:
    approval_id = _propose(client)
    client.post(f"/v1/approvals/{approval_id}/grant", headers=_h("akey1"))
    r = client.post(f"/v1/approvals/{approval_id}/grant", headers=_h("akey1"))
    assert r.status_code == 409
    assert "already approved" in r.json()["detail"]
