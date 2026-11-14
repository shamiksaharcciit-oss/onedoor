"""The propose path's own notify step: a
Tier-3 proposal for a policy declaring approval_notify builds and sends
the links, and records approvals.link_sent/link_channel. A policy that
does not configure one leaves both exactly as before this feature
existed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import policy_loader
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import ApprovalNotify, Bounds, Policy, Tier
from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}


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
            action_type="demo.notified",
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
            approval_notify=ApprovalNotify(channel="email", recipient="ops@example.test"),
        ),
    )
    policy_loader.upsert(
        engine.conn,
        Policy(
            action_type="demo.not_notified",
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
        ),
    )
    return TestClient(app)


def test_a_proposal_for_a_notified_policy_sends_a_link_and_records_it(
    client: TestClient, sent_emails: list[tuple[str, str, str]]
) -> None:
    r = client.post(
        "/v1/decide", json={"action_type": "demo.notified", "params": {}}, headers=_h("dkey")
    )
    approval_id = r.json()["approval_id"]
    assert approval_id is not None

    assert len(sent_emails) == 1
    to, _subject, body = sent_emails[0]
    assert to == "ops@example.test"
    assert "https://onedoor.example/links/" in body

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT link_sent, link_channel FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row[0] == 1
    assert row[1] == "email"


def test_a_proposal_for_an_unnotified_policy_decides_identically_to_before(
    client: TestClient, sent_emails: list[tuple[str, str, str]]
) -> None:
    r = client.post(
        "/v1/decide", json={"action_type": "demo.not_notified", "params": {}}, headers=_h("dkey")
    )
    approval_id = r.json()["approval_id"]
    assert approval_id is not None
    assert sent_emails == []

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT link_sent, link_channel FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row[0] == 0
    assert row[1] is None


def test_the_sent_link_can_be_presented_through_the_by_link_route(
    client: TestClient, sent_emails: list[tuple[str, str, str]]
) -> None:
    """End to end: the link the adapter actually sent is a real, usable
    token against the by-link POST route."""
    r = client.post(
        "/v1/decide", json={"action_type": "demo.notified", "params": {}}, headers=_h("dkey")
    )
    approval_id = r.json()["approval_id"]
    _to, _subject, body = sent_emails[0]
    approve_line = next(line for line in body.splitlines() if line.startswith("Approve:"))
    token = approve_line.split("/links/", 1)[1]

    act = client.post(f"/v1/approvals/by-link/{token}")
    assert act.status_code == 200
    assert act.json() == {"status": "approved", "approval_id": approval_id}
