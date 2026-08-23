"""The append-only audit writer — the ONLY writer to ``actions_audit``.

There are deliberately no update/delete methods here; the table's triggers reject
those structurally as a second line of defense (invariant 5).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple, Protocol
from uuid import UUID

from onedoor._vendor.canonical import canon_decimal
from onedoor.guardrail import digests, signing
from onedoor.guardrail import preimage as preimage_module
from onedoor.guardrail.models import (
    ActionRequest,
    ActionResult,
    CheckId,
    Decision,
    JsonValue,
    PolicyDecision,
    Source,
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


CHAIN_ENABLED_KEY = "chain.enabled"
"""The one key that says whether rows are chained.

Declared here and re-exported by `chain.py` rather than spelled in both -- two string
constants that must agree is X-14's shape, and a chain that writes under one key while
a verifier reads another would report every row as unchained while the store was full
of hashes.

Until `chain.enable()` sets it, every row's chain columns stay NULL and the engine
behaves exactly as it did. Chaining is an opt-in, audited, once-only event, not
something a deployment acquires by upgrading.
"""


def chaining_on(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM config WHERE key=?", (CHAIN_ENABLED_KEY,)).fetchone()
    return row is not None and row["value"] == "1"


SIGNING_KEY = "chain.signing_key_path"
"""Where the deployer's private key lives, recorded in `config` when signing is enabled.

The PATH, never the key. No private key material enters this database, this repository
or any receipt (R037 §2).
"""


def _signing_key(conn: sqlite3.Connection) -> object | None:
    """The loaded signing key for this store, or None when signing is off.

    Cached on the connection: loading a PEM per row would be wasteful and, worse, would
    make the signing identity re-derivable mid-run if the file changed underneath.
    """
    cached = getattr(conn, "_onedoor_signing_key", "unset")
    if cached != "unset":
        return cached
    row = conn.execute("SELECT value FROM config WHERE key=?", (SIGNING_KEY,)).fetchone()
    key = None if row is None else signing.load_private_key(str(row["value"]))
    conn._onedoor_signing_key = key  # type: ignore[attr-defined]
    return key


def _sign(conn: sqlite3.Connection, values: dict[str, object]) -> None:
    """Attach a signature over the row's hash, if this store signs.

    Per-row over `row_hash` (R037 §2): the signature attests the sealed bytes and
    nothing else, which is also why `sig`/`key_id`/`alg` are excluded from the preimage
    -- a signature cannot precede the hash it attests.
    """
    key = _signing_key(conn)
    if key is None:
        return
    values["sig"] = key.sign(str(values["row_hash"]))  # type: ignore[attr-defined]
    values["key_id"] = key.key_id  # type: ignore[attr-defined]
    values["alg"] = signing.ALGORITHM


def _stamp_chain(conn: sqlite3.Connection, values: dict[str, object], tip: _Tip) -> _Tip:
    """Fill `seq`, `prev_hash` and `row_hash` in place, and return the new tip.

    MUST be called inside the caller's `BEGIN IMMEDIATE`. That is not a comment, it is
    the chain's whole correctness argument: `tx()` takes the write lock at entry, so
    between reading the tip and writing the successor no other connection can insert.
    Outside a transaction, two appends could read the same tip and both claim it as
    their predecessor, and the fork would be invisible until a verifier walked it.

    Threading the tip through rather than re-reading it per row is what lets the
    buffered path chain a batch: `flush` reads once and stamps in order.
    """
    values["seq"] = tip.seq + 1
    values["prev_hash"] = tip.row_hash
    digest = preimage_module.row_hash(values)
    values["row_hash"] = digest
    _sign(conn, values)
    # The four content-addressed digests (ND-017 / M1). Computed at write time because
    # they live on an append-only table: a column that cannot be UPDATEd must be right
    # when the row is born or it is never right at all.
    values.update(digests.digests_for(_DigestRow(values), closure=_closure(conn)))
    return _Tip(seq=tip.seq + 1, row_hash=digest)


class _DigestRow:
    """A row-shaped view of values not yet inserted.

    The digest builders read a `sqlite3.Row`, and at stamping time the row does not
    exist yet -- the same reason `row_hash` is computed from a mapping. Two accessors is
    the whole contract.
    """

    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def __getitem__(self, name: str) -> object:
        return self._values.get(name)

    def keys(self) -> list[str]:
        return list(self._values)


def _closure(conn: sqlite3.Connection) -> str:
    """Does this deployment publish roots? A declaration, known when the row is sealed.

    `anchor-closed` says a verifier will be able to close the trust set on a root held
    outside the store; `store-closed` says they are trusting this store. Not a claim
    that a particular anchor exists -- anchoring is periodic, and a fresh row is normally
    not yet covered.
    """
    row = conn.execute("SELECT value FROM config WHERE key=?", ("anchor.cadence",)).fetchone()
    return digests.ANCHOR_CLOSED if row is not None else digests.STORE_CLOSED


class _Tip(NamedTuple):
    """The last chained row: its ordinal and its hash."""

    seq: int
    row_hash: str


def _read_tip(conn: sqlite3.Connection) -> _Tip:
    """The chain's current end, or the genesis position when nothing is chained yet."""
    row = conn.execute(
        "SELECT seq, row_hash FROM actions_audit WHERE seq IS NOT NULL ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if row is None:
        # seq 0 is the position BEFORE the first chained row, so the first row gets
        # seq 1 and prev_hash = the ruled genesis sentinel.
        return _Tip(seq=0, row_hash=preimage_module.GENESIS_PREV_HASH)
    return _Tip(seq=int(row["seq"]), row_hash=str(row["row_hash"]))


_INSERT_COLUMNS: tuple[str, ...] = (
    "request_id",
    "kind",
    "parent_id",
    "action_type",
    "source",
    "params_json",
    "decision",
    "reason_code",
    "nominal_tier",
    "effective_tier",
    "detail",
    "connector_ok",
    "error",
    "payload_json",
    "approval_id",
    "undo_until",
    "undo_of",
    "created_at",
    "policy_version",
    "protocol",
    "budget_json",
    "outcome",
    "params_provenance",
    "payload_provenance",
    "malformed_kind",
    "canon_schema",
    "opaque_class",
    "approval_ref_status",
    "preimage_version",
    "e_digest",
    "i_digest",
    "t_digest",
    "v_digest",
    "sig",
    "key_id",
    "alg",
    "seq",
    "prev_hash",
    "row_hash",
)
"""Every column an append writes.

Named columns and named placeholders, deliberately. The positional form this replaced
carried a 27-item column list beside a 27-item value tuple, and getting them out of
step is not a hypothetical: it happened twice while building `0.4.x` -- once producing
`sqlite3.ProgrammingError: statement uses 26, 24 supplied`, once silently shifting a
value into the wrong column. Two lists that must agree, which X-14 has a name for.
"""

_INSERT_SQL = (
    f"INSERT INTO actions_audit ({', '.join(_INSERT_COLUMNS)}) "
    f"VALUES ({', '.join(':' + c for c in _INSERT_COLUMNS)})"
)


def _blank_row() -> dict[str, object]:
    """Every insertable column, NULL. Callers fill what they mean and nothing else.

    Starting from a complete blank rather than from a partial dict is what makes a
    forgotten column a NULL -- an honest absence the preimage encodes as ABSENT --
    instead of a KeyError at insert time or, worse, a value landing in a neighbour.
    """
    return dict.fromkeys(_INSERT_COLUMNS, None)


def _insert(conn: sqlite3.Connection, values: dict[str, object]) -> int:
    cur = conn.execute(_INSERT_SQL, values)
    return int(cur.lastrowid or 0)


def append(
    conn: sqlite3.Connection,
    request: RowSource,
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
    opaque_class: str | None = None,
    frozen: tuple[str | bytes, str | None] | None = None,
    approval_ref_status: str | None = None,
) -> int:
    """Insert one audit row and return its id.

    Every row carries the hash of the policy set in force, so a verdict can be
    re-derived against the exact rules that produced it (AADP section 10). The
    policy table is upserted in place; without this stamp, editing policy silently
    destroys the ability to check any earlier decision.
    """
    values = _row_values(
        conn,
        request,
        decision,
        kind=kind,
        now=now,
        parent_id=parent_id,
        connector_ok=connector_ok,
        error=error,
        payload=payload,
        approval_id=approval_id,
        undo_until=undo_until,
        undo_of=undo_of,
        outcome=outcome,
        malformed_kind=malformed_kind,
        canon_schema=canon_schema,
        opaque_class=opaque_class,
        frozen=frozen,
        approval_ref_status=approval_ref_status,
    )
    if chaining_on(conn):
        _stamp_chain(conn, values, _read_tip(conn))
    return _insert(conn, values)


class RowSource(Protocol):
    """The three fields a row needs from whatever asked for the action.

    `ActionRequest` satisfies this, and so does `ND-010`'s `RebuiltIntent` -- which is
    the point: a rebuilt permit supplies exactly what the row needs and **nothing it
    would have to invent**. It has no `rationale` and no `cost_eur` because the ledger
    does not store them, and a type that cannot express a value cannot default one.
    """

    @property
    def request_id(self) -> object: ...

    @property
    def action_type(self) -> str: ...

    @property
    def source(self) -> Source: ...


def _row_values(
    conn: sqlite3.Connection,
    request: RowSource,
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
    opaque_class: str | None = None,
    frozen: tuple[str | bytes, str | None] | None = None,
    approval_ref_status: str | None = None,
) -> dict[str, object]:
    """One row's column values, shared by the immediate and buffered paths.

    Both paths building the same row from one function is what makes the chain
    testable: the buffered and unbuffered routes must produce IDENTICAL `row_hash`
    values for the same sequence of appends, and they cannot if each assembles its own
    idea of what a row contains.
    """
    stamp = conn.execute("SELECT version_hash FROM policy_current WHERE id=1").fetchone()
    params_bytes: str | bytes
    params_provenance: str | None
    if frozen is None:
        # Only a live ActionRequest can be asked for its frozen params; a rebuilt
        # permit always supplies them, which the assert makes a type error rather
        # than a runtime surprise.
        assert isinstance(request, ActionRequest)
        params_bytes, params_provenance = frozen_params(request)
    else:
        # A REBUILT permit supplies the intent row's own bytes and its own provenance
        # (ND-010). Without this, `frozen_params` would re-serialise -- it returns
        # `params_raw` verbatim or falls back to serialising `params`, and only a live
        # ingress sets `params_raw`. A result row written after a restart would then
        # stamp `serialized` on bytes that arrived `received`: a wrong label on a
        # receipt, written at the moment the system is least observed.
        #
        # `append_expiry` has always done exactly this for reclamation rows. Same
        # discipline, now reachable by the one other caller that needs it.
        params_bytes, params_provenance = frozen
    values = _blank_row()
    values.update(
        {
            "request_id": str(request.request_id),
            "kind": kind,
            "parent_id": parent_id,
            "action_type": request.action_type,
            "source": request.source.value,
            "params_json": params_bytes,
            "decision": decision.decision.value,
            "reason_code": decision.reason_code.value,
            "nominal_tier": int(decision.nominal_tier),
            "effective_tier": int(decision.effective_tier),
            "detail": decision.detail,
            "connector_ok": None if connector_ok is None else int(connector_ok),
            "error": error,
            "payload_json": None if payload is None else dumps_json_value(payload),
            "approval_id": approval_id,
            "undo_until": to_iso(undo_until) if undo_until else None,
            "undo_of": undo_of,
            "created_at": to_iso(now),
            "policy_version": stamp["version_hash"] if stamp else None,
            "protocol": AADP_PROTOCOL,
            # E7: PERSISTED, not merely returned. cap_value collapses the day and
            # month windows, so a denial that cannot name its window is not
            # re-derivable from the evidence store alone.
            "budget_json": (
                None if decision.budget is None else dumps_json_value(decision.budget.model_dump())
            ),
            "outcome": outcome,
            "params_provenance": params_provenance,
            # A payload is produced by the enforcement point after acting, and every
            # packaged PEP hands us objects rather than bytes, so it is serialized
            # here. If a PEP ever forwards raw payload bytes this becomes RECEIVED.
            "payload_provenance": None if payload is None else Provenance.SERIALIZED.value,
            "malformed_kind": malformed_kind,
            "canon_schema": canon_schema,
            "opaque_class": opaque_class,
            "approval_ref_status": approval_ref_status,
            # The version HINT (R035 §1). Excluded from the hash -- the authoritative
            # statement is the magic string inside the preimage -- so it is stamped
            # here rather than computed, and a row whose hint disagrees with how it
            # was sealed fails verification under the version it names.
            "preimage_version": preimage_module.CURRENT_VERSION,
        }
    )
    return values


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
    stamp = conn.execute("SELECT version_hash FROM policy_current WHERE id=1").fetchone()
    values = _blank_row()
    values.update(
        {
            "request_id": intent_row["request_id"],
            "kind": kind,
            "parent_id": int(intent_row["id"]),
            "action_type": intent_row["action_type"],
            "source": intent_row["source"],
            # Already-frozen bytes; never re-serialized (E10).
            "params_json": intent_row["params_json"],
            "decision": Decision.FAILED.value,
            "reason_code": reason.value,
            "nominal_tier": int(intent_row["nominal_tier"]),
            "effective_tier": int(intent_row["effective_tier"]),
            "detail": detail,
            "undo_of": intent_row["undo_of"],
            "created_at": to_iso(now),
            "policy_version": stamp["version_hash"] if stamp else None,
            "protocol": AADP_PROTOCOL,
            # No budget: a reclamation row records a permit whose deadline passed, not
            # a cap denial. ND-003's object is present iff the verdict IS the cap.
            #
            # Everything not named here stays NULL by way of `_blank_row()`, and the
            # preimage encodes NULL as ABSENT -- an honest "no statement was made"
            # rather than an empty value someone has to interpret.
            "params_provenance": (
                # The params bytes are copied verbatim from the intent row, so this row
                # inherits that row's provenance rather than claiming one of its own.
                intent_row["params_provenance"]
                if "params_provenance" in intent_row.keys()
                else None
            ),
        }
    )
    if chaining_on(conn):
        # A disposition row is a ledger event like any other. Leaving it unchained
        # would put a hole in the chain at exactly the rows that record budget going
        # back -- the ones an auditor would most want covered.
        _stamp_chain(conn, values, _read_tip(conn))
    return _insert(conn, values)


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
        self.rows: list[dict[str, object]] = []
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
    request: RowSource,
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
    frozen: tuple[str | bytes, str | None] | None = None,
) -> None:
    """Queue a result row. Raises on a duplicate report, as the UNIQUE constraint would."""
    buf = _buffer(conn)
    key = (str(request.request_id), kind)
    if key in buf.keys:
        raise sqlite3.IntegrityError(
            f"UNIQUE constraint failed: actions_audit.request_id, actions_audit.kind "
            f"({key[0]}, {kind}) already reported"
        )
    buf.keys.add(key)
    # The SAME builder the immediate path uses. Both paths assembling their own idea
    # of a row is what let them drift before; now a row is a row, and the test that
    # the two routes produce IDENTICAL row_hash values has something to be true about.
    #
    # The chain is stamped at FLUSH, not here: a queued row has no position yet, and
    # guessing one would fork the chain the moment two buffers interleaved.
    buf.rows.append(
        _row_values(
            conn,
            request,
            decision,
            kind=kind,
            now=now,
            parent_id=parent_id,
            connector_ok=connector_ok,
            error=error,
            payload=payload,
            undo_of=undo_of,
            outcome=outcome,
            frozen=frozen,
        )
    )
    if event_topic is not None and event_payload is not None:
        buf.events.append((event_topic, event_payload))


def flush(conn: sqlite3.Connection) -> int:
    """Write every queued result row in one transaction. Returns rows written.

    **N2, decided rather than deferred.** A chain is sequential and an `executemany`
    is not, so one of them had to give. Refusing group commit while chaining would
    have made a performance feature and an integrity feature mutually exclusive, and
    every deployer who wanted both would quietly turn off the one that is harder to
    notice missing. Instead the chain is stitched here, in row order, inside the
    transaction this function already opens: read the tip once, stamp each row against
    the one before it, then insert them together.

    The tip is read INSIDE the transaction. `tx()` is `BEGIN IMMEDIATE`, so no other
    connection can insert between that read and the write, and the batch cannot fork
    the chain.

    **What buffering does change, and it is not a defect:** deferring result rows
    changes the ledger's ROW ORDER, so a buffered store's chain differs from an
    immediate store's for the same actions. `seq` and `prev_hash` are in the preimage;
    different positions, different hashes. The invariant that holds -- and the one
    worth asserting -- is that the preimage does not depend on which path wrote a row,
    which `tests/guardrail/test_chain.py` checks by holding the position-determined
    fields fixed and comparing the content.
    """
    buf = _buffer(conn)
    if not buf.rows:
        return 0
    rows, events = buf.rows, buf.events
    buf.rows, buf.events, buf.keys = [], [], set()
    with tx(conn):
        if chaining_on(conn):
            tip = _read_tip(conn)
            for values in rows:
                tip = _stamp_chain(conn, values, tip)
        conn.executemany(_INSERT_SQL, rows)
        if events:
            stamp = to_iso(now_utc())
            conn.executemany(
                "INSERT INTO events (topic, payload_json, created_at) VALUES (?, ?, ?)",
                [(t, p, stamp) for t, p in events],
            )
    return len(rows)
