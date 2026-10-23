"""The decide-key HTTP client: idempotent by reusing one request_id across
retries (never a second reservation), and honest about a dropped call.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from onedoor.integrations.decide_client import DecideKeyClient, NotAttempted
from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def real_client(monkeypatch: pytest.MonkeyPatch) -> DecideKeyClient:
    """A `DecideKeyClient` wired to a real, in-process `create_app()` instance.

    `TestClient` bridges the async ASGI app to a synchronous `.post()` the same
    shape `httpx.Client` has -- `DecideKeyClient` only ever calls `.post()` and
    `.raise_for_status()`/`.json()` on the response, never anything specific to
    one HTTP library, so it does not care which one actually answered.
    """
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", "akey")
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
    )
    test_client = TestClient(app, headers={"Authorization": "Bearer dkey"})
    return DecideKeyClient(client=test_client)  # type: ignore[arg-type]


def _engine_conn(client: DecideKeyClient):  # type: ignore[no-untyped-def]
    app = client.client.app  # type: ignore[attr-defined]
    return app.state.engine.conn


RETRY_1 = "8e2a1c44-0000-4000-8000-00000000abcd"
CALL_A = "8e2a1c44-0000-4000-8000-0000000000aa"
CALL_B = "8e2a1c44-0000-4000-8000-0000000000bb"


def test_a_repeated_idempotency_key_returns_the_first_decision_and_reserves_nothing_twice(
    real_client: DecideKeyClient,
) -> None:
    body = {"action_type": "demo.capped", "params": {}}
    first = real_client.decide(body, request_id=RETRY_1)
    second = real_client.decide(body, request_id=RETRY_1)

    assert first["decision"] == "permitted"
    # A live permit answers "permitted" with `intent_audit_id` set
    # (decide_and_reserve returned a fresh PermittedIntent). A replayed call
    # reconstructs an ActionResult from the stored row instead -- its `decision`
    # already reads EXECUTED at intent time (invariant 9), and the wire reply
    # carries the same row id under `audit_id`, not `intent_audit_id`. Both are
    # pre-existing label/field differences this test does not change; what it
    # asserts is that the row id underneath is the SAME permit, not a new one.
    assert second["decision"] in ("permitted", "executed")
    second_permit_id = second["intent_audit_id"] or second["audit_id"]
    assert first["intent_audit_id"] == second_permit_id

    conn = _engine_conn(real_client)
    row = conn.execute("SELECT count FROM cap_counters WHERE action_type='demo.capped'").fetchone()
    assert row["count"] == 1, "a repeated idempotency key must not reserve the rate cap twice"

    audit_count = conn.execute(
        "SELECT COUNT(*) AS n FROM actions_audit WHERE request_id=?", (RETRY_1,)
    ).fetchone()["n"]
    assert audit_count == 1, "a repeated idempotency key must produce exactly one audit row"


def test_two_different_keys_each_reserve_their_own_call(real_client: DecideKeyClient) -> None:
    """The negative control: this is dedup by key, not a cap that silently stopped
    counting -- two genuinely different calls both reserve."""
    body = {"action_type": "demo.capped", "params": {}}
    first = real_client.decide(body, request_id=CALL_A)
    second = real_client.decide(body, request_id=CALL_B)

    assert first["decision"] == "permitted"
    assert second["decision"] == "permitted"
    assert first["intent_audit_id"] != second["intent_audit_id"]

    conn = _engine_conn(real_client)
    row = conn.execute("SELECT count FROM cap_counters WHERE action_type='demo.capped'").fetchone()
    assert row["count"] == 2


def _always_drops(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection dropped", request=request)


def test_a_call_past_its_deadline_takes_no_action_and_reports_not_attempted() -> None:
    dropped_client = httpx.Client(
        transport=httpx.MockTransport(_always_drops),
        base_url="http://unreachable",
        headers={"Authorization": "Bearer dkey"},
    )
    slept: list[float] = []
    client = DecideKeyClient(
        client=dropped_client,
        max_retries=5,
        backoff_base_seconds=0.01,
        backoff_cap_seconds=0.02,
        total_deadline_seconds=0.05,
        _sleep=slept.append,
    )

    with pytest.raises(NotAttempted) as excinfo:
        client.decide({"action_type": "demo.capped", "params": {}}, request_id="never-arrives")

    assert excinfo.value.reason == "the decision was not received"
    assert excinfo.value.request_id == "never-arrives"
    assert slept, "at least one backoff must have been attempted before giving up"


def test_an_answered_refusal_is_not_retried() -> None:
    """A 403 IS an answer -- the wrong role, say -- and must propagate immediately,
    never be mistaken for a dropped call and retried."""
    calls: list[int] = []

    def _refuse(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403, json={"detail": "key lacks decide role"})

    client = DecideKeyClient(
        client=httpx.Client(
            transport=httpx.MockTransport(_refuse),
            base_url="http://test",
            headers={"Authorization": "Bearer wrong-key"},
        ),
        max_retries=5,
        total_deadline_seconds=5.0,
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.decide({"action_type": "demo.capped", "params": {}}, request_id="refused")

    assert len(calls) == 1, "an answered 403 must not be retried as if it were dropped"
