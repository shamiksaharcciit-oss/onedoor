"""`OneDoorMiddleware._ref_status` reads `self._conn` directly with no lock --
unlike both call sites around `self._decide`, which take `self._lock`.

This reproduces exactly that: one thread holds `self._lock` with an open
(later rolled back) transaction on `self._conn`, inserting a row and noting
its id; the other thread calls `middleware._ref_status(that_id)` directly,
the same way `_resume_refusal` does. Before the fix, the dirty,
never-committed row -- and its `approval_ref_status` -- is visible through
it; the fix wraps the read in `self._lock`, so it can only ever see a state
consistent with some actual commit or rollback, never one mid-flight.
"""

from __future__ import annotations

import tempfile
import threading
import time
from zoneinfo import ZoneInfo

from onedoor.guardrail.executor import EngineConfig
from onedoor.integrations.langchain_middleware import OneDoorMiddleware
from onedoor.store.db import Database, tx

_HOLD_SECONDS = 0.3


def _make_middleware() -> OneDoorMiddleware:
    db = Database(tempfile.mktemp(suffix=".db"))
    db.init()
    conn = db.connect(check_same_thread=False)
    config = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=30.0, tz=ZoneInfo("UTC")
    )
    return OneDoorMiddleware(conn, config)


def _run_writer(
    middleware: OneDoorMiddleware, ready: threading.Event, row_id: list[int]
) -> threading.Thread:
    """Holds self._lock with an open, later-rolled-back transaction for a short
    fixed duration -- long enough for the reader to race it, but never waiting
    on the reader itself, so the two threads cannot deadlock."""

    def writer() -> None:
        try:
            with middleware._lock:
                with tx(middleware._conn):
                    cur = middleware._conn.execute(
                        "INSERT INTO actions_audit "
                        "(request_id, kind, action_type, source, params_json, decision, "
                        "reason_code, nominal_tier, effective_tier, created_at, "
                        "approval_ref_status) "
                        "VALUES ('dirty-read-probe', 'decision', 'demo.toggle', 'llm', "
                        "'{}', 'proposed', 'tier_confirm', 1, 1, "
                        "'2026-01-01T00:00:00+00:00', 'honored')"
                    )
                    row_id.append(cur.lastrowid)
                    ready.set()
                    time.sleep(_HOLD_SECONDS)
                    raise RuntimeError("deliberate rollback -- this row must never really exist")
        except RuntimeError:
            pass  # the rollback above is the point; nothing to report

    t = threading.Thread(target=writer)
    t.start()
    return t


def test_ref_status_does_not_dirty_read_another_threads_open_transaction() -> None:
    middleware = _make_middleware()
    ready = threading.Event()
    row_id: list[int] = []
    t = _run_writer(middleware, ready, row_id)
    ready.wait(timeout=5)
    try:
        audit_id = row_id[0]
        # The real call `_resume_refusal` makes. Once fixed, `_ref_status`
        # itself takes `self._lock` -- so this must block until the writer's
        # transaction ends, and only ever see the post-rollback state (no such
        # row at all).
        status = middleware._ref_status(audit_id)
    finally:
        t.join(timeout=5)

    assert status is None, (
        f"_ref_status saw the writer's uncommitted (and rolled-back) row: {status!r}"
    )
