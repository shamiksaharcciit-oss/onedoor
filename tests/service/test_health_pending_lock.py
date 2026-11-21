"""`/v1/health` reads `state.pending` without holding `state.lock` -- unlike
every other endpoint, which takes the lock around each `state.conn` use.

This calls the real `/v1/health` endpoint function directly (pulled off the
app's own route table, not through the ASGI/threadpool layer) and races it
against a writer thread that holds `state.lock` with an open (later rolled
back) transaction on `state.conn`, inserting a row `state.pending` would
count. `rebuild_module.pending` -- what `state.pending` actually calls -- is
wrapped so it signals the writer and then pauses briefly right before running
its real query: long enough for the writer to open its transaction, so the
query (locked or not, depending on whether `health()` is fixed) runs exactly
while that transaction is open. Before the fix, `health()` has already
released `state.lock` by the time this runs, so the writer races in freely
and the dirty, never-committed row is visible; after it, the read is still
inside `health()`'s own lock block, so the writer cannot even acquire the
lock until `health()` is done, and the query only ever sees the post-rollback
state.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from onedoor.guardrail import rebuild as rebuild_module
from onedoor.service.app import create_app
from onedoor.store.db import tx

ROOT = Path(__file__).parent.parent.parent

_PRE_QUERY_SECONDS = 0.1
_HOLD_SECONDS = 0.4


def _health_endpoint(app: Any) -> Any:
    for route in app.routes:
        if getattr(route, "path", None) == "/v1/health":
            return route.endpoint
    raise AssertionError("no /v1/health route found on this app")


def test_health_does_not_dirty_read_another_requests_open_transaction() -> None:
    app = create_app(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=str(ROOT / "config" / "policies.yaml"),
    )
    state = app.state.engine
    health = _health_endpoint(app)

    ready = threading.Event()
    original_pending = rebuild_module.pending

    def patched_pending(conn: Any) -> list[int]:
        ready.set()
        time.sleep(_PRE_QUERY_SECONDS)  # gives the writer time to open its transaction
        return original_pending(conn)

    def writer() -> None:
        ready.wait(timeout=5)
        try:
            with state.lock:
                with tx(state.conn):
                    state.conn.execute(
                        "INSERT INTO actions_audit "
                        "(request_id, kind, action_type, source, params_json, decision, "
                        "reason_code, nominal_tier, effective_tier, created_at) "
                        "VALUES ('dirty-read-probe', 'exec_intent', 'demo.toggle', 'llm', "
                        "'{}', 'executed', 'ok', 0, 0, '2026-01-01T00:00:00+00:00')"
                    )
                    time.sleep(_HOLD_SECONDS)
                    raise RuntimeError("deliberate rollback -- this row must never really exist")
        except RuntimeError:
            pass  # the rollback above is the point; nothing to report

    rebuild_module.pending = patched_pending
    t = threading.Thread(target=writer)
    try:
        t.start()
        result = health()
    finally:
        rebuild_module.pending = original_pending
        t.join(timeout=5)

    assert result["pending_intents"] == 0, (
        f"/v1/health saw the writer's uncommitted (and rolled-back) exec_intent row: {result}"
    )
