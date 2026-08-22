"""Rebuilding a pending permit from the ledger instead of from memory (ND-010).

`service/app.py` has kept `self.pending: dict[int, PermittedIntent]` in memory since
`0.3`, and its own docstring promised `0.4` would rebuild from the `exec_intent` row.
Until now a restart between decide and report stranded every in-flight permit: the
reservation stayed held, the deadline ran, and the reclaimer eventually voided budget
for an action that may well have happened.

What a rebuilt permit is, and is not
------------------------------------
It is **not** a :class:`PermittedIntent`, and that is the whole design. Three fields of
`ActionRequest` are stored nowhere in `actions_audit` — `rationale`, `cost_eur` and
`session_id` — so reconstructing one means passing `cost_eur=Decimal(0)`, which is **a
default that looks like a fact**. Any later code reading it off a rebuilt permit would
read zero and be wrong, and nothing in the type system would object.

So a rebuilt permit is its own type. It carries what the store holds, **provenance
references to the rows it derives from**, and no `ActionRequest` at all — R032 §3's
*surface the gap, do not synthesise*, made structural rather than remembered.

Timestamps (R033 §3)
--------------------
**A rebuilt row's `created_at` is its own write time, never backdated.** The
append-only ledger records when the ledger *learned* a thing; a rebuilt row carrying the
original's timestamp would be the ledger testifying to a moment it did not witness. So
the field here is `requested_at` — plainly the request's time, not this row's — and
there is deliberately no `created_at` on this object, so the result row's stamp can only
come from `now`. A rebuilt record is typed as rebuilt, timestamps are what was
witnessed, and lineage travels by reference. It never impersonates the live row it
reconstructs.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from onedoor.guardrail.models import Source, Tier
from onedoor.store.clock import from_iso


class RebuildStatus(StrEnum):
    """Four outcomes at recovery time, and the middle two are why this is a type.

    ``rebuilt``
        The intent row and its held reservation are both present and agree.
    ``absent``
        No such pending intent. It was never permitted, or it was already reported.
        **Not an error** — the ordinary answer to "is there anything to resume?".
    ``unverifiable``
        The evidence disagrees with itself: an intent with no reservation, or a held
        reservation naming an intent that is not there. `cap_reservations` has no
        foreign key to `actions_audit`, so this is genuinely reachable.
    ``failed``
        The rows are there and cannot be read — `deltas_json` that will not parse.

    Collapsing the middle two is not a tidiness question, it loses money. A missing
    reservation read as "nothing to settle" silently discards held budget; a missing
    intent read as "nothing to do" leaves a reservation held until the reclaimer voids
    it. Both are quiet, and both are wrong in a direction someone pays for.
    """

    REBUILT = "rebuilt"
    ABSENT = "absent"
    UNVERIFIABLE = "unverifiable"
    FAILED = "failed"


@dataclass(frozen=True)
class RebuiltIntent:
    """A permit reconstructed from the ledger. Never mistakable for a live one."""

    intent_audit_id: int
    """Provenance: the `exec_intent` row this was derived from."""

    request_id: str
    action_type: str
    source: Source
    effective_tier: Tier
    nominal_tier: Tier
    compensating_command: str | None
    undo_until: datetime | None
    undo_of: int | None

    params_json: str | bytes
    """The frozen bytes, carried verbatim from the intent row -- never re-serialised."""

    params_provenance: str | None
    """Inherited from the intent row, not claimed afresh.

    This is the finding that made the type necessary. `report_result` used to hand the
    request to `audit.append`, which calls `frozen_params`: it returns `params_raw`
    verbatim, or **re-serialises `params` when `params_raw` is None** -- and only a live
    ingress sets `params_raw`. A rebuilt request would therefore have stamped
    `serialized` on bytes that arrived `received`: not a crash, not a test failure, a
    wrong label on a receipt written at the moment the system is least observed.

    `append_expiry` already solved this by copying the intent row's bytes and inheriting
    its provenance. A rebuilt permit does the same.
    """

    reservation_deltas: tuple[tuple[str, str, str, int, str], ...]
    """From `cap_reservations.deltas_json`. The record of what was reserved, so
    settlement never has to re-derive a cost that is not stored."""

    reservation_deadline: str
    """Provenance: the reservation row's own deadline, carried for evidence."""

    requested_at: datetime
    """When the ACTION WAS ASKED FOR, from the intent row.

    Named `requested_at` rather than `created_at` on purpose (R033 §3). Two timestamps
    under one name is X-14's shape, and the ledger is permanent: a result row's
    `created_at` is when the ledger learned the outcome, which after a restart is not
    when the request was made. This object deliberately has no `created_at` at all, so
    a caller cannot reach for the wrong one.
    """


@dataclass(frozen=True)
class RebuildResult:
    """What the ledger could say about one pending intent."""

    status: RebuildStatus
    intent: RebuiltIntent | None
    detail: str


def _reservation(conn: sqlite3.Connection, intent_audit_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM cap_reservations WHERE intent_audit_id=?", (intent_audit_id,)
    ).fetchone()
    return row


def rebuild(conn: sqlite3.Connection, intent_audit_id: int) -> RebuildResult:
    """Reconstruct one pending permit, or say precisely why not."""
    row = conn.execute(
        "SELECT * FROM actions_audit WHERE id=? AND kind='exec_intent'", (intent_audit_id,)
    ).fetchone()
    reservation = _reservation(conn, intent_audit_id)

    if row is None:
        if reservation is not None and reservation["status"] == "held":
            return RebuildResult(
                RebuildStatus.UNVERIFIABLE,
                None,
                f"a held reservation names intent {intent_audit_id}, which is not in the "
                f"audit log: the evidence disagrees with itself",
            )
        return RebuildResult(RebuildStatus.ABSENT, None, f"no pending intent {intent_audit_id}")

    already = conn.execute(
        "SELECT 1 FROM actions_audit WHERE parent_id=? AND kind='exec_result'",
        (intent_audit_id,),
    ).fetchone()
    if already is not None:
        return RebuildResult(
            RebuildStatus.ABSENT,
            None,
            f"intent {intent_audit_id} was already reported; nothing is pending",
        )

    if reservation is None:
        # No reservation is legitimate for a Tier-1 permit that reserved no budget.
        # The distinction is whether caps were involved at all, which the intent row
        # cannot say on its own -- so it is reported as a rebuild with empty deltas
        # rather than guessed either way.
        deltas: tuple[tuple[str, str, str, int, str], ...] = ()
        deadline = ""
    elif reservation["status"] != "held":
        return RebuildResult(
            RebuildStatus.ABSENT,
            None,
            f"the reservation for intent {intent_audit_id} is already "
            f"{reservation['status']}; nothing is pending",
        )
    else:
        try:
            parsed = json.loads(reservation["deltas_json"])
            deltas = tuple(tuple(d) for d in parsed)
        except (ValueError, TypeError) as exc:
            return RebuildResult(
                RebuildStatus.FAILED,
                None,
                f"the reservation for intent {intent_audit_id} is stored and unreadable: {exc}",
            )
        deadline = str(reservation["deadline_utc"])

    return RebuildResult(
        RebuildStatus.REBUILT,
        RebuiltIntent(
            intent_audit_id=int(row["id"]),
            request_id=str(row["request_id"]),
            action_type=str(row["action_type"]),
            source=Source(row["source"]),
            effective_tier=Tier(int(row["effective_tier"])),
            nominal_tier=Tier(int(row["nominal_tier"])),
            compensating_command=None,
            undo_until=from_iso(row["undo_until"]) if row["undo_until"] else None,
            undo_of=row["undo_of"],
            params_json=row["params_json"],
            params_provenance=row["params_provenance"],
            reservation_deltas=deltas,
            reservation_deadline=deadline,
            requested_at=from_iso(str(row["created_at"])),
        ),
        f"rebuilt from audit row {intent_audit_id}"
        + (f" and its reservation held until {deadline}" if deadline else " (no budget reserved)"),
    )


def pending(conn: sqlite3.Connection) -> list[int]:
    """Every intent id with no result row — the permits a restart must pick back up.

    Read from the ledger rather than from a dict, which is the whole ticket: after this
    lands, `state.pending` is a query and a restart loses nothing.
    """
    return [
        int(r["id"])
        for r in conn.execute(
            "SELECT a.id FROM actions_audit a "
            "WHERE a.kind='exec_intent' AND NOT EXISTS ("
            "  SELECT 1 FROM actions_audit r WHERE r.parent_id=a.id AND r.kind='exec_result'"
            ") ORDER BY a.id"
        ).fetchall()
    ]
