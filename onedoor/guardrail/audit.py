"""The append-only audit writer — the ONLY writer to ``actions_audit``.

There are deliberately no update/delete methods here; the table's triggers reject
those structurally as a second line of defense (invariant 5).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from onedoor._vendor.canonical import canon_decimal
from onedoor.guardrail.models import (
    ActionRequest,
    ActionResult,
    CheckId,
    Decision,
    JsonValue,
    PolicyDecision,
    Tier,
)
from onedoor.guardrail.received import Provenance
from onedoor.store.clock import from_iso, now_utc, to_iso
from onedoor.store.db import tx


def frozen_params(request: ActionRequest) -> tuple[str, str]:
    """The bytes to store for `params`, and how they came to be (E10 / R004).

    Received bytes are stored EXACTLY as sent -- not parsed, not re-serialized, not
    canonicalised. `250.00` stays `250.00`, because the record must show what the
    enforcement point transmitted rather than what this PDP would have written.
    Only when no bytes were received (the in-process binding) does the PDP serialize,
    once, and say so.
    """
    if request.params_raw is not None:
        return request.params_raw, Provenance.RECEIVED.value
    return dumps_json_value(request.params), Provenance.SERIALIZED.value


AADP_PROTOCOL = "aadp/0.2"
"""The wire vocabulary every row written by this PDP is stamped with (ND-002/E6).

A row with NO protocol value MUST be read under `aadp/0.1` -- the pre-0.4.0
vocabulary, where a cap denial says `cap_eur_day` or `cap_eur_month` rather than
`cap_value` and carries its window only as prose in `detail`. That fallback is the
absent-value rule, and it is why the column is nullable rather than defaulted: an
absent stamp is a fact about when the row was written, not a value to invent.
"""


def dumps_json_value(value: object) -> str:
    """Serialize a params/payload tree so it ROUND-TRIPS through Decimal.

    `json.dumps(..., default=str)` renders a `Decimal` as a JSON *string*, and
    `json.loads(..., parse_float=Decimal)` then hands back a `str` -- so a numeric
    parameter written by the decision point comes back non-numeric and the bounds
    gate refuses it as "must be numeric". That surfaced the moment E10's
    `parse_float=Decimal` landed: the approval-resumption path re-reads `params_json`,
    and every governed numeric action began denying. It fails closed, so it is a
    correctness break rather than a safety hole, but it is a break.

    Decimals are therefore emitted as JSON **numbers**, rendered through the canonical
    renderer so `49.99`, `49.990` and `4.999E+1` all write identically and read back
    equal. Note this is deliberately NOT ACJ: ACJ carries decimals as strings
    (`canonical_bytes` refuses a `Decimal` outright), which is right for a *generated*
    structure like the budget object and wrong for received params, where a JSON
    number must stay a JSON number.

    `ND-002`/W7 replaces this with the verbatim freeze -- the stored bytes being the
    received bytes, with no re-serialization at all. Until then this keeps the
    round trip honest.
    """
    if isinstance(value, Decimal):
        return canon_decimal(value)
    if isinstance(value, bool) or value is None or isinstance(value, int | float):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(dumps_json_value(v) for v in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items())
        return "{" + ",".join(f"{json.dumps(str(k))}:{dumps_json_value(v)}" for k, v in items) + "}"
    return json.dumps(value, default=str)


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
    outcome: str | None = None,
    malformed_kind: str | None = None,
    canon_schema: str | None = None,
) -> int:
    """Insert one audit row and return its id.

    Every row carries the hash of the policy set in force, so a verdict can be
    re-derived against the exact rules that produced it (AADP section 10). The
    policy table is upserted in place; without this stamp, editing policy silently
    destroys the ability to check any earlier decision.
    """
    row = conn.execute("SELECT version_hash FROM policy_current WHERE id=1").fetchone()
    policy_version = row["version_hash"] if row else None
    params_bytes, params_provenance = frozen_params(request)
    cur = conn.execute(
        "INSERT INTO actions_audit ("
        " request_id, kind, parent_id, action_type, source, params_json,"
        " decision, reason_code, nominal_tier, effective_tier, detail,"
        " connector_ok, error, payload_json, approval_id, undo_until, undo_of, created_at,"
        " policy_version, protocol, budget_json, outcome,"
        " params_provenance, payload_provenance, malformed_kind, canon_schema"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(request.request_id),
            kind,
            parent_id,
            request.action_type,
            request.source.value,
            params_bytes,
            decision.decision.value,
            decision.reason_code.value,
            int(decision.nominal_tier),
            int(decision.effective_tier),
            decision.detail,
            None if connector_ok is None else int(connector_ok),
            error,
            None if payload is None else dumps_json_value(payload),
            approval_id,
            to_iso(undo_until) if undo_until else None,
            undo_of,
            to_iso(now),
            policy_version,
            AADP_PROTOCOL,
            # E7: PERSISTED, not merely returned. cap_value collapses the day and
            # month windows, so a denial that cannot name its window is not
            # re-derivable from the evidence store alone.
            None if decision.budget is None else dumps_json_value(decision.budget.model_dump()),
            outcome,
            params_provenance,
            # A payload is produced by the enforcement point after acting, and every
            # packaged PEP hands us objects rather than bytes, so it is serialized
            # here. If a PEP ever forwards raw payload bytes this becomes RECEIVED.
            None if payload is None else Provenance.SERIALIZED.value,
            malformed_kind,
            canon_schema,
        ),
    )
    return int(cur.lastrowid or 0)


def append_expiry(
    conn: sqlite3.Connection,
    intent_row: sqlite3.Row,
    now: datetime,
    *,
    detail: str = "",
    kind: str = "reservation_expired",
    reason: CheckId = CheckId.EXPIRED,
) -> int:
    """Append a reservation-disposition row for a permit whose budget went back.

    Two callers, one shape, on purpose. Reclamation writes
    ``reservation_expired`` when a deadline passes unreported; a ``not_attempted``
    report writes ``reservation_released`` when the enforcement point positively
    asserts the action did not happen (R005). Both give budget back, and **both are
    audited events, never silent adjustments** -- the audit's job is to make a false
    report attributable, not to prevent a trusted reporter from lying.

    Written directly from the stored exec_intent row rather than a reconstructed
    request, because reclamation runs long after the request object is gone. It
    links back to the intent it voids via ``parent_id``.
    """
    row = conn.execute("SELECT version_hash FROM policy_current WHERE id=1").fetchone()
    policy_version = row["version_hash"] if row else None
    cur = conn.execute(
        "INSERT INTO actions_audit ("
        " request_id, kind, parent_id, action_type, source, params_json,"
        " decision, reason_code, nominal_tier, effective_tier, detail,"
        " connector_ok, error, payload_json, approval_id, undo_until, undo_of, created_at,"
        " policy_version, protocol, budget_json, outcome,"
        " params_provenance, payload_provenance, malformed_kind, canon_schema"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            intent_row["request_id"],
            kind,
            int(intent_row["id"]),
            intent_row["action_type"],
            intent_row["source"],
            intent_row["params_json"],  # already-frozen bytes; never re-serialized
            Decision.FAILED.value,
            reason.value,
            int(intent_row["nominal_tier"]),
            int(intent_row["effective_tier"]),
            detail,
            None,
            None,
            None,
            None,
            None,
            intent_row["undo_of"],
            to_iso(now),
            policy_version,
            AADP_PROTOCOL,
            # No budget: a reclamation row records a permit whose deadline passed, not
            # a cap denial. ND-003's object is present iff the verdict IS the cap.
            None,
            None,
            # The params bytes are copied verbatim from the intent row, so this row
            # inherits that row's provenance rather than claiming one of its own.
            intent_row["params_provenance"] if "params_provenance" in intent_row.keys() else None,
            None,
            # A reservation disposition is not a malformed denial and involves no
            # canonicalization: both fields are absent because nothing produced them.
            None,
            None,
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
        payload = (
            json.loads(result["payload_json"], parse_float=Decimal)
            if result["payload_json"]
            else None
        )
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


# ---------------------------------------------------------------------------
# Group commit for RESULT rows only.
#
# Invariant 9 requires the *intent* to be durable before the permit is returned,
# so intent writes stay synchronous and are never buffered. Result rows are a
# different risk: losing one on a crash leaves an intent with no result, which is
# exactly the recoverable, detectable state the invariant already demands. The
# failure direction is "we do not know yet", never "this was authorized".
#
# Exactly-once reporting is preserved: a duplicate is caught in the buffer by the
# same (request_id, kind) key the database UNIQUE constraint enforces, so the
# second report is rejected at call time rather than at flush time.
#
# Off by default. Buffering trades durability for throughput and that is an
# operator's decision, not a default.
# ---------------------------------------------------------------------------


class _ResultBuffer:
    __slots__ = ("rows", "events", "keys")

    def __init__(self) -> None:
        self.rows: list[tuple[object, ...]] = []
        self.events: list[tuple[str, str]] = []
        self.keys: set[tuple[str, str]] = set()


def _buffer(conn: sqlite3.Connection) -> _ResultBuffer:
    buf = getattr(conn, "_audit_buffer", None)
    if buf is None:
        buf = _ResultBuffer()
        conn._audit_buffer = buf  # type: ignore[attr-defined]
    return buf


def buffered_len(conn: sqlite3.Connection) -> int:
    return len(_buffer(conn).rows)


def append_buffered(
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
    undo_of: int | None = None,
    event_topic: str | None = None,
    event_payload: str | None = None,
    outcome: str | None = None,
) -> None:
    """Queue a result row. Raises on a duplicate report, as the UNIQUE constraint would."""
    buf = _buffer(conn)
    key = (str(request.request_id), kind)
    if key in buf.keys:
        raise sqlite3.IntegrityError(
            f"UNIQUE constraint failed: actions_audit.request_id, actions_audit.kind "
            f"({key[0]}, {kind}) already reported"
        )
    row = conn.execute("SELECT version_hash FROM policy_current WHERE id=1").fetchone()
    buf.keys.add(key)
    params_bytes, params_provenance = frozen_params(request)
    buf.rows.append(
        (
            str(request.request_id),
            kind,
            parent_id,
            request.action_type,
            request.source.value,
            params_bytes,
            decision.decision.value,
            decision.reason_code.value,
            int(decision.nominal_tier),
            int(decision.effective_tier),
            decision.detail,
            None if connector_ok is None else int(connector_ok),
            error,
            None if payload is None else dumps_json_value(payload),
            None,
            None,
            undo_of,
            to_iso(now),
            row["version_hash"] if row else None,
            AADP_PROTOCOL,
            None if decision.budget is None else dumps_json_value(decision.budget.model_dump()),
            outcome,
            params_provenance,
            None if payload is None else Provenance.SERIALIZED.value,
        )
    )
    if event_topic is not None and event_payload is not None:
        buf.events.append((event_topic, event_payload))


def flush(conn: sqlite3.Connection) -> int:
    """Write every queued result row in one transaction. Returns rows written."""
    buf = _buffer(conn)
    if not buf.rows:
        return 0
    rows, events = buf.rows, buf.events
    buf.rows, buf.events, buf.keys = [], [], set()
    with tx(conn):
        conn.executemany(
            "INSERT INTO actions_audit ("
            " request_id, kind, parent_id, action_type, source, params_json,"
            " decision, reason_code, nominal_tier, effective_tier, detail,"
            " connector_ok, error, payload_json, approval_id, undo_until, undo_of,"
            " created_at, policy_version, protocol, budget_json, outcome,"
            " params_provenance, payload_provenance"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        if events:
            stamp = to_iso(now_utc())
            conn.executemany(
                "INSERT INTO events (topic, payload_json, created_at) VALUES (?, ?, ?)",
                [(t, p, stamp) for t, p in events],
            )
    return len(rows)
