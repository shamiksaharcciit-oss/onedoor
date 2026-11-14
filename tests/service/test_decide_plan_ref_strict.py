"""`/v1/decide` takes `plan_ref` as a plain integer
only, matching what the MCP proxy's own `isinstance(x, int) and not
isinstance(x, bool)` check already enforces -- pydantic's default lax
`int` coercion would otherwise accept `true`/`false` (bool is an `int`
subclass) and a numeric string like `"1"`, both of which the report's
own evidence showed being silently treated as plan 1.
"""

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
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"), policies=str(ROOT / "config" / "policies.yaml")
    )
    return TestClient(app)


def _h() -> dict[str, str]:
    return {"Authorization": "Bearer dkey"}


def test_a_real_integer_plan_ref_is_accepted(client: TestClient) -> None:
    r = client.post(
        "/v1/decide",
        json={"action_type": "money.transfer", "params": {"amount_eur": 5}, "plan_ref": 999999},
        headers=_h(),
    )
    assert r.status_code == 200  # absent/unknown plan_ref evaluates as absent, not an error


@pytest.mark.parametrize("bad_plan_ref", [True, False, "1", 1.0])
def test_a_non_integer_plan_ref_is_refused_with_422(
    client: TestClient, bad_plan_ref: object
) -> None:
    r = client.post(
        "/v1/decide",
        json={
            "action_type": "money.transfer",
            "params": {"amount_eur": 5},
            "plan_ref": bad_plan_ref,
        },
        headers=_h(),
    )
    assert r.status_code == 422
