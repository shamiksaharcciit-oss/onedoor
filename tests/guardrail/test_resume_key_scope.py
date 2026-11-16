"""The resume-by-key lookup (`find_by_resume_key`) is scoped to the caller's
own principal, so a second caller holding the first caller's own
``(thread_id, tool_call_id)`` learns nothing and can consume nothing of the
first caller's own approval — whatever principal either side did or did not
authenticate.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionResult, CheckId, Decision
from onedoor.store.db import _MIGRATIONS_DIR, run_migrations, tx
from onedoor.store.db import connect as db_connect
from tests.conftest import FROZEN_NOW, _seed_test_policies, make_request

THREAD = "shared-thread-1"
CALL = "shared-call-1"
PARAMS_A = {"amount": "10"}
PARAMS_B = {"amount": "99"}


def _resume(
    conn: Connection,
    config: EngineConfig,
    *,
    principal: str | None,
    params: dict[str, object],
    now=FROZEN_NOW,
):
    req = make_request("demo.confirm", params, now=now)
    return decide_and_reserve(
        req,
        conn=conn,
        config=config,
        now=now,
        principal=principal,
        thread_id=THREAD,
        tool_call_id=CALL,
    )


def _present_ref(
    conn: Connection,
    config: EngineConfig,
    *,
    approval_id: int,
    principal: str | None,
    params: dict[str, object],
    now=FROZEN_NOW,
):
    req = make_request("demo.confirm", params, now=now).model_copy(
        update={"approval_ref": approval_id}
    )
    return decide_and_reserve(req, conn=conn, config=config, now=now, principal=principal)


def _approval_state(conn: Connection, approval_id: int) -> str:
    row = conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return str(row["state"])


def _mismatch_flag(conn: Connection, audit_id: int) -> object:
    row = conn.execute(
        "SELECT resume_key_principal_mismatch FROM actions_audit WHERE id=?", (audit_id,)
    ).fetchone()
    return row["resume_key_principal_mismatch"]


# --- The fix's own test: the former no-principal consumption case is now refused ---


def test_a_second_principal_can_no_longer_consume_a_first_proposals_approval(
    conn: Connection, config: EngineConfig
) -> None:
    """The exact case that was carried out before the fix: a first proposal
    naming no principal, approved, then resumed by a second caller sharing
    the first caller's own resume key. The second caller now gets a fresh,
    unrelated proposal, and the first approval stays `approved`.
    """
    first = _resume(conn, config, principal=None, params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None
    with tx(conn):
        approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)
    assert _approval_state(conn, approval_id) == "approved"

    second = _resume(conn, config, principal="principal-b", params=PARAMS_A)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
    assert second.approval_id != approval_id, "the id must not be handed to a different principal"
    assert _mismatch_flag(conn, second.audit_id) == 1

    # Even presenting the id directly (however it might have been learned) is refused.
    third = _present_ref(
        conn, config, approval_id=approval_id, principal="principal-b", params=PARAMS_A
    )
    assert not isinstance(third, PermittedIntent)
    assert _approval_state(conn, approval_id) == "approved", "must still not be consumed"


# --- Every state the severity investigation covered, now scoped: same request shape ---


@pytest.mark.parametrize("state", ["pending", "approved", "expired"])
@pytest.mark.parametrize(
    ("a_principal", "b_principal"),
    [
        (None, "principal-b"),
        ("principal-a", None),
        ("principal-a", "principal-b"),
    ],
)
def test_a_mismatched_principal_learns_and_consumes_nothing_for_any_state(
    conn: Connection,
    config: EngineConfig,
    state: str,
    a_principal: str | None,
    b_principal: str | None,
) -> None:
    first = _resume(conn, config, principal=a_principal, params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None

    now = FROZEN_NOW
    if state == "approved":
        with tx(conn):
            approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)
    elif state == "expired":
        now = FROZEN_NOW + timedelta(seconds=config.approval_ttl_seconds + 1)

    second = _resume(conn, config, principal=b_principal, params=PARAMS_A, now=now)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
    assert second.approval_id != approval_id, "no id must be handed to a mismatched principal"

    if state == "expired":
        # Indistinguishable from a key nobody had ever used: no row to mismatch against.
        assert _mismatch_flag(conn, second.audit_id) is None
        assert _approval_state(conn, approval_id) == "expired"
    else:
        assert _mismatch_flag(conn, second.audit_id) == 1
        assert _approval_state(conn, approval_id) == state, "untouched by the mismatched lookup"


@pytest.mark.parametrize("state", ["pending", "approved"])
@pytest.mark.parametrize("principal", [None, "principal-a"])
def test_a_matching_principal_still_reuses_the_row_as_before(
    conn: Connection, config: EngineConfig, state: str, principal: str | None
) -> None:
    """The same principal's own resume is unaffected by the scoping fix."""
    first = _resume(conn, config, principal=principal, params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None
    if state == "approved":
        with tx(conn):
            approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)

    second = _resume(conn, config, principal=principal, params=PARAMS_A)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED
    assert second.approval_id == approval_id, "the same principal must still reuse its own row"
    assert _mismatch_flag(conn, second.audit_id) is None

    rows = conn.execute("SELECT COUNT(*) AS n FROM approvals").fetchone()
    assert rows["n"] == 1


@pytest.mark.parametrize("principal", [None, "principal-a"])
def test_an_expired_own_approval_is_denied_not_reproposed(
    conn: Connection, config: EngineConfig, principal: str | None
) -> None:
    """The caller's own in-flight row at this key, found past
    its own `expires_at`, must be denied (`CheckId.APPROVAL_EXPIRED`) --
    never silently re-proposed. Before this, an expired own row was
    indistinguishable from a key nobody had ever used, so a resume just
    created a second, unrelated approval -- an unanswered approval could be
    retried forever by resuming again.
    """
    first = _resume(conn, config, principal=principal, params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None

    later = FROZEN_NOW + timedelta(seconds=config.approval_ttl_seconds + 1)
    second = _resume(conn, config, principal=principal, params=PARAMS_A, now=later)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.DENIED
    assert second.decision.reason_code == CheckId.APPROVAL_EXPIRED
    assert second.approval_id is None

    assert _approval_state(conn, approval_id) == "expired"
    rows = conn.execute("SELECT COUNT(*) AS n FROM approvals").fetchone()
    assert rows["n"] == 1, "an expired own row must not spawn a second approval"


# --- A different request shape presented against the first caller's live key ---


@pytest.mark.parametrize("state", ["pending", "approved", "expired"])
@pytest.mark.parametrize(
    ("a_principal", "b_principal"),
    [
        (None, "principal-b"),
        ("principal-a", None),
        ("principal-a", "principal-b"),
    ],
)
def test_a_mismatched_principals_different_shaped_request_also_learns_nothing(
    conn: Connection,
    config: EngineConfig,
    state: str,
    a_principal: str | None,
    b_principal: str | None,
) -> None:
    """Before the fix, a mismatched-shape request against a live key was told
    apart from a key nobody had used (RESUME_REQUEST_MISMATCH). Scoped to the
    caller, that tell disappears along with everything else the lookup used
    to reveal: the second caller's own, differently-shaped request simply
    proposes fresh, in every state.
    """
    first = _resume(conn, config, principal=a_principal, params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None

    now = FROZEN_NOW
    if state == "approved":
        with tx(conn):
            approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)
    elif state == "expired":
        now = FROZEN_NOW + timedelta(seconds=config.approval_ttl_seconds + 1)

    second = _resume(conn, config, principal=b_principal, params=PARAMS_B, now=now)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.PROPOSED, (
        "a mismatched principal must never see RESUME_REQUEST_MISMATCH"
    )
    assert second.decision.reason_code != CheckId.RESUME_REQUEST_MISMATCH


@pytest.mark.parametrize("state", ["pending", "approved"])
@pytest.mark.parametrize("principal", [None, "principal-a"])
def test_a_matching_principals_different_shaped_request_is_still_refused_with_both_digests(
    conn: Connection, config: EngineConfig, state: str, principal: str | None
) -> None:
    """The same principal's own mismatched-shape resume is unaffected: still
    refused, still with both digests recorded, exactly as before the fix.
    """
    first = _resume(conn, config, principal=principal, params=PARAMS_A)
    assert isinstance(first, ActionResult)
    approval_id = first.approval_id
    assert approval_id is not None
    if state == "approved":
        with tx(conn):
            approvals.cas_approve(conn, approval_id, "human-1", FROZEN_NOW)

    second = _resume(conn, config, principal=principal, params=PARAMS_B)
    assert isinstance(second, ActionResult)
    assert second.decision.decision == Decision.DENIED
    assert second.decision.reason_code == CheckId.RESUME_REQUEST_MISMATCH
    audit_row = conn.execute(
        "SELECT resume_digest_expected, resume_digest_actual FROM actions_audit WHERE id=?",
        (second.audit_id,),
    ).fetchone()
    assert audit_row["resume_digest_expected"] is not None
    assert audit_row["resume_digest_actual"] is not None


# --- FIX A: a principal's own resume once ANOTHER principal already holds its
# own row at the same key (possible since the scoping fix lets each principal
# hold one) must still find that caller's own row, never raise, and never be
# blocked by a rival's row whether it is still live or has already lapsed. ---


@pytest.mark.parametrize(
    ("first_principal", "second_principal"),
    [
        ("aaa-principal", "zzz-principal"),  # proposal order matches alphabetical order
        ("zzz-principal", "aaa-principal"),  # proposal order is the reverse of it
    ],
)
def test_two_principals_each_resuming_their_own_row_does_not_raise(
    conn: Connection, config: EngineConfig, first_principal: str, second_principal: str
) -> None:
    """Before the fix, `find_by_resume_key` read only the first in-flight row at
    the key -- SQLite's own index order, which sorts by principal, not by
    proposal order -- so whichever principal's identity sorted LATER found a
    mismatch, was told "no row", and then collided with its own already-
    existing row trying to `create` a fresh one. Both proposal orders are
    covered here so the fix is not accidentally order-dependent.
    """
    first = _resume(conn, config, principal=first_principal, params=PARAMS_A)
    assert isinstance(first, ActionResult)
    first_id = first.approval_id
    assert first_id is not None

    second = _resume(conn, config, principal=second_principal, params=PARAMS_A)
    assert isinstance(second, ActionResult)
    second_id = second.approval_id
    assert second_id is not None
    assert second_id != first_id

    first_again = _resume(conn, config, principal=first_principal, params=PARAMS_A)
    assert isinstance(first_again, ActionResult)
    assert first_again.approval_id == first_id, "the first principal must still reuse its own row"

    second_again = _resume(conn, config, principal=second_principal, params=PARAMS_A)
    assert isinstance(second_again, ActionResult)
    assert second_again.approval_id == second_id, (
        "the second principal must still reuse its own row, not raise"
    )


def test_a_rivals_lapsed_row_does_not_block_ones_own_still_live_resume(
    conn: Connection, config: EngineConfig
) -> None:
    """A rival's row ahead of the caller's own in the lookup's read order used
    to block the caller's resume whether that row was still live (a mismatch,
    read as "no row for me") or had already lapsed (the old code returned
    right after marking it expired, before ever reading the caller's own
    row). Here the rival's row lapses first and the caller's own is still
    live when the caller resumes -- the case the old code got wrong by
    returning too early.
    """
    rival = _resume(conn, config, principal="aaa-rival", params=PARAMS_A, now=FROZEN_NOW)
    assert isinstance(rival, ActionResult)
    rival_id = rival.approval_id
    assert rival_id is not None

    own_created_at = FROZEN_NOW + timedelta(seconds=30)
    own = _resume(conn, config, principal="zzz-own", params=PARAMS_A, now=own_created_at)
    assert isinstance(own, ActionResult)
    own_id = own.approval_id
    assert own_id is not None

    later = FROZEN_NOW + timedelta(seconds=config.approval_ttl_seconds + 5)
    assert later < own_created_at + timedelta(seconds=config.approval_ttl_seconds), (
        "the rival must have lapsed while the caller's own row is still live"
    )

    own_again = _resume(conn, config, principal="zzz-own", params=PARAMS_A, now=later)
    assert isinstance(own_again, ActionResult)
    assert own_again.approval_id == own_id, (
        "the rival's lapse must not block the caller's own, still-live row"
    )

    rival_row = conn.execute("SELECT state FROM approvals WHERE id=?", (rival_id,)).fetchone()
    assert rival_row["state"] == "expired"


def test_a_third_principals_first_presentation_of_an_occupied_key_proposes_fresh(
    conn: Connection, config: EngineConfig
) -> None:
    """A third principal's first-ever presentation of a key two others already
    hold rows at must still be an ordinary fresh proposal -- not blocked, not
    told `RESUME_REQUEST_MISMATCH`, and not handed anyone else's id.
    """
    for principal in ("aaa-rival", "zzz-rival"):
        occupied = _resume(conn, config, principal=principal, params=PARAMS_A)
        assert isinstance(occupied, ActionResult)

    third = _resume(conn, config, principal="third-principal", params=PARAMS_A)
    assert isinstance(third, ActionResult)
    assert third.decision.decision == Decision.PROPOSED
    assert third.decision.reason_code != CheckId.RESUME_REQUEST_MISMATCH
    assert third.approval_id not in (None,)


def _legacy_0_11_1_store(
    tmp_path: Path, *, legacy_principal: str | None, ttl_seconds: int
) -> Connection:
    """A store whose one row at `THREAD`/`CALL` was written before migrations
    `0051`-`0053` existed. 0.11.1's own resume-key index was global and
    unscoped, so it could only ever hold one in-flight row per key at all --
    this is the only starting shape a real upgrade can actually have.
    """
    path = str(tmp_path / "legacy_0_11_1.db")
    conn = db_connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    for migration_path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        if migration_path.name >= "0051":
            continue
        conn.executescript(migration_path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
            (migration_path.name,),
        )
    _seed_test_policies(conn)
    approvals.create(
        conn,
        make_request("demo.confirm", PARAMS_A),
        ttl_seconds,
        FROZEN_NOW,
        proposed_by=legacy_principal,
        thread_id=THREAD,
        tool_call_id=CALL,
    )
    applied = run_migrations(conn)
    assert any(name.startswith("0051") for name in applied)
    assert any(name.startswith("0052") for name in applied)
    return conn


@pytest.mark.parametrize("legacy_principal", [None, "legacy-principal"])
def test_two_principals_resume_cleanly_on_a_store_upgraded_from_0_11_1(
    tmp_path: Path, config: EngineConfig, legacy_principal: str | None
) -> None:
    """The same two-principals-at-one-key scenario, replayed starting from a
    store an actual 0.11.1 release wrote to: one legacy row, upgraded in
    place, with a second principal then proposing fresh at the same key.
    Neither the legacy proposer nor the newcomer may raise resuming, and
    each must keep reusing its own row.
    """
    conn = _legacy_0_11_1_store(
        tmp_path, legacy_principal=legacy_principal, ttl_seconds=config.approval_ttl_seconds
    )
    try:
        legacy_row = conn.execute(
            "SELECT id FROM approvals WHERE thread_id=? AND tool_call_id=?", (THREAD, CALL)
        ).fetchone()
        legacy_id = int(legacy_row["id"])

        newcomer = _resume(conn, config, principal="new-principal", params=PARAMS_A)
        assert isinstance(newcomer, ActionResult)
        newcomer_id = newcomer.approval_id
        assert newcomer_id is not None
        assert newcomer_id != legacy_id

        legacy_again = _resume(conn, config, principal=legacy_principal, params=PARAMS_A)
        assert isinstance(legacy_again, ActionResult)
        assert legacy_again.approval_id == legacy_id, (
            "the legacy row's own proposer must still reuse it"
        )

        newcomer_again = _resume(conn, config, principal="new-principal", params=PARAMS_A)
        assert isinstance(newcomer_again, ActionResult)
        assert newcomer_again.approval_id == newcomer_id, (
            "the newcomer must still reuse its own row"
        )
    finally:
        conn.close()
