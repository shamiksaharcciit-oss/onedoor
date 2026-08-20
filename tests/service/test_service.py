"""Decision service: auth roles, decide/report over the wire, approvals, kill switch."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_auth_is_required_and_roles_split(client: TestClient) -> None:
    assert client.post("/v1/decide", json={"action_type": "demo.toggle"}).status_code == 401
    assert (
        client.post("/v1/killswitch", json={"engaged": True}, headers=_h("dkey")).status_code == 403
    )  # decide key lacks admin


def test_decide_permit_then_report(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.toggle", "params": {"target": "demo.lamp", "state": "on"}},
        headers=_h("dkey"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "permitted"
    assert body["intent_audit_id"] is not None
    rep = client.post(
        "/v1/report",
        json={"intent_audit_id": body["intent_audit_id"], "ok": True, "payload": {"done": 1}},
        headers=_h("dkey"),
    )
    assert rep.status_code == 200
    assert rep.json()["decision"] == "executed"
    # double report of the same intent is refused
    again = client.post(
        "/v1/report",
        json={"intent_audit_id": body["intent_audit_id"], "ok": True},
        headers=_h("dkey"),
    )
    assert again.status_code == 404


def test_bounds_denial_over_the_wire(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.toggle", "params": {"target": "demo.lamp", "state": "up"}},
        headers=_h("dkey"),
    )
    assert r.json()["decision"] == "denied"
    assert r.json()["reason"] == "bounds"


def test_default_deny_then_admin_approves(client: TestClient) -> None:
    r = client.post(
        "/v1/decide", json={"action_type": "demo.unlisted", "params": {"x": 1}}, headers=_h("dkey")
    )
    body = r.json()
    assert body["decision"] == "proposed" and body["reason"] == "default_deny"
    aid = body["approval_id"]

    pending = client.get("/v1/approvals", headers=_h("akey")).json()
    assert [p["id"] for p in pending] == [aid]

    ok = client.post(f"/v1/approvals/{aid}/approve", headers=_h("akey"))
    assert ok.status_code == 200
    assert ok.json()["decision"] == "permitted"  # obligation handed back for enforcement

    # decide-key cannot approve
    r2 = client.post(
        "/v1/decide", json={"action_type": "demo.unlisted", "params": {"x": 2}}, headers=_h("dkey")
    )
    assert (
        client.post(
            f"/v1/approvals/{r2.json()['approval_id']}/approve", headers=_h("dkey")
        ).status_code
        == 403
    )


def test_kill_switch_clamps_and_health_reports(client: TestClient) -> None:
    client.post("/v1/killswitch", json={"engaged": True}, headers=_h("akey"))
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.toggle", "params": {"target": "demo.lamp", "state": "on"}},
        headers=_h("dkey"),
    )
    assert r.json()["decision"] == "proposed" and r.json()["reason"] == "kill_switch"
    assert client.get("/v1/health").json()["kill_switch"] is True
