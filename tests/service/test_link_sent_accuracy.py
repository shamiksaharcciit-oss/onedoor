"""`link_sent` recorded 1 after `notify()` whatever it
actually did -- the design note's own receipt wording promises a link
"built and dispatched", not merely attempted. It must stay 0 (its
default) for a missing sender or a sender that raised, and only become 1
once a sender actually ran without raising.
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


def _client_with_policy(
    monkeypatch: pytest.MonkeyPatch, action_type: str, *, send_email: object = None
) -> TestClient:
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
        send_email=send_email,  # type: ignore[arg-type]
    )
    engine = app.state.engine  # type: ignore[attr-defined]
    policy_loader.upsert(
        engine.conn,
        Policy(
            action_type=action_type,
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
            approval_notify=ApprovalNotify(channel="email", recipient="ops@example.test"),
        ),
    )
    return TestClient(app)


def _propose(client: TestClient, action_type: str) -> int:
    r = client.post(
        "/v1/decide", json={"action_type": action_type, "params": {}}, headers=_h("dkey")
    )
    return int(r.json()["approval_id"])


def test_link_sent_is_1_once_a_sender_actually_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str, str]] = []
    client = _client_with_policy(
        monkeypatch,
        "demo.link_sent_ok",
        send_email=lambda to, subject, body: sent.append((to, subject, body)),
    )
    approval_id = _propose(client, "demo.link_sent_ok")
    assert len(sent) == 1

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT link_sent, link_channel FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["link_sent"] == 1
    assert row["link_channel"] == "email"


def test_link_sent_stays_0_with_no_sender_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client_with_policy(monkeypatch, "demo.link_sent_no_sender", send_email=None)
    approval_id = _propose(client, "demo.link_sent_no_sender")

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT link_sent, link_channel FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["link_sent"] == 0
    assert row["link_channel"] is None


def test_link_sent_stays_0_when_the_sender_itself_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_sender(to: str, subject: str, body: str) -> None:
        raise ConnectionError("stand-in failure")

    client = _client_with_policy(monkeypatch, "demo.link_sent_raises", send_email=failing_sender)
    approval_id = _propose(client, "demo.link_sent_raises")

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT link_sent, link_channel FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["link_sent"] == 0
    assert row["link_channel"] is None
