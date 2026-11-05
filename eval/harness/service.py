"""Starts onedoor 0.10.2's real decision service, locally, on 127.0.0.1 only --
never on 0.0.0.0 and never on any other interface -- and gives the runner a
decide client and an admin client against it.

Loads the shipped payments pack (``onedoor/templates/payments/policies.yaml``)
and the eval's own extra policies (``eval/policies/eval_extra.yaml``) into one
database before the app starts, so every category but ``permits`` (which runs
in-process -- see ``permits.py``) uses the one running service.
"""

from __future__ import annotations

import contextlib
import os
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import uvicorn

from onedoor.guardrail import policy_loader
from onedoor.integrations.decide_client import DecideKeyClient
from onedoor.service.app import create_app
from onedoor.store.db import Database

REPO_ROOT = Path(__file__).resolve().parents[2]
PAYMENTS_PACK = REPO_ROOT / "onedoor" / "templates" / "payments" / "policies.yaml"
EVAL_EXTRA = REPO_ROOT / "eval" / "policies" / "eval_extra.yaml"

DECIDE_KEY = "eval-decide-key"
ADMIN_KEY = "eval-admin-key"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class RunningService:
    base_url: str
    db_path: str
    decide: DecideKeyClient
    admin: httpx.Client
    _server: uvicorn.Server
    _thread: threading.Thread

    def admin_set_killswitch(self, engaged: bool) -> None:
        r = self.admin.post("/v1/killswitch", json={"engaged": engaged})
        r.raise_for_status()

    def admin_approve(self, approval_id: int) -> dict:
        r = self.admin.post(f"/v1/approvals/{approval_id}/approve")
        r.raise_for_status()
        return r.json()

    def admin_deny(self, approval_id: int) -> None:
        r = self.admin.post(f"/v1/approvals/{approval_id}/deny")
        r.raise_for_status()

    def close(self) -> None:
        self.decide.close()
        self.admin.close()
        self._server.should_exit = True
        self._thread.join(timeout=5)


@contextlib.contextmanager
def start(db_path: str, *, approval_ttl_seconds: int | None = None) -> Iterator[RunningService]:
    db = Database(db_path)
    db.init()
    conn = db.connect()
    policy_loader.load_file(conn, EVAL_EXTRA)
    conn.close()

    os.environ["ONEDOOR_DECIDE_KEYS"] = DECIDE_KEY
    os.environ["ONEDOOR_ADMIN_KEYS"] = ADMIN_KEY
    if approval_ttl_seconds is not None:
        os.environ["ONEDOOR_APPROVAL_TTL"] = str(approval_ttl_seconds)
    elif "ONEDOOR_APPROVAL_TTL" in os.environ:
        del os.environ["ONEDOOR_APPROVAL_TTL"]
    port = _free_port()
    app = create_app(db_path=db_path, policies=str(PAYMENTS_PACK))
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10.0
    base_url = f"http://127.0.0.1:{port}"
    with httpx.Client() as probe:
        while time.monotonic() < deadline:
            try:
                if probe.get(f"{base_url}/v1/health", timeout=0.5).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        else:
            raise RuntimeError("service did not come up within 10s")

    decide = DecideKeyClient.connect(base_url, DECIDE_KEY)
    admin = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {ADMIN_KEY}"})
    svc = RunningService(
        base_url=base_url, db_path=db_path, decide=decide, admin=admin, _server=server, _thread=thread
    )
    try:
        yield svc
    finally:
        svc.close()
