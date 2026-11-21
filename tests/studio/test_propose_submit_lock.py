"""`propose_submit` (`POST /propose`) reads `state.enforcer` via
`validate.known_action_types_for` before calling `derive()` -- unlike every
other route in this file, which takes `state.lock` around each
`state.enforcer` use.

This posts to the real `/propose` route (through a real `TestClient`, so the
actual async endpoint runs) and races it against a writer thread that holds
`state.lock` with an open (later rolled back) transaction on
`state.enforcer`, inserting a policy row the read would see.
`validate.known_action_types_for` -- what `propose_submit` actually calls --
is wrapped so it signals the writer and then pauses briefly right before
running its real query: long enough for the writer to open its transaction,
so the query (locked or not, depending on whether `propose_submit` is fixed)
runs exactly while that transaction is open. The patch also captures the
value `propose_submit` goes on to use, since the shipped `FixtureProposer`
accepts but never consults `known_action_types` -- nothing about it is
otherwise observable in the response. Before the fix, `propose_submit` has
already released `state.lock` (it never took it) by the time this runs, so
the writer races in freely and the dirty, never-committed policy is visible;
after it, the read is inside `state.lock`, so the writer cannot even acquire
the lock until the read is done, and it only ever sees the post-rollback
state.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi.testclient import TestClient

from onedoor.store.db import tx
from onedoor.studio import proposer as studio_proposer
from onedoor.studio import server, validate

_PRE_QUERY_SECONDS = 0.1
_HOLD_SECONDS = 0.4
_DIRTY_ACTION_TYPE = "dirty-read-probe.action"


def test_propose_submit_does_not_dirty_read_another_requests_open_transaction(
    tmp_path: Any,
) -> None:
    state = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    state.proposer = studio_proposer.FixtureProposer()
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
        # Not followed: a successful POST redirects to the new draft's own
        # detail page, which makes its own, separately-locked call to the
        # same patched function (`draft_detail` -> `canvas.build`) -- fine on
        # its own, but it would add a second, irrelevant entry to `seen`.
        resp = client.post(
            "/propose", data={"description": "a refund for the customer"}, follow_redirects=False
        )
    finally:
        validate.known_action_types_for = original
        t.join(timeout=5)

    assert resp.status_code == 303
    assert len(seen) == 1
    assert _DIRTY_ACTION_TYPE not in seen[0], (
        "known_action_types_for saw the writer's uncommitted (and rolled-back) policy"
    )
