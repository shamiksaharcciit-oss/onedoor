"""One-tap undo for executed Tier-1 actions (15-minute window).

Undo is not a special case in the executor — it submits the policy's registered
compensating command back through the full pipeline as a normal ``ActionRequest``
(``source=UNDO``), so it is itself bounds-checked, capped, and audited. The
linkage back to the original action is carried by ``parent_audit_id`` -> the audit
``undo_of`` column, which also prevents double-undo.
"""

from __future__ import annotations

import json
from datetime import datetime
from sqlite3 import Connection
from uuid import uuid4

from onedoor.guardrail.errors import UndoError
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute
from onedoor.guardrail.models import ActionRequest, ActionResult, JsonValue, Source
from onedoor.guardrail.policy import PolicyStore
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.clock import from_iso, now_utc


def undo(
    audit_id: int,
    *,
    conn: Connection,
    registry: ConnectorRegistry,
    config: EngineConfig,
    session_id: str | None = None,
    now: datetime | None = None,
    policy_store: PolicyStore | None = None,
) -> ActionResult:
    """Reverse an executed Tier-1 action identified by its ``exec_intent`` audit id."""
    when = now or now_utc()
    store = policy_store or PolicyStore()

    intent = conn.execute(
        "SELECT * FROM actions_audit WHERE id=? AND kind='exec_intent'", (audit_id,)
    ).fetchone()
    if intent is None:
        raise UndoError(f"no executed action with audit id {audit_id}")
    if not intent["undo_until"]:
        raise UndoError("action is not undoable")
    if when >= from_iso(intent["undo_until"]):
        raise UndoError("undo window expired")

    success = conn.execute(
        "SELECT 1 FROM actions_audit WHERE parent_id=? AND kind='exec_result' AND connector_ok=1",
        (audit_id,),
    ).fetchone()
    if success is None:
        raise UndoError("original action did not execute successfully")

    already = conn.execute(
        "SELECT 1 FROM actions_audit WHERE undo_of=? AND connector_ok=1", (audit_id,)
    ).fetchone()
    if already is not None:
        raise UndoError("action already undone")

    policy = store.get(conn, intent["action_type"])
    if not policy.compensating_command:
        raise UndoError("no compensating command registered")

    original_params: dict[str, JsonValue] = json.loads(intent["params_json"])
    reverse = ActionRequest(
        request_id=uuid4(),
        action_type=policy.compensating_command,
        params=original_params,
        source=Source.UNDO,
        rationale=f"undo of audit {audit_id}",
        session_id=session_id,
        created_at=when,
        parent_audit_id=audit_id,
    )
    return evaluate_and_execute(
        reverse, conn=conn, registry=registry, config=config, now=when, policy_store=store
    )
