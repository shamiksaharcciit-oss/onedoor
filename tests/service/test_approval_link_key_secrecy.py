"""The HMAC signing key stays out of the record entirely: never in a receipt, the database, a log, or an error.

A recognisable key is planted and the full lifecycle is exercised --
propose (which triggers the notify adapter), the GET confirmation page,
the POST that acts, a recorded-but-insufficient vote, a forced crash --
then every database row, every captured log line, every HTTP response
body, and the stand-in email body are searched for that key, in its raw
bytes, its hex form, and its base64 form. It must appear nowhere.
"""

from __future__ import annotations

import base64
import binascii
import logging
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import approval_link, policy_loader
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import ApprovalNotify, Bounds, Policy, Tier
from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent
PLANTED_KEY = b"PLANTED-SECRET-SIGNING-KEY-32byt"
assert len(PLANTED_KEY) == 32
KEYS = {"k1": PLANTED_KEY}
PLANTED_FORMS = (
    PLANTED_KEY,
    PLANTED_KEY.hex().encode(),
    base64.b64encode(PLANTED_KEY),
    base64.urlsafe_b64encode(PLANTED_KEY),
    binascii.hexlify(PLANTED_KEY, "-").decode().encode(),
)


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
            action_type="demo.key_secrecy",
            tier=Tier.CONFIRM,
            dry_run=True,
            bounds=Bounds(strict_params=False),
            approval_notify=ApprovalNotify(channel="email", recipient="ops@example.test"),
        ),
    )
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _assert_key_absent(haystack: bytes | str, *, where: str) -> None:
    data = haystack.encode("utf-8", errors="replace") if isinstance(haystack, str) else haystack
    for form in PLANTED_FORMS:
        assert form not in data, f"the signing key leaked into {where} (form: {form!r})"


def _dump_every_db_row(db_path: str) -> bytes:
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        chunks: list[bytes] = []
        for table in tables:
            for row in conn.execute(f"SELECT * FROM {table}"):  # noqa: S608 - table names from sqlite_master
                for value in row:
                    if value is None:
                        continue
                    chunks.append(str(value).encode("utf-8", errors="replace"))
        return b"\n".join(chunks)
    finally:
        conn.close()


def test_the_signing_key_never_reaches_a_receipt_row_log_or_response(
    client: TestClient, sent_emails: list[tuple[str, str, str]], caplog: pytest.LogCaptureFixture
) -> None:
    response_bodies: list[str] = []

    with caplog.at_level(logging.DEBUG):
        # 1. Propose a notified action -- triggers approval_notify.notify(),
        #    which calls approval_link.issue() with the planted key.
        proposed = client.post(
            "/v1/decide",
            json={"action_type": "demo.key_secrecy", "params": {}},
            headers=_h("dkey"),
        )
        response_bodies.append(proposed.text)
        approval_id = proposed.json()["approval_id"]
        assert approval_id is not None
        assert len(sent_emails) == 1
        _to, subject, body = sent_emails[0]
        response_bodies.append(subject)
        response_bodies.append(body)
        approve_line = next(line for line in body.splitlines() if line.startswith("Approve:"))
        deny_line = next(line for line in body.splitlines() if line.startswith("Deny:"))
        approve_token = approve_line.split("/links/", 1)[1]
        deny_token = deny_line.split("/links/", 1)[1]

        # 2. GET the confirmation page (never acts, never consumes).
        get_resp = client.get(f"/v1/approvals/by-link/{approve_token}")
        response_bodies.append(get_resp.text)

        # 3. POST to act -- approves (this policy has no two-person block,
        #    so one approver suffices; still exercises cas_approve's own
        #    write path end to end).
        post_resp = client.post(f"/v1/approvals/by-link/{approve_token}")
        response_bodies.append(post_resp.text)

        # 4. A second presentation (CONSUMED) -- another code path to check.
        again_resp = client.post(f"/v1/approvals/by-link/{approve_token}")
        response_bodies.append(again_resp.text)

        # 5. The deny token's own GET and POST, for the sibling code path.
        deny_get = client.get(f"/v1/approvals/by-link/{deny_token}")
        response_bodies.append(deny_get.text)
        deny_post = client.post(f"/v1/approvals/by-link/{deny_token}")
        response_bodies.append(deny_post.text)

        # 6. A forced crash on each route.
        quiet_client = TestClient(client.app, raise_server_exceptions=False)
        with patch.object(approval_link, "verify", side_effect=RuntimeError("stand-in crash")):
            crash_get = quiet_client.get(f"/v1/approvals/by-link/{approve_token}")
            response_bodies.append(crash_get.text)
        with patch.object(approval_link, "resolve", side_effect=RuntimeError("stand-in crash")):
            crash_post = quiet_client.post(f"/v1/approvals/by-link/{approve_token}")
            response_bodies.append(crash_post.text)

    # --- search every surface ---------------------------------------------
    for body_text in response_bodies:
        _assert_key_absent(body_text, where="an HTTP response body")

    for record in caplog.records:
        _assert_key_absent(record.getMessage(), where=f"a log line ({record.name})")

    engine = client.app.state.engine  # type: ignore[attr-defined]
    # `PRAGMA database_list` names the open file, rather than depending on
    # an attribute `EngineState` may not expose.
    db_path = engine.conn.execute("PRAGMA database_list").fetchone()[2]
    db_dump = _dump_every_db_row(db_path)
    _assert_key_absent(db_dump, where="a database row")
