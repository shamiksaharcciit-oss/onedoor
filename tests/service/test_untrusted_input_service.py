"""The service's own `/v1/decide` carries `untrusted`/`untrusted_matched` the
same way the library does."""

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
                        "action_type": "messages.send",
                        "tier": 2,
                        "dry_run": False,
                        "compensating_command": "messages.retract",
                        "bounds": {"strict_params": False},
                        "untrusted_params": {"deny": ["command"], "hold": ["recipient"]},
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


def test_a_deny_listed_marked_path_is_denied_over_the_service(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={
            "action_type": "messages.send",
            "params": {"command": "x"},
            "untrusted": ["command"],
        },
        headers=_h("dkey"),
    )
    body = r.json()
    assert body["decision"] == "denied"
    assert body["reason"] == "untrusted_input"
    assert body["untrusted_matched"] == ["command"]


def test_a_hold_listed_marked_path_is_proposed_over_the_service(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={
            "action_type": "messages.send",
            "params": {"recipient": "x"},
            "untrusted": ["recipient"],
        },
        headers=_h("dkey"),
    )
    body = r.json()
    assert body["decision"] == "proposed"
    assert body["reason"] == "untrusted_input"
    assert body["untrusted_matched"] == ["recipient"]


def test_no_untrusted_field_decides_identically_to_0_10_x_over_the_service(
    client: TestClient,
) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "messages.send", "params": {"recipient": "x"}},
        headers=_h("dkey"),
    )
    body = r.json()
    assert body["decision"] == "permitted"
    assert body["untrusted_matched"] == []
