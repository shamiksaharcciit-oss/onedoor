"""Tier-3 approval lifecycle (pure persistence).

State transitions use compare-and-set so the TTL-expiry race is closed: approving
after expiry affects zero rows and is rejected. The ``actions_audit`` table stays
append-only; the ``approvals`` table is legitimately mutable lifecycle state.

This module does NOT import the executor. The *resume-on-approve* orchestration
lives in :mod:`app.guardrail.executor` (which imports this), avoiding a cycle.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from onedoor._vendor.canonical import digest_obj
from onedoor.guardrail import audit
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.models import (
    ActionRequest,
    Approval,
    ApprovalState,
    CheckId,
    Decision,
    JsonValue,
)
from onedoor.store.clock import from_iso, to_iso

RESUME_DIGEST_KIND = "onedoor/resume-request-digest/1"


def resume_digest(action_type: str, params: dict[str, JsonValue]) -> str:
    """What a resumed proposal is CHECKED against: the request's canonical digest,
    deliberately WITHOUT `request_id`.

    `onedoor.guardrail.mandate.core_digest` solves the opposite problem -- it is
    request_id-bound ON PURPOSE, so a ratification cannot be replayed onto a
    different record. A resumed LangGraph node rebuilds its `ActionRequest` with a
    fresh `request_id` every time (that is the bug this digest exists to catch
    around, not a property to bind to), so the two facts that make a resume "the
    same request" are exactly `action_type` and `params` -- the same canonical
    rendering `core_digest` uses for `params`, reused here rather than introducing
    a second canonicalisation scheme.
    """
    params_digest = digest_obj(_canon(params))
    return digest_obj(
        {"kind": RESUME_DIGEST_KIND, "action_type": action_type, "params_digest": params_digest}
    )


def _canon(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canon(v) for v in value]
    return value


def _row_to_approval(row: sqlite3.Row) -> Approval:
    return Approval(
        approval_id=int(row["id"]),
        request=loads_request(row["request_json"]),
        state=ApprovalState(row["state"]),
        created_at=from_iso(row["created_at"]),
        expires_at=from_iso(row["expires_at"]),
        decided_at=from_iso(row["decided_at"]) if row["decided_at"] else None,
        decided_by_session=row["decided_by_session"],
        resulting_audit_id=row["resulting_audit_id"],
    )


def dumps_request(request: ActionRequest) -> str:
    """Persist a request so its numeric params survive the round trip.

    `model_dump_json()` renders a `Decimal` param as a JSON *string*, and the
    approval resumption then re-validates it as a `str` -- which the bounds gate
    refuses as "must be numeric", denying every approved numeric action. Found by
    running the MCP demo end to end after E10's `parse_float=Decimal` landed: step 5,
    "a human approves", reported `approved action did not execute (reason: bounds)`.

    It fails closed, so it is a correctness break rather than a safety hole. Same
    class as the audit serializer, at the other persistence boundary -- a numeric
    parameter must be a JSON number wherever it is stored, or it stops being numeric
    when read back.
    """
    return audit.dumps_json_value(request.model_dump())


def loads_request(text: str) -> ActionRequest:
    """The matching read: JSON numbers become `Decimal`, never float (E10)."""
    return ActionRequest.model_validate(json.loads(text, parse_float=Decimal))


def create(
    conn: sqlite3.Connection,
    request: ActionRequest,
    ttl_seconds: int,
    now: datetime,
    *,
    mandate_core_digest: str | None = None,
    mandate_combined: bool = False,
    proposed_by: str | None = None,
    thread_id: str | None = None,
    tool_call_id: str | None = None,
) -> int:
    """Create a pending approval.

    `mandate_core_digest` set marks it mandate-gated: `cas_approve`/
    `deny` refuse it structurally, and only `onedoor.guardrail.mandate.ratify` can
    resolve it, against exactly this digest.

    `mandate_combined` marks a mandate-gated approval whose action onedoor's own checks
    also send to a human: it is released only when the mandate authority has ratified it
    AND an approver has then approved it (`mandate_authority` 2 rather than 1).

    `proposed_by` is the principal that asked, as authenticated by the caller of the
    engine; `cas_approve` refuses an approval by that same principal.

    `thread_id`/`tool_call_id` (migration `0030`) are the caller's resume key, when it
    has one -- NULL for every caller that does not (the HTTP service, the MCP
    integration, direct engine calls), unconstrained by the unique index either way.
    `request_digest` is computed and stored ONLY when both are given: a row with no
    resume key is never looked up by `find_by_resume_key`, and `resume_digest` rejects
    a raw float in `params` (E10) -- a real, legitimate shape for a caller that has no
    resume key and no reason to canonicalise anything. Computing it unconditionally
    would make an ordinary, non-resumable propose fail on a param shape every other
    path on this route already tolerates.
    """
    digest = (
        resume_digest(request.action_type, request.params)
        if thread_id is not None and tool_call_id is not None
        else None
    )
    cur = conn.execute(
        "INSERT INTO approvals "
        "(request_json, action_type, state, created_at, expires_at, "
        "mandate_authority, mandate_core_digest, proposed_by, "
        "thread_id, tool_call_id, request_digest) "
        "VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dumps_request(request),
            request.action_type,
            to_iso(now),
            to_iso(now + timedelta(seconds=ttl_seconds)),
            (2 if mandate_combined else 1) if mandate_core_digest is not None else None,
            mandate_core_digest,
            proposed_by,
            thread_id,
            tool_call_id,
            digest,
        ),
    )
    return int(cur.lastrowid or 0)


def find_by_resume_key(
    conn: sqlite3.Connection, thread_id: str, tool_call_id: str
) -> sqlite3.Row | None:
    """The row, if any, a resume with this exact (thread_id, tool_call_id) would reuse.

    `state` `pending` or `approved` only. A LangGraph resume re-executes the
    interrupted node from the top -- `_decide()` runs once with no reference,
    which must find the row whatever state waiting left it in, pending (a
    human hasn't acted) or approved (a human already has, but the resumed
    node hasn't yet presented the reference to consume it) -- and only then,
    separately, with the reference. A row that has been consumed, denied or
    expired is no longer reusable -- `cas_approve` will never flip it to
    'approved' a second time -- so a resume that finds one must get a fresh
    pending approval of its own, the same as a caller presenting this resume
    key for the very first time. Without this, a resume landing after the
    original approval was consumed (the action already ran) or expired would
    be told 'proposed' against a dead row that can never be approved again.

    Returns the raw row (not an :class:`Approval`) because the caller needs
    `request_digest` and `id` to decide whether to reuse it at all -- `_row_to_approval`
    would have to grow a field most callers never need.
    """
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM approvals WHERE thread_id=? AND tool_call_id=? "
        "AND state IN ('pending', 'approved')",
        (thread_id, tool_call_id),
    ).fetchone()
    return row


def get(conn: sqlite3.Connection, approval_id: int) -> Approval | None:
    row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return _row_to_approval(row) if row else None


def list_pending(conn: sqlite3.Connection) -> list[Approval]:
    rows = conn.execute("SELECT * FROM approvals WHERE state='pending' ORDER BY created_at DESC")
    return [_row_to_approval(r) for r in rows]


def _refuse_if_mandate_gated(
    conn: sqlite3.Connection, approval_id: int, *, session_id: str, now: datetime
) -> None:
    """The structural half of the rule: not merely "the HTTP route doesn't expose
    it", but "this function refuses it even if something else calls it directly".

    AADP -03 §8.1: an approval waiting on a mandate-layer deferral is resolved by
    the mandate authority's ratification and by nothing else -- an admin key is
    "nothing else", however it reaches this function.

    A refused attempt is still an attempt, and is audited -- who tried, when, which
    approval -- BEFORE `ApprovalError` is raised, the same way a wrong-key
    ratification attempt is audited before `mandate.ratify` refuses it. Silence here
    would mean the one route explicitly forbidden from resolving a mandate-gated
    approval is also the one route that leaves no trace when it tries.
    """
    row = conn.execute(
        "SELECT mandate_authority, state FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    if row is not None and row["mandate_authority"] == 2 and row["state"] == "ratified":
        return  # the mandate half is done; an approver may now give the other half
    if row is not None and row["mandate_authority"]:
        intent_row = conn.execute(
            "SELECT * FROM actions_audit WHERE approval_id=? ORDER BY id DESC LIMIT 1",
            (approval_id,),
        ).fetchone()
        if intent_row is not None:  # pragma: no cover - defensive; every approval has one
            audit.append_expiry(
                conn,
                intent_row,
                now,
                detail=f"admin attempt by session {session_id!r} on a mandate-gated approval",
                kind="mandate_admin_attempt",
                reason=CheckId.EXTERNAL_AUTHORIZATION,
                decision=Decision.DENIED,
                request_id=str(uuid4()),
            )
        if row["mandate_authority"] == 2:
            raise ApprovalError(
                f"approval {approval_id} needs the mandate-layer authority's ratification "
                f"first (onedoor.guardrail.mandate.ratify); an approver can approve it only "
                f"after that"
            )
        raise ApprovalError(
            f"approval {approval_id} waits on a mandate-layer ratification (AADP -03 "
            f"§8.1); it resolves only through onedoor.guardrail.mandate.ratify, never "
            f"through an admin key"
        )


def cas_approve(
    conn: sqlite3.Connection, approval_id: int, session_id: str, now: datetime
) -> ActionRequest:
    """Flip pending -> approved iff still pending and unexpired. Returns the request.

    The principal that proposed the action can never approve it: refused here, in the
    store, so the rule holds for every caller rather than only for the enforcement
    points that choose not to offer an approve method.

    A combined approval (`mandate_authority=2`) only reaches here from
    `state='ratified'` -- stated limit, not an oversight: the mandate authority must
    ratify FIRST, before an approver can act; an approver cannot approve a combined
    approval that is still merely `pending`. The requirement this satisfies is
    narrower than "either order works" -- it is that neither authority alone resumes
    the action, which this still holds regardless of the ordering restriction.
    """
    _refuse_if_mandate_gated(conn, approval_id, session_id=session_id, now=now)
    proposer = conn.execute(
        "SELECT proposed_by FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    if proposer is not None and proposer["proposed_by"] == session_id:
        raise ApprovalError(
            f"approval {approval_id} was proposed by {session_id!r}; the principal that "
            f"proposed an action cannot approve it"
        )
    cur = conn.execute(
        "UPDATE approvals SET state='approved', decided_at=?, decided_by_session=? "
        "WHERE id=? AND expires_at > ? AND (proposed_by IS NULL OR proposed_by != ?) "
        "AND ((state='pending' AND mandate_authority IS NULL) "
        "OR (state='ratified' AND mandate_authority=2))",
        (to_iso(now), session_id, approval_id, to_iso(now), session_id),
    )
    if cur.rowcount == 0:
        raise ApprovalError(f"approval {approval_id} not pending or already expired")
    row = conn.execute("SELECT request_json FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return loads_request(row["request_json"])


def cas_resume_ratified(conn: sqlite3.Connection, approval_id: int, now: datetime) -> ActionRequest:
    """Flip ratified -> approved iff still ratified. Returns the request.

    `mandate.ratify`'s own CAS (pending -> ratified) stops a second ratification of
    the same record; it does not stop a second RESUMPTION of the one ratification
    that already succeeded, since resuming is a separate call with no state check
    of its own. This is that check, mirroring `cas_approve`'s pending -> approved
    gate exactly: 'approved' is reused rather than adding a new state, because it
    means the same thing here as it does for an admin approval -- cleared for the
    one resumption now in flight, not yet consumed. A second resumption attempt,
    however it arrives or whatever request_id it mints, finds the row no longer
    'ratified' and is refused before anything executes twice.
    """
    cur = conn.execute(
        "UPDATE approvals SET state='approved' WHERE id=? AND state='ratified' "
        "AND mandate_authority=1",
        (approval_id,),
    )
    if cur.rowcount == 0:
        combined = conn.execute(
            "SELECT 1 FROM approvals WHERE id=? AND mandate_authority=2", (approval_id,)
        ).fetchone()
        if combined is not None:
            raise ApprovalError(
                f"approval {approval_id} also needs an approver's approval; the "
                f"ratification alone does not resume it"
            )
        raise ApprovalError(f"approval {approval_id} not ratified or already resumed")
    row = conn.execute("SELECT request_json FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return loads_request(row["request_json"])


def deny(conn: sqlite3.Connection, approval_id: int, session_id: str, now: datetime) -> None:
    """Refuse a pending approval. An approver may refuse a combined approval (a mandate
    deferral on an action onedoor also escalates) before or after the ratification --
    either authority saying no ends it. A mandate-only approval stays the mandate
    authority's alone."""
    row = conn.execute(
        "SELECT mandate_authority FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()
    if row is None or row["mandate_authority"] != 2:
        _refuse_if_mandate_gated(conn, approval_id, session_id=session_id, now=now)
    cur = conn.execute(
        "UPDATE approvals SET state='denied', decided_at=?, decided_by_session=? "
        "WHERE id=? AND (state='pending' OR (state='ratified' AND mandate_authority=2))",
        (to_iso(now), session_id, approval_id),
    )
    if cur.rowcount == 0:
        raise ApprovalError(f"approval {approval_id} not pending")


def proposed_audit_id(conn: sqlite3.Connection, approval_id: int) -> int | None:
    """The audit id of the row that proposed this approval (`kind='decision'`,
    the Tier-3 `PROPOSED` verdict written when the approval was created) --
    the link a resumption's own new audit row needs to name what it resumes.
    `None` if somehow no such row exists (defensive; every approval this
    module creates is immediately followed by exactly one).

    A read against `actions_audit`, not a new column on `approvals`: the
    audit row already carries `approval_id` (set by the same `decide_and_reserve`
    call that created this approval), so the link already exists in the one
    place it can never be edited out from under a caller.
    """
    row = conn.execute(
        "SELECT id FROM actions_audit WHERE approval_id=? AND kind='decision' "
        "ORDER BY id ASC LIMIT 1",
        (approval_id,),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def consume(conn: sqlite3.Connection, approval_id: int) -> None:
    """Flip approved -> consumed iff still approved; refuse otherwise.

    Called first, inside the transaction of the decision that resumes the approval,
    so the approval is used up by that decision whatever its verdict -- a denied
    resumption consumes it exactly as a permitted one does. A row no longer
    `approved` (used already, or lost to a concurrent resumption) is refused before
    anything is evaluated.
    """
    cur = conn.execute(
        "UPDATE approvals SET state='consumed' WHERE id=? AND state='approved'",
        (approval_id,),
    )
    if cur.rowcount == 0:
        raise ApprovalError(f"approval {approval_id} is not approved, or has already been used")


def record_result(conn: sqlite3.Connection, approval_id: int, audit_id: int | None) -> None:
    """Link a consumed approval to the audit row of the decision that consumed it."""
    conn.execute(
        "UPDATE approvals SET resulting_audit_id=? WHERE id=? AND state='consumed'",
        (audit_id, approval_id),
    )


def sweep(conn: sqlite3.Connection, now: datetime) -> int:
    """Lazily expire overdue pending approvals. Returns count expired."""
    cur = conn.execute(
        "UPDATE approvals SET state='expired' WHERE state='pending' AND expires_at <= ?",
        (to_iso(now),),
    )
    return cur.rowcount
