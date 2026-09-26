"""Decision service: auth roles, decide/report over the wire, approvals, kill switch."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import approvals
from onedoor.guardrail.models import ActionRequest, Source
from onedoor.service.app import create_app
from onedoor.store.clock import now_utc
from onedoor.store.db import tx

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
        json={
            "intent_audit_id": body["intent_audit_id"],
            "outcome": "success",
            "payload": {"done": 1},
        },
        headers=_h("dkey"),
    )
    assert rep.status_code == 200
    assert rep.json()["decision"] == "executed"
    # double report of the same intent is refused
    again = client.post(
        "/v1/report",
        json={"intent_audit_id": body["intent_audit_id"], "outcome": "success"},
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


# --- WO-D1 step 2: approval_ref over HTTP ---------------------------------------


def _approval_ref_status(client: TestClient) -> str | None:
    row = client.app.state.engine.conn.execute(  # type: ignore[attr-defined]
        "SELECT approval_ref_status FROM actions_audit ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["approval_ref_status"]


def _approved_ref(client: TestClient, params: dict[str, object]) -> int:
    """An approval already granted, sitting `approved` and unconsumed (ND-009).

    Built directly against the engine's own connection -- the admin HTTP route
    (`/v1/approvals/{id}/approve`) executes immediately and never leaves an
    `approved`-but-unconsumed row for a PEP to resume, so this is the only way to
    reach the state `approval_ref` exists to resume.
    """
    engine = client.app.state.engine  # type: ignore[attr-defined]
    now = now_utc()
    request = ActionRequest(
        request_id=uuid4(),
        action_type="money.transfer",
        params=params,  # type: ignore[arg-type]
        source=Source.LLM,
        rationale="wo-d1 step 2 fixture",
        created_at=now,
    )
    with tx(engine.conn):
        approval_id = approvals.create(
            engine.conn, request, engine.config.approval_ttl_seconds, now
        )
        approvals.cas_approve(engine.conn, approval_id, "human-1", now)
    return approval_id


def test_a_valid_approval_ref_over_http_reaches_the_engine_and_is_honored(
    client: TestClient,
) -> None:
    params = {"to": "acme-gmbh", "amount_eur": "40.00"}
    approval_id = _approved_ref(client, params)

    r = client.post(
        "/v1/decide",
        json={"action_type": "money.transfer", "params": params, "approval_ref": approval_id},
        headers=_h("dkey"),
    )
    assert r.status_code == 200
    assert r.json()["decision"] == "permitted", r.json()
    assert _approval_ref_status(client) == "honored"


def test_a_malformed_approval_ref_is_refused_in_the_engines_own_words(
    client: TestClient,
) -> None:
    """An ID no approval was ever created for: refused as `unknown`, never an error.

    The action still re-evaluates on its own merits -- money.transfer is Tier 3 with
    no approval attached, so it proposes exactly as it would with no ref at all
    (ND-009: a bad ref evaluates as absent, and never errors).
    """
    r = client.post(
        "/v1/decide",
        json={
            "action_type": "money.transfer",
            "params": {"to": "acme-gmbh", "amount_eur": "40.00"},
            "approval_ref": 999999,
        },
        headers=_h("dkey"),
    )
    assert r.status_code == 200
    assert r.json()["decision"] == "proposed"
    assert _approval_ref_status(client) == "unknown"


def test_no_approval_ref_behaves_exactly_as_today(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={
            "action_type": "money.transfer",
            "params": {"to": "acme-gmbh", "amount_eur": "40.00"},
        },
        headers=_h("dkey"),
    )
    assert r.status_code == 200
    assert r.json()["decision"] == "proposed"
    assert _approval_ref_status(client) == "absent"


# --- WO-D1 step 4: no_effect over HTTP -------------------------------------------


def test_no_effect_on_a_timeout_is_refused_over_http(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.capped", "params": {}},
        headers=_h("dkey"),
    )
    intent_audit_id = r.json()["intent_audit_id"]
    rep = client.post(
        "/v1/report",
        json={"intent_audit_id": intent_audit_id, "outcome": "timeout", "no_effect": True},
        headers=_h("dkey"),
    )
    assert rep.status_code == 400
    assert "failure" in rep.json()["detail"]


def test_no_effect_on_a_failure_never_releases_the_rate_budget_over_http(
    client: TestClient,
) -> None:
    """`demo.capped` allows 2 calls/day. A no_effect failure must not give the slot
    back, so a third call the same day still exhausts the cap (-03 §4.1)."""

    def _spend() -> int:
        r = client.post(
            "/v1/decide", json={"action_type": "demo.capped", "params": {}}, headers=_h("dkey")
        )
        return r.json()["intent_audit_id"]

    first = _spend()
    client.post(
        "/v1/report",
        json={"intent_audit_id": first, "outcome": "failure", "no_effect": True},
        headers=_h("dkey"),
    )
    second = _spend()
    assert second is not None

    third = client.post(
        "/v1/decide", json={"action_type": "demo.capped", "params": {}}, headers=_h("dkey")
    )
    assert third.json()["decision"] == "denied"
    assert third.json()["reason"] == "cap_rate", "the no_effect report must not have freed the slot"
