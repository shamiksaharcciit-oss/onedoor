"""The resume key's reuse rule, stated once over every value of `ApprovalState`:

A row is IN FLIGHT while its state is `pending`, `ratified` or `approved` AND
`expires_at` is later than now. A resume key reuses its in-flight row, and only
that. Everything else -- `denied`, `expired`, `consumed`, `executed`, or any of
the three in-flight states past its own expiry -- gets a fresh row.

Two earlier fixes in this same release each named the case they were written
for and broke a neighbour: filtering to `pending` alone missed an `approved`
row mid-resume (a second, never-granted row on the ordinary flow); filtering
to `pending` or `approved` then missed `ratified` (a combined, mandate-gated
approval resumed before the approver acts), which let a second row sit beside
the ratified one until the approver's own `cas_approve` crashed on the index.
Neither fix, nor this one, touched `approvals.sweep`'s own `pending`-only
expiry -- nothing in `onedoor/` calls it, so an in-flight row past its
`expires_at` would otherwise be reused forever (and, for `pending`/`ratified`,
never become approvable again either); `find_by_resume_key` now expires it
itself, in the caller's own transaction, on the way out.
"""

from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ApprovalState, Decision
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.clock import to_iso
from tests.conftest import FROZEN_NOW, make_request

REUSED = "reused: the resume key finds this row and acts on it again"
FRESH = "fresh: the resume key gets a new row, this one is untouched (or expired first)"

RESUME_OUTCOME: dict[ApprovalState, str] = {
    ApprovalState.PENDING: REUSED,
    ApprovalState.RATIFIED: REUSED,
    ApprovalState.APPROVED: REUSED,
    ApprovalState.DENIED: FRESH,
    ApprovalState.EXPIRED: FRESH,
    ApprovalState.EXECUTED: FRESH,
    ApprovalState.CONSUMED: FRESH,
}
"""Every `ApprovalState` member's own expected outcome, named once: the three
in-flight states (`pending`, `ratified`, `approved`), while unexpired, are the
only ones a resume key ever reuses -- everything else is a fresh row. A state
added to the enum with no entry here fails
`test_every_approval_state_has_a_traced_resume_outcome` immediately, rather
than silently landing on one side of a membership test nobody updated."""


def test_every_approval_state_has_a_traced_resume_outcome() -> None:
    assert set(RESUME_OUTCOME) == set(ApprovalState)


IN_FLIGHT = frozenset(state for state, outcome in RESUME_OUTCOME.items() if outcome == REUSED)


def _resume(
    conn: Connection,
    config: EngineConfig,
    *,
    params: dict[str, object],
    approval_ref: int | None = None,
    now=FROZEN_NOW,  # type: ignore[no-untyped-def]
):
    req = make_request("demo.confirm", params, now=now)
    if approval_ref is not None:
        req = req.model_copy(update={"approval_ref": approval_ref})
    return decide_and_reserve(
        req, conn=conn, config=config, now=now, thread_id="thread-1", tool_call_id="call-1"
    )


def _table(conn: Connection) -> list[tuple[int, str]]:
    rows = conn.execute("SELECT id, state FROM approvals ORDER BY id").fetchall()
    return [(r["id"], r["state"]) for r in rows]


def _force(conn: Connection, approval_id: int, *, state: str, expires_at: object) -> None:
    """Direct SQL, bypassing every CAS: some states (`ratified`, `executed`) and
    every expiry this file tests for aren't reachable through the ordinary API
    from a single fresh row, and the rule under test must hold for the stored
    state alone, not for however a caller might have arrived at it."""
    conn.execute(
        "UPDATE approvals SET state=?, expires_at=? WHERE id=?",
        (state, to_iso(expires_at), approval_id),
    )


@pytest.mark.parametrize("state", list(ApprovalState))
def test_a_resume_reuses_the_row_only_while_it_is_in_flight_and_unexpired(
    conn: Connection, config: EngineConfig, state: ApprovalState
) -> None:
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    _force(conn, approval_id, state=state.value, expires_at=FROZEN_NOW + timedelta(hours=1))

    second = _resume(conn, config, params={"amount": "10"})
    if state in IN_FLIGHT:
        assert second.approval_id == approval_id, (
            f"a resume while the row is {state.value} (in flight, unexpired) must reuse it"
        )
        assert _table(conn) == [(approval_id, state.value)], (
            f"a resume while the row is {state.value} must create no second row"
        )
    else:
        assert second.approval_id != approval_id, (
            f"a resume while the row is {state.value} reused a row that is not in flight"
        )
        assert _table(conn) == [(approval_id, state.value), (second.approval_id, "pending")]


@pytest.mark.parametrize("state", list(ApprovalState))
def test_a_resume_gets_a_fresh_row_when_the_found_one_has_lapsed_with_no_sweep(
    conn: Connection, config: EngineConfig, state: ApprovalState
) -> None:
    """No `sweep` call anywhere -- nothing in `onedoor/` makes one. A lapsed
    in-flight row must still yield a fresh row, and must read `expired`
    afterwards; a row already in a terminal state is untouched by the lookup,
    since it was never in the reusable set to begin with."""
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    _force(conn, approval_id, state=state.value, expires_at=FROZEN_NOW - timedelta(seconds=1))

    second = _resume(conn, config, params={"amount": "10"})
    assert second.approval_id != approval_id, (
        f"a resume after the found row ({state.value}, lapsed) reused it"
    )
    row = approvals.get(conn, approval_id)
    assert row is not None
    if state in IN_FLIGHT:
        assert row.state.value == "expired", (
            f"a lapsed in-flight row ({state.value}) must read expired after the lookup"
        )
    else:
        assert row.state.value == state.value, (
            "a row already in a terminal state must be untouched by the lookup"
        )


def test_the_ordinary_resume_leaves_exactly_one_row_at_engine_level(
    conn: Connection, config: EngineConfig
) -> None:
    """Row-counting: propose with a resume key, approve, then resume -- the
    ordinary LangGraph shape, where the interrupted node's re-execution
    decides once with no reference and once with the reference."""
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    assert _table(conn) == [(approval_id, "pending")]

    approvals.cas_approve(conn, approval_id, session_id="approver", now=FROZEN_NOW)
    assert _table(conn) == [(approval_id, "approved")]

    no_ref = _resume(conn, config, params={"amount": "10"})
    assert no_ref.decision.decision == Decision.PROPOSED
    assert no_ref.approval_id == approval_id
    assert _table(conn) == [(approval_id, "approved")], (
        "the resume's first (reference-less) pass must not propose a second approval"
    )

    with_ref = _resume(conn, config, params={"amount": "10"}, approval_ref=approval_id)
    assert isinstance(with_ref, PermittedIntent)
    assert _table(conn) == [(approval_id, "consumed")], (
        "the ordinary resume must end with exactly the one original row, consumed"
    )


def test_case_e_a_pending_row_past_its_expiry_with_no_sweep_gets_a_fresh_row(
    conn: Connection, config: EngineConfig
) -> None:
    """Case E: nothing sweeps a pending row past its expiry, so
    without the lookup's own expiry check every later resume would keep
    naming it, and the approver's own cas_approve would keep refusing it."""
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    row = approvals.get(conn, approval_id)
    assert row is not None
    later = row.expires_at + timedelta(seconds=1)

    second = _resume(conn, config, params={"amount": "10"}, now=later)
    assert second.approval_id != approval_id, "a resume after the pending row lapsed reused it"
    assert _table(conn) == [(approval_id, "expired"), (second.approval_id, "pending")]

    with pytest.raises(ApprovalError):
        approvals.cas_approve(conn, approval_id, session_id="approver", now=later)


def test_case_f_an_approved_row_past_its_expiry_with_no_sweep_gets_a_fresh_row(
    conn: Connection, config: EngineConfig
) -> None:
    """Case F: an approved row that lapses must not be reused
    forever -- at 5b7a260/f7a9333 that tool call could never be approved
    again, since the index forbade a fresh row and the reference itself is
    refused as expired by the approval_ref path."""
    first = _resume(conn, config, params={"amount": "10"})
    approval_id = first.approval_id
    approvals.cas_approve(conn, approval_id, session_id="approver", now=FROZEN_NOW)
    row = approvals.get(conn, approval_id)
    assert row is not None
    later = row.expires_at + timedelta(seconds=1)

    second = _resume(conn, config, params={"amount": "10"}, now=later)
    assert second.approval_id != approval_id, "a resume after the approved row lapsed reused it"
    assert _table(conn) == [(approval_id, "expired"), (second.approval_id, "pending")]


def test_case_g_a_combined_approval_resumed_while_ratified_reuses_it(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    """Case G, the bug this round closes: a mandate-gated
    (combined) approval the mandate authority has ratified sits in flight
    too -- a resume in that window must reuse it, not create a second row
    the approver's later cas_approve would then crash on."""
    from tests.guardrail.test_mandate_combined import ACTION, _ratify, _setup

    cfg, private = _setup(conn, config, registry)
    first = decide_and_reserve(
        make_request(ACTION),
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
        thread_id="thread-g",
        tool_call_id="call-g",
    )
    approval_id = first.approval_id
    _ratify(conn, approval_id, private, cfg.mandate_authority_public_key)
    assert _table(conn) == [(approval_id, "ratified")]

    second = decide_and_reserve(
        make_request(ACTION),
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
        thread_id="thread-g",
        tool_call_id="call-g",
    )
    assert second.approval_id == approval_id, "a resume while ratified must reuse the row"
    assert _table(conn) == [(approval_id, "ratified")], (
        "a resume while ratified must create no second row"
    )

    approvals.cas_approve(conn, approval_id, session_id="approver", now=FROZEN_NOW)
    assert _table(conn) == [(approval_id, "approved")]

    third_req = make_request(ACTION).model_copy(update={"approval_ref": approval_id})
    third = decide_and_reserve(
        third_req,
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
        thread_id="thread-g",
        tool_call_id="call-g",
    )
    assert isinstance(third, PermittedIntent)
    assert _table(conn) == [(approval_id, "consumed")]


def test_case_g_variant_the_approver_acts_before_the_resume(
    conn: Connection, config: EngineConfig, registry: ConnectorRegistry
) -> None:
    """The same window, the other order: the approver approves the ratified
    row before the node resumes at all -- the resume must still find the one
    row, now `approved`, not the `ratified` one it no longer is."""
    from tests.guardrail.test_mandate_combined import ACTION, _ratify, _setup

    cfg, private = _setup(conn, config, registry)
    first = decide_and_reserve(
        make_request(ACTION),
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
        thread_id="thread-g2",
        tool_call_id="call-g2",
    )
    approval_id = first.approval_id
    _ratify(conn, approval_id, private, cfg.mandate_authority_public_key)
    approvals.cas_approve(conn, approval_id, session_id="approver", now=FROZEN_NOW)
    assert _table(conn) == [(approval_id, "approved")]

    resumed = decide_and_reserve(
        make_request(ACTION),
        conn=conn,
        config=cfg,
        now=FROZEN_NOW,
        thread_id="thread-g2",
        tool_call_id="call-g2",
    )
    assert resumed.approval_id == approval_id
    assert _table(conn) == [(approval_id, "approved")]


def test_the_index_refuses_a_second_in_flight_row_whatever_the_firsts_in_flight_state(
    conn: Connection, config: EngineConfig
) -> None:
    """Step 7, direct: `idx_approvals_resume_key` must refuse a second
    in-flight row for one key no matter which of the three in-flight states
    the first is in, and allow a fresh pending row once the first is in a
    terminal state."""

    def _create() -> int:
        return approvals.create(
            conn,
            make_request("demo.confirm", {}),
            config.approval_ttl_seconds,
            FROZEN_NOW,
            thread_id="thread-idx",
            tool_call_id="call-idx",
        )

    first = _create()
    for state in ("pending", "ratified", "approved"):
        _force(conn, first, state=state, expires_at=FROZEN_NOW + timedelta(hours=1))
        with pytest.raises(Exception, match="UNIQUE constraint"):
            _create()

    for state in ("consumed", "denied", "expired"):
        _force(conn, first, state=state, expires_at=FROZEN_NOW + timedelta(hours=1))
        second = _create()
        assert second != first
        conn.execute("DELETE FROM approvals WHERE id=?", (second,))
