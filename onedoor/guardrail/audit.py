"""The append-only audit writer — the ONLY writer to ``actions_audit``.

There are deliberately no update/delete methods here; the table's triggers reject
those structurally as a second line of defense (invariant 5).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from uuid import UUID

from onedoor.guardrail.models import (
    ActionRequest,
    ActionResult,
    Decision,
    JsonValue,
    PolicyDecision,
    Tier,
)
from onedoor.store.clock import from_iso, to_iso


def append(
    conn: sqlite3.Connection,
    request: ActionRequest,
    decision: PolicyDecision,
    *,
    kind: str,
    now: datetime,
    parent_id: int | None = None,
    connector_ok: bool | None = None,
    error: str | None = None,
    payload: dict[str, JsonValue] | None = None,
    approval_id: int | None = None,
    undo_until: datetime | None = None,
    undo_of: int | None = None,
) -> int:
    """Insert one audit row and return its id."""
    cur = conn.execute(
        "INSERT INTO actions_audit ("
        " request_id, kind, parent_id, action_type, source, params_json,"
        " decision, reason_code, nominal_tier, effective_tier, detail,"
        " connector_ok, error, payload_json, approval_id, undo_until, undo_of, created_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(request.request_id),
            kind,
            parent_id,
            request.action_type,
            request.source.value,
            json.dumps(request.params, default=str),
            decision.decision.value,
            decision.reason_code.value,
            int(decision.nominal_tier),
            int(decision.effective_tier),
            decision.detail,
            None if connector_ok is None else int(connector_ok),
            error,
            None if payload is None else json.dumps(payload, default=str),
            approval_id,
            to_iso(undo_until) if undo_until else None,
            undo_of,
            to_iso(now),
        ),
    )
    return int(cur.lastrowid or 0)


def find_rows(conn: sqlite3.Connection, request_id: UUID) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM actions_audit WHERE request_id=? ORDER BY id",
            (str(request_id),),
        )
    )


def _row_decision(row: sqlite3.Row) -> PolicyDecision:
    decision = Decision(row["decision"])
    return PolicyDecision(
        decision=decision,
        effective_tier=Tier(row["effective_tier"]),
        nominal_tier=Tier(row["nominal_tier"]),
        reason_code=row["reason_code"],
        detail=row["detail"],
        dry_run=decision == Decision.DRY_RUN,
        requires_approval=decision == Decision.PROPOSED,
    )


def result_for_request_id(conn: sqlite3.Connection, request_id: UUID) -> ActionResult | None:
    """Reconstruct the prior :class:`ActionResult` for a replayed request, if any."""
    rows = find_rows(conn, request_id)
    if not rows:
        return None

    by_kind = {row["kind"]: row for row in rows}
    intent = by_kind.get("exec_intent")
    result = by_kind.get("exec_result")
    primary = result or intent or by_kind.get("decision") or rows[-1]

    connector_ok: bool | None = None
    executed = False
    error: str | None = None
    payload: dict[str, JsonValue] | None = None
    undo_until: datetime | None = None
    if result is not None:
        connector_ok = None if result["connector_ok"] is None else bool(result["connector_ok"])
        executed = bool(connector_ok)
        error = result["error"]
        payload = json.loads(result["payload_json"]) if result["payload_json"] else None
    if intent is not None and intent["undo_until"]:
        undo_until = from_iso(intent["undo_until"])

    # Report the intent row's id when the action executed, matching what the
    # executor returned on the original run (so replays are identical).
    anchor = intent or primary
    return ActionResult(
        request_id=request_id,
        decision=_row_decision(primary),
        executed=executed,
        connector_ok=connector_ok,
        connector_payload=payload,
        error=error,
        audit_id=int(anchor["id"]),
        approval_id=primary["approval_id"],
        undo_available_until=undo_until if executed else None,
    )
