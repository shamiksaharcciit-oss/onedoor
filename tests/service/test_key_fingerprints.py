"""What the service records about a key: enough to tell keys apart, nothing of the key.

The approver of an approval and the proposer of an HTTP proposal are recorded as a keyed
fingerprint of the bearer key (HMAC under a server-side secret), never a prefix or any
other fragment of it. The secret lives outside the database, which other processes read,
and persists, so the same key keeps the same fingerprint across a restart.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onedoor.service.app import create_app

ROOT = Path(__file__).parent.parent.parent
ADMIN = "Zq-admin-secret-9f"
OTHER_ADMIN = "Vb-other-admin-7d"
DECIDE = "Wx-decide-secret-3c"


def _app(monkeypatch: pytest.MonkeyPatch, db_path: Path, secret: str | None = None) -> TestClient:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", DECIDE)
    monkeypatch.setenv("ONEDOOR_ADMIN_KEYS", f"{ADMIN},{OTHER_ADMIN}")
    if secret is None:
        monkeypatch.delenv("ONEDOOR_KEY_FINGERPRINT_SECRET", raising=False)
    else:
        monkeypatch.setenv("ONEDOOR_KEY_FINGERPRINT_SECRET", secret)
    app = create_app(db_path=str(db_path), policies=str(ROOT / "config" / "policies.yaml"))
    return TestClient(app)


def _h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _propose(client: TestClient) -> int:
    r = client.post(
        "/v1/decide",
        json={"action_type": "money.transfer", "params": {"amount_eur": 5}},
        headers=_h(DECIDE),
    )
    assert r.json()["decision"] == "proposed"
    return int(r.json()["approval_id"])


def _approvals(db_path: Path) -> dict[int, sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = {int(r["id"]): r for r in conn.execute("SELECT * FROM approvals")}
    conn.close()
    return rows


def _fragments(secret: str, n: int = 4) -> set[str]:
    return {secret[i : i + n] for i in range(len(secret) - n + 1)}


def _discloses(value: str | None, secret: str) -> bool:
    return value is not None and any(f in value for f in _fragments(secret))


def test_approve_and_deny_store_no_part_of_the_admin_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "svc.db"
    client = _app(monkeypatch, db_path)
    approved, denied = _propose(client), _propose(client)
    assert client.post(f"/v1/approvals/{approved}/approve", headers=_h(ADMIN)).status_code == 200
    assert client.post(f"/v1/approvals/{denied}/deny", headers=_h(ADMIN)).status_code == 200

    rows = _approvals(db_path)
    for approval_id in (approved, denied):
        recorded = rows[approval_id]["decided_by_session"]
        assert recorded, "the approver is still recorded"
        assert not _discloses(recorded, ADMIN), recorded


def test_the_recorded_approver_tells_keys_apart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "svc.db"
    client = _app(monkeypatch, db_path)
    first, second, third = _propose(client), _propose(client), _propose(client)
    client.post(f"/v1/approvals/{first}/deny", headers=_h(ADMIN))
    client.post(f"/v1/approvals/{second}/deny", headers=_h(ADMIN))
    client.post(f"/v1/approvals/{third}/deny", headers=_h(OTHER_ADMIN))

    rows = _approvals(db_path)
    by_first = rows[first]["decided_by_session"]
    assert rows[second]["decided_by_session"] == by_first
    assert rows[third]["decided_by_session"] != by_first
    assert not _discloses(rows[third]["decided_by_session"], OTHER_ADMIN)


def test_an_http_proposal_records_its_proposer_without_the_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "svc.db"
    client = _app(monkeypatch, db_path)
    approval_id = _propose(client)

    proposer = _approvals(db_path)[approval_id]["proposed_by"]
    assert proposer, "an HTTP proposal names the key that proposed it"
    assert not _discloses(proposer, DECIDE), proposer


def test_the_same_key_keeps_its_fingerprint_across_a_restart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "svc.db"
    before = _app(monkeypatch, db_path)
    first = _propose(before)
    before.post(f"/v1/approvals/{first}/deny", headers=_h(ADMIN))

    after = _app(monkeypatch, db_path)  # a new process on the same store
    second = _propose(after)
    after.post(f"/v1/approvals/{second}/deny", headers=_h(ADMIN))

    rows = _approvals(db_path)
    assert rows[first]["decided_by_session"] == rows[second]["decided_by_session"]
    assert rows[first]["proposed_by"] == rows[second]["proposed_by"]


def test_the_fingerprint_secret_is_not_kept_in_the_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "svc.db"
    client = _app(monkeypatch, db_path)
    _propose(client)

    secret_files = [p for p in tmp_path.iterdir() if p.name.startswith("svc.db.key-fingerprint")]
    assert len(secret_files) == 1, "the secret persists beside the store, not inside it"
    secret = secret_files[0].read_text(encoding="utf-8").strip()
    assert len(secret) >= 32
    dump = "\n".join(sqlite3.connect(db_path).iterdump())
    assert secret not in dump


def test_a_configured_secret_is_used_and_no_secret_file_is_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "svc.db"
    client = _app(monkeypatch, db_path, secret="a-configured-server-side-secret")
    approval_id = _propose(client)
    client.post(f"/v1/approvals/{approval_id}/deny", headers=_h(ADMIN))

    assert not any(p.name.startswith("svc.db.key-fingerprint") for p in tmp_path.iterdir())
    recorded = _approvals(db_path)[approval_id]["decided_by_session"]
    assert recorded and not _discloses(recorded, ADMIN)
