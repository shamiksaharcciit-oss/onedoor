"""The service's own `/v1/decide` carries `session_id`/`sequence_*` the same
way the library does."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    policies_path = tmp_path / "policies.yaml"
    policies_path.write_text(
        yaml.safe_dump(
            {
                "policies": [
                    {
                        "action_type": "demo.read",
                        "tier": 0,
                        "sequence": {"tag_as": "untrusted_content"},
                    },
                    {
                        "action_type": "messages.send",
                        "tier": 2,
                        "dry_run": False,
                        "compensating_command": "messages.retract",
                        "bounds": {"strict_params": False},
                        "sequence": {
                            "rules": [
                                {
                                    "after_tag": "untrusted_content",
                                    "within_seconds": 3600,
                                    "effect": "hold",
                                }
                            ]
                        },
                    },
                    {"action_type": "messages.retract", "tier": 3},
                ]
            }
        ),
        encoding="utf-8",
    )
    app = create_app(db_path=tempfile.mktemp(suffix=".db"), policies=str(policies_path))
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def test_a_send_after_a_tagged_read_in_the_same_session_is_held_over_the_service(
    client: TestClient,
) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.read", "params": {}, "session_id": "svc-1"},
        headers=_h("dkey"),
    )
    assert r.json()["decision"] == "executed"

    r = client.post(
        "/v1/decide",
        json={"action_type": "messages.send", "params": {}, "session_id": "svc-1"},
        headers=_h("dkey"),
    )
    body = r.json()
    assert body["decision"] == "proposed"
    assert body["reason"] == "sequence_rule"
    assert body["sequence_rule_matched"] == "after_tag:untrusted_content"
    assert body["sequence_events_considered"] == 1


def test_a_different_session_id_is_not_held_over_the_service(client: TestClient) -> None:
    client.post(
        "/v1/decide",
        json={"action_type": "demo.read", "params": {}, "session_id": "svc-a"},
        headers=_h("dkey"),
    )
    r = client.post(
        "/v1/decide",
        json={"action_type": "messages.send", "params": {}, "session_id": "svc-b"},
        headers=_h("dkey"),
    )
    body = r.json()
    assert body["decision"] == "permitted"
    assert body["sequence_rule_matched"] is None


def test_no_session_id_is_inert_for_a_tag_only_policy_over_the_service(
    client: TestClient,
) -> None:
    """`demo.read`'s own policy carries `sequence.tag_as` but no `rules` --
    there is nothing to evaluate a session against, so a missing
    `session_id` is inert for it either way."""
    r = client.post(
        "/v1/decide",
        json={"action_type": "demo.read", "params": {}},
        headers=_h("dkey"),
    )
    assert r.json()["decision"] == "executed"


def test_no_session_id_against_a_policy_with_rules_is_held_over_the_service(
    client: TestClient,
) -> None:
    """`messages.send`'s own policy declares `sequence.rules` -- a caller
    must not be able to avoid it just by sending no session at all."""
    r = client.post(
        "/v1/decide",
        json={"action_type": "messages.send", "params": {}},
        headers=_h("dkey"),
    )
    body = r.json()
    assert body["decision"] == "proposed"
    assert body["reason"] == "sequence_no_session"
