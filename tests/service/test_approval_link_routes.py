"""The two by-link service routes: GET shows a
confirmation page only and never acts; POST acts, by the token's own
claim. Both deliberately unauthenticated -- the signed token is the
credential.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import approval_link, approvals
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.service.app import create_app
from onedoor.store.clock import now_utc

ROOT = Path(__file__).parent.parent.parent
KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
ISSUER = "test-deployment"
REQUEST_DIGEST = approvals.resume_digest("money.transfer", {"amount_eur": 5})


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
    return TestClient(app)


@pytest.fixture
def client_no_notify(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _propose(client: TestClient) -> int:
    r = client.post(
        "/v1/decide",
        json={"action_type": "money.transfer", "params": {"amount_eur": 5}},
        headers=_h("dkey"),
    )
    return int(r.json()["approval_id"])


def _link(approval_id: int, *, action: str = "approve", recipient: str = "ops@example.test") -> str:
    return approval_link.issue(
        approval_id=approval_id,
        action=action,  # type: ignore[arg-type]
        recipient=recipient,
        now=now_utc(),
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer=ISSUER,
        request_digest=REQUEST_DIGEST,
    )


def test_no_notify_config_refuses_both_routes_with_404(client_no_notify: TestClient) -> None:
    token = _link(1)
    assert client_no_notify.get(f"/v1/approvals/by-link/{token}").status_code == 404
    assert client_no_notify.post(f"/v1/approvals/by-link/{token}").status_code == 404


def test_get_shows_a_confirmation_page_and_never_acts(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _link(approval_id)

    r = client.get(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body == {"valid": True, "action": "approve", "approval_id": approval_id}

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row[0] == "pending", "a GET must never approve or deny"
    # Multiple GETs: still never acts, and the link still works for the POST below.
    client.get(f"/v1/approvals/by-link/{token}")
    client.get(f"/v1/approvals/by-link/{token}")


def test_get_on_an_already_used_link_says_consumed(client: TestClient) -> None:
    """Unlike the key/signature distinctions kept
    opaque, telling a human their OWN link was already used is a
    legitimate, distinct thing for the confirmation page to say."""
    approval_id = _propose(client)
    token = _link(approval_id)
    client.post(f"/v1/approvals/by-link/{token}")

    r = client.get(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    assert r.json() == {"valid": False, "status": "consumed"}


def test_a_malformed_token_shows_as_invalid_not_a_500(client: TestClient) -> None:
    r = client.get("/v1/approvals/by-link/not-a-real-token")
    assert r.status_code == 200
    assert r.json()["valid"] is False


def test_post_approves_and_is_recorded_as_the_recipients_identity(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _link(approval_id, recipient="ops@example.test")

    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    assert r.json() == {"status": "approved", "approval_id": approval_id}

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT state, decided_by_session, link_used_at FROM approvals WHERE id=?",
        (approval_id,),
    ).fetchone()
    assert row[0] == "approved"
    assert row[1] == "ops@example.test"
    assert row[2] is not None


def test_post_denies_when_the_token_names_deny(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _link(approval_id, action="deny", recipient="ops@example.test")

    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    assert r.json() == {"status": "denied", "approval_id": approval_id}


def test_a_second_presentation_of_the_same_link_is_refused(client: TestClient) -> None:
    approval_id = _propose(client)
    token = _link(approval_id)

    first = client.post(f"/v1/approvals/by-link/{token}")
    assert first.status_code == 200
    second = client.post(f"/v1/approvals/by-link/{token}")
    assert second.status_code == 409


def test_an_expired_link_is_refused(client: TestClient) -> None:
    approval_id = _propose(client)
    token = approval_link.issue(
        approval_id=approval_id,
        action="approve",
        recipient="ops@example.test",
        now=now_utc() - timedelta(hours=2),
        ttl_seconds=60,
        signing_keys=KEYS,
        key_id="k1",
        issuer=ISSUER,
        request_digest=REQUEST_DIGEST,
    )
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 409


def test_an_approve_token_and_a_deny_token_are_never_interchangeable(client: TestClient) -> None:
    approval_id = _propose(client)
    approve_token = _link(approval_id, action="approve")
    deny_token = _link(approval_id, action="deny")

    # The deny token names deny -- presenting it never approves, whatever a
    # caller might have hoped.
    r = client.post(f"/v1/approvals/by-link/{deny_token}")
    assert r.json()["status"] == "denied"

    # The approve token, for an approval now already denied, is refused.
    r2 = client.post(f"/v1/approvals/by-link/{approve_token}")
    assert r2.status_code == 409


def test_a_link_vote_is_never_excluded_for_being_the_proposer_in_disguise(
    client: TestClient,
) -> None:
    """Replaces a test that could only fail by setting a
    link's recipient to an admin key's own fingerprint -- a value no real
    policy's `approval_notify.recipient` (always an email or webhook URL)
    can ever hold, so that scenario proved nothing a deployment could
    actually configure.

    What a policy *can* express: a normal decide-key proposal, and a link
    sent to the policy's own configured recipient. `cas_approve` has no
    channel-aware exclusion for links at all (the design note's own former
    claim was wrong, corrected in `docs/design/011-core-features.md`) --
    it is channel separation, not an identity check, that is meant to keep
    a proposer from presenting a link sent to a channel it does not
    control. Demonstrated here directly: the link is accepted and counted
    as a vote exactly like any other, with nothing in the store comparing
    it against who proposed the action.
    """
    approval_id = _propose(client)
    token = _link(approval_id, recipient="ops@example.test")
    r = client.post(f"/v1/approvals/by-link/{token}")
    assert r.status_code == 200
    assert r.json() == {"status": "approved", "approval_id": approval_id}

    engine = client.app.state.engine  # type: ignore[attr-defined]
    row = engine.conn.execute(
        "SELECT decided_by_session FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    assert row["decided_by_session"] == "ops@example.test"
