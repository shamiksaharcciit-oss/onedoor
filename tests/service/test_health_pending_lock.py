"""`/v1/health` reads `state.pending` without holding `state.lock` -- unlike
every other endpoint, which takes the lock around every `state.conn` use.

This reproduces exactly the statement itself (`len(state.pending)`, the real
code `health()` runs): one thread holds `state.lock` with an open (later
rolled back) transaction on `state.conn`, inserting a row `pending()` would
count, for a short fixed hold -- never waiting on the reader, so there is no
circular wait between this test's own threads. The other thread reads
`state.pending` the same way `health()` does. Before the fix (reading
unlocked), the dirty, never-committed row is visible; after it (reading under
`state.lock`, as `health()` now does), the read blocks until the writer's
transaction ends and only ever sees a state consistent with some actual
commit or rollback, never one mid-flight.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from onedoor.service.app import EngineState
from onedoor.store.db import tx

ROOT = Path(__file__).parent.parent.parent

_HOLD_SECONDS = 0.3


def _run_writer(state: EngineState, ready: threading.Event) -> threading.Thread:
    """Holds state.lock with an open, later-rolled-back transaction for a
    short fixed duration -- long enough for the reader to race it, but never
    waiting on the reader itself, so the two threads cannot deadlock."""

    def writer() -> None:
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
                    ready.set()
                    time.sleep(_HOLD_SECONDS)
                    raise RuntimeError("deliberate rollback -- this row must never really exist")
        except RuntimeError:
            pass  # the rollback above is the point; nothing to report

    t = threading.Thread(target=writer)
    t.start()
    return t


def test_pending_property_does_not_dirty_read_another_threads_open_transaction() -> None:
    state = EngineState(
        db_path=tempfile.mktemp(suffix=".db"),
        policies=ROOT / "config" / "policies.yaml",
    )
    ready = threading.Event()
    t = _run_writer(state, ready)
    ready.wait(timeout=5)
    try:
        # The fixed statement `health()` now runs: `len(state.pending)`, under
        # `state.lock` -- must block until the writer's transaction ends, so it
        # only ever sees the post-rollback, empty state.
        with state.lock:
            count = len(state.pending)
    finally:
        t.join(timeout=5)

    assert count == 0, (
        "state.pending saw the writer's uncommitted (and rolled-back) exec_intent row"
    )
    assert state.pending == []  # the row genuinely never existed: the writer rolled back
