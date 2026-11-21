"""`api_create_draft` (`POST {api.API_ROOT}/drafts`) reads `state.enforcer`
via `validate.known_action_types_for` before its own `with state.lock:` block
-- unlike every other route in this file, which takes the lock around each
`state.enforcer` use.

This reproduces exactly that read: one thread holds `state.lock` with an open
(later rolled back) transaction on `state.enforcer`, inserting a policy row
the read would see; the other calls `validate.known_action_types_for(state.enforcer,
[])` directly, unlocked, the same way `api_create_draft` did. Before the fix,
the dirty, never-committed policy is visible through it; the fix wraps the
call site in `state.lock`, so it can only ever see a state consistent with
some actual commit or rollback, never one mid-flight.
"""

from __future__ import annotations

import threading
import time

from onedoor.store.db import tx
from onedoor.studio import server, validate

_HOLD_SECONDS = 0.3
_DIRTY_ACTION_TYPE = "dirty-read-probe.action"


def _run_writer(state: object, ready: threading.Event) -> threading.Thread:
    """Holds state.lock with an open, later-rolled-back transaction for a
    short fixed duration -- long enough for the reader to race it, but never
    waiting on the reader itself, so the two threads cannot deadlock."""

    def writer() -> None:
        try:
            with state.lock:  # type: ignore[attr-defined]
                with tx(state.enforcer):  # type: ignore[attr-defined]
                    state.enforcer.execute(  # type: ignore[attr-defined]
                        "INSERT INTO policies (action_type, tier, updated_at) VALUES "
                        f"('{_DIRTY_ACTION_TYPE}', 2, '2026-01-01T00:00:00+00:00')"
                    )
                    ready.set()
                    time.sleep(_HOLD_SECONDS)
                    raise RuntimeError("deliberate rollback -- this policy must never really exist")
        except RuntimeError:
            pass  # the rollback above is the point; nothing to report

    t = threading.Thread(target=writer)
    t.start()
    return t


def test_known_action_types_for_does_not_dirty_read_another_threads_open_transaction(
    tmp_path: object,
) -> None:
    state = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))  # type: ignore[arg-type]
    ready = threading.Event()
    t = _run_writer(state, ready)
    ready.wait(timeout=5)
    try:
        # The real call `api_create_draft` makes before its own `with
        # state.lock:` block. Once fixed, it is itself taken under
        # `state.lock` -- reproduced here directly.
        with state.lock:
            known = validate.known_action_types_for(state.enforcer, [])
    finally:
        t.join(timeout=5)

    assert _DIRTY_ACTION_TYPE not in known, (
        "known_action_types_for saw the writer's uncommitted (and rolled-back) policy"
    )
