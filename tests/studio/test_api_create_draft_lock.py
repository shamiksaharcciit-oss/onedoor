"""`api_create_draft` (`POST {api.API_ROOT}/drafts`) read `state.enforcer`
via `validate.known_action_types_for` before its own `with state.lock:`
block -- unlike every other route in this file, which takes the lock around
each `state.enforcer` use.

This posts to the real route (through a real `TestClient`, so the actual
async endpoint runs) and races it against a writer thread that holds
`state.lock` with an open (later rolled back) transaction on
`state.enforcer`, inserting a policy row the read would see.
`validate.known_action_types_for` -- what the route actually calls -- is
wrapped so it signals the writer and then pauses briefly right before
running its real query: long enough for the writer to open its transaction,
so the query (locked or not, depending on whether the route is fixed) runs
exactly while that transaction is open, and the patch captures the value the
route goes on to use. Before the fix, the route had not yet taken
`state.lock` when this ran, so the writer raced in freely and the dirty,
never-committed policy was visible; after it, the read is inside
`state.lock`, so the writer cannot even acquire the lock until the read is
done, and it only ever sees the post-rollback state.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi.testclient import TestClient

from onedoor.store.db import tx
from onedoor.studio import api, server, validate

_PRE_QUERY_SECONDS = 0.1
_HOLD_SECONDS = 0.4
_DIRTY_ACTION_TYPE = "dirty-read-probe.action"


def test_api_create_draft_does_not_dirty_read_another_requests_open_transaction(
    tmp_path: Any,
) -> None:
    state = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    app = server.create_app(state)
    client = TestClient(app)

    ready = threading.Event()
    seen: list[frozenset[str]] = []
    original = validate.known_action_types_for

    def patched(conn: Any, candidate: Any) -> frozenset[str]:
        ready.set()
        time.sleep(_PRE_QUERY_SECONDS)  # gives the writer time to open its transaction
        result = original(conn, candidate)
        seen.append(result)
        return result

    def writer() -> None:
        ready.wait(timeout=5)
        try:
            with state.lock:
                with tx(state.enforcer):
                    state.enforcer.execute(
                        "INSERT INTO policies (action_type, tier, updated_at) VALUES "
                        f"('{_DIRTY_ACTION_TYPE}', 2, '2026-01-01T00:00:00+00:00')"
                    )
                    time.sleep(_HOLD_SECONDS)
                    raise RuntimeError("deliberate rollback -- this policy must never really exist")
        except RuntimeError:
            pass  # the rollback above is the point; nothing to report

    validate.known_action_types_for = patched
    t = threading.Thread(target=writer)
    try:
        t.start()
        resp = client.post(f"{api.API_ROOT}/drafts", json={"title": "x", "rules": []})
    finally:
        validate.known_action_types_for = original
        t.join(timeout=5)

    assert resp.status_code == 201
    assert len(seen) == 1
    assert _DIRTY_ACTION_TYPE not in seen[0], (
        "known_action_types_for saw the writer's uncommitted (and rolled-back) policy"
    )
