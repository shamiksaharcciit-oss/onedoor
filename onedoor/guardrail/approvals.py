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

from onedoor.guardrail import audit
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.models import ActionRequest, Approval, ApprovalState
from onedoor.store.clock import from_iso, to_iso


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
    conn: sqlite3.Connection, request: ActionRequest, ttl_seconds: int, now: datetime
) -> int:
    cur = conn.execute(
        "INSERT INTO approvals (request_json, action_type, state, created_at, expires_at) "
        "VALUES (?, ?, 'pending', ?, ?)",
        (
            dumps_request(request),
            request.action_type,
            to_iso(now),
            to_iso(now + timedelta(seconds=ttl_seconds)),
        ),
    )
    return int(cur.lastrowid or 0)


def get(conn: sqlite3.Connection, approval_id: int) -> Approval | None:
    row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return _row_to_approval(row) if row else None


def list_pending(conn: sqlite3.Connection) -> list[Approval]:
    rows = conn.execute("SELECT * FROM approvals WHERE state='pending' ORDER BY created_at DESC")
    return [_row_to_approval(r) for r in rows]


def cas_approve(
    conn: sqlite3.Connection, approval_id: int, session_id: str, now: datetime
) -> ActionRequest:
    """Flip pending -> approved iff still pending and unexpired. Returns the request."""
    cur = conn.execute(
        "UPDATE approvals SET state='approved', decided_at=?, decided_by_session=? "
        "WHERE id=? AND state='pending' AND expires_at > ?",
        (to_iso(now), session_id, approval_id, to_iso(now)),
    )
    if cur.rowcount == 0:
        raise ApprovalError(f"approval {approval_id} not pending or already expired")
    row = conn.execute("SELECT request_json FROM approvals WHERE id=?", (approval_id,)).fetchone()
    return loads_request(row["request_json"])


def deny(conn: sqlite3.Connection, approval_id: int, session_id: str, now: datetime) -> None:
    cur = conn.execute(
        "UPDATE approvals SET state='denied', decided_at=?, decided_by_session=? "
        "WHERE id=? AND state='pending'",
        (to_iso(now), session_id, approval_id),
    )
    if cur.rowcount == 0:
        raise ApprovalError(f"approval {approval_id} not pending")


def mark_executed(conn: sqlite3.Connection, approval_id: int, audit_id: int | None) -> None:
    conn.execute(
        "UPDATE approvals SET state='executed', resulting_audit_id=? WHERE id=?",
        (audit_id, approval_id),
    )


def sweep(conn: sqlite3.Connection, now: datetime) -> int:
    """Lazily expire overdue pending approvals. Returns count expired."""
    cur = conn.execute(
        "UPDATE approvals SET state='expired' WHERE state='pending' AND expires_at <= ?",
        (to_iso(now),),
    )
    return cur.rowcount
