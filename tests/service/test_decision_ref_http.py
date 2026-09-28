"""The decision reference over HTTP: `/v1/decide`, `/v1/report` and
`/v1/approvals/{id}/approve` all carry `decision_ref` once an issuer is
configured, and none of them do before it is.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.decision_digest import decision_digest
from onedoor.export import export_rows
from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent
ISSUER = "https://onedoor.example/http-deployment"


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    monkeypatch.setenv("ONEDOOR_ISSUER", ISSUER)
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
    )
    return TestClient(app)


@pytest.fixture
def client_no_issuer(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    monkeypatch.delenv("ONEDOOR_ISSUER", raising=False)
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
    )
    return TestClient(app)


def test_no_issuer_configured_omits_decision_ref_over_http(client_no_issuer: TestClient) -> None:
    r = client_no_issuer.post(
        "/v1/decide",
        json={"action_type": "demo.toggle", "params": {"target": "demo.lamp", "state": "on"}},
        headers=_h("dkey"),
    )
    assert r.status_code == 200
    assert r.json()["decision_ref"] is None


def test_decide_permit_then_report_both_carry_the_same_reference(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.toggle", "params": {"target": "demo.lamp", "state": "on"}},
        headers=_h("dkey"),
    )
    assert r.status_code == 200
    body = r.json()
    ref = body["decision_ref"]
    assert ref is not None
    assert ref["format"] == "onedoor-decision-ref/1"
    assert ref["verdict"] == "permit"
    assert ref["issuer"] == ISSUER
    assert ref["request_id"] == body["request_id"]

    rep = client.post(
        "/v1/report",
        json={"intent_audit_id": body["intent_audit_id"], "outcome": "success"},
        headers=_h("dkey"),
    )
    assert rep.status_code == 200
    # The reference to the permit is unchanged by the report -- what was
    # decided does not change when the connector's outcome is recorded.
    assert rep.json()["decision_ref"] == ref


def test_a_denial_over_http_carries_a_deny_reference(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.toggle", "params": {"target": "nope", "state": "on"}},
        headers=_h("dkey"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "denied"
    ref = body["decision_ref"]
    assert ref is not None
    assert ref["verdict"] == "deny"


def test_a_resumed_approval_over_http_names_its_own_decision(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "money.transfer", "params": {"amount_eur": 5}},
        headers=_h("dkey"),
    )
    body = r.json()
    assert body["decision"] == "proposed"
    propose_ref = body["decision_ref"]
    assert propose_ref is not None
    assert propose_ref["verdict"] == "propose"

    approval_id = client.get("/v1/approvals", headers=_h("akey")).json()[0]["id"]
    approved = client.post(f"/v1/approvals/{approval_id}/approve", headers=_h("akey"))
    assert approved.status_code == 200
    resume_ref = approved.json()["decision_ref"]
    assert resume_ref is not None
    assert resume_ref["verdict"] == "permit"
    assert resume_ref["request_id"] != propose_ref["request_id"]
    assert resume_ref["decision_digest"] != propose_ref["decision_digest"]


def test_the_wire_digest_matches_a_fresh_export(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.toggle", "params": {"target": "demo.lamp", "state": "on"}},
        headers=_h("dkey"),
    )
    body = r.json()
    ref = body["decision_ref"]
    conn = client.app.state.engine.conn  # type: ignore[attr-defined]
    exported = {int(row["id"]): row for row in export_rows(conn)}
    row = exported[body["intent_audit_id"]]
    assert decision_digest(row) == ref["decision_digest"]
