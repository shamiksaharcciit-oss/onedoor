"""The resume-by-key lookup (`find_by_resume_key`) is scoped to the caller's
own principal, so a second caller holding the first caller's own
``(thread_id, tool_call_id)`` learns nothing and can consume nothing of the
first caller's own approval — whatever principal either side did or did not
authenticate.
"""

from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionResult, CheckId, Decision
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request

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


# --- Every case of 30sr step 1, now scoped: same request shape, by state ---


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
