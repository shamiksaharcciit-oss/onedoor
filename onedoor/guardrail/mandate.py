"""Mandate-layer deferral (AADP -03 §8.1).

A PDP consuming a mandate-layer verdict must not return `permit` while that verdict
denies or defers the action. onedoor is the PDP here, never the mandate authority: a
deployment supplies a resolver (:data:`MandateResolver`) that answers DENY / PENDING /
PERMIT for a request, and this module handles what onedoor itself owns -- turning a
PENDING into a Tier-3-shaped approval that **only a verified ratification can
resolve**, never an onedoor admin key and never a timeout.

`core_digest` is onedoor's OWN identifier for a pending mandate decision, not a
byte-for-byte implementation of AAE's (`draft-kroehl-agentic-trust-aae` §2.5.3, which
this repository does not vendor and whose RFC 8785 JSON Canonicalization Scheme this
module does not implement). It serves the same purpose §8.1 needs -- a ratification
names the exact record it resolves, and cannot be moved to another one -- using
onedoor's own, already-vendored canonical form (`onedoor._vendor.canonical`) instead of
introducing a second canonicalization scheme into a codebase that has spent real effort
keeping to one. Disclosed rather than implied: a ratification built to this
digest is not an AAE-interoperable artifact.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from onedoor._vendor.canonical import canonical_bytes, digest_obj
from onedoor.guardrail import audit
from onedoor.guardrail.models import ActionRequest, CheckId, Decision, JsonValue
from onedoor.store.clock import to_iso

CORE_DIGEST_KIND = "onedoor/mandate-core-digest/1"


class MandateVerdict(StrEnum):
    """What the mandate authority says about one request (AAE §6.1's three values).

    onedoor only branches on DENY and PENDING; PERMIT means the mandate layer has no
    objection and the request continues through onedoor's own pipeline unchanged.
    """

    PERMIT = "permit"
    DENY = "deny"
    PENDING = "pending"


class MandateResolver(Protocol):
    """A deployment-supplied callable: what does the mandate authority say?

    Never built into onedoor and never called over the network by this module --
    key and network fetches for mandate resolution are deliberately kept out of this
    component. A deployment wires its own resolver into
    `EngineConfig.mandate_resolver`; tests supply a stub.
    """

    def __call__(self, request: ActionRequest) -> MandateVerdict: ...


def core_digest(request_id: object, action_type: str, params: dict[str, JsonValue]) -> str:
    """onedoor's identifier for one pending mandate decision.

    Computed from the same three facts that make a request unique -- `request_id`
    alone would already be enough, since onedoor mints a fresh one per decide, but
    `action_type` and `params_digest` are included so the digest states what it is
    about rather than resolving to an opaque, unauditable token. A ratification
    naming this digest cannot be replayed onto a different record: that record's own
    request_id differs, so its digest differs, and the lookup by digest simply finds
    nothing.
    """
    params_digest = hashlib.sha256(_params_bytes(params)).hexdigest()
    return digest_obj(
        {
            "kind": CORE_DIGEST_KIND,
            "request_id": str(request_id),
            "action_type": action_type,
            "params_digest": params_digest,
        }
    )


def _params_bytes(params: dict[str, JsonValue]) -> bytes:
    """The same params, canonically rendered -- not the frozen received bytes.

    E10's verbatim discipline is for the audit row, not for this digest: two callers
    must compute the identical digest for the identical logical request regardless
    of key order or number spelling on the wire, which is exactly what onedoor's
    already-vendored canonical form is for.
    """
    return canonical_bytes(_canon(params))


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


class RatificationStatus(StrEnum):
    """Every outcome a ratification attempt can have, each auditable on its own."""

    RATIFIED = "ratified"
    UNKNOWN_DIGEST = "unknown_digest"
    """No pending mandate approval carries this digest -- never distinguished
    from a wrong-key attempt in behaviour, only in evidence, for the same reason
    approval_ref's failure modes all look alike from outside."""
    WRONG_KEY = "wrong_key"
    ALREADY_RESOLVED = "already_resolved"
    """The digest names a real record, but it was already ratified or is no longer
    pending (expired, denied). A lost race lands here too -- consuming is a CAS."""


@dataclass(frozen=True)
class RatificationResult:
    authorised: bool
    status: RatificationStatus
    approval_id: int | None = None
    request: ActionRequest | None = None
    """The original request, present iff `authorised` -- for the caller to resume
    exactly as `/v1/approvals/{id}/approve` resumes an admin-approved one: a NEW
    request_id, `approved_override=True`, full re-evaluation. `ratify` does not
    resume it itself, the same separation `approvals.cas_approve` already has from
    its own callers."""


def _audit_attempt(
    conn: sqlite3.Connection, approval_id: int, now: datetime, status: RatificationStatus
) -> None:
    """Every ratification attempt against a real record is audited, refused or not.

    Linked back to the PROPOSED decision row via `parent_id`, the same shape
    `append_expiry` already uses for reservation dispositions -- a ratification
    attempt is a lifecycle event about that row, not a fact with nowhere to live.
    """
    intent_row = conn.execute(
        "SELECT * FROM actions_audit WHERE approval_id=? ORDER BY id DESC LIMIT 1",
        (approval_id,),
    ).fetchone()
    if intent_row is None:  # pragma: no cover - defensive; every mandate approval has one
        return
    audit.append_expiry(
        conn,
        intent_row,
        now,
        detail=f"mandate ratification attempt: {status.value}",
        kind="mandate_ratification",
        reason=CheckId.EXTERNAL_AUTHORIZATION,
        decision=Decision.PROPOSED if status is RatificationStatus.RATIFIED else Decision.DENIED,
        # A fresh id per attempt: more than one attempt (a replay, a wrong key, a
        # retry) can target the same approval, and actions_audit's UNIQUE(request_id,
        # kind) backstop would refuse a second row sharing the intent's own id.
        request_id=str(uuid4()),
    )


def ratify(
    conn: sqlite3.Connection,
    *,
    core_digest_value: str,
    signature_hex: str,
    authority_public_key: bytes,
    now: datetime,
) -> RatificationResult:
    """Resolve a mandate-pending approval, or refuse it -- never anything else.

    MUST be called inside the caller's transaction (the same `BEGIN IMMEDIATE`
    discipline `approval_ref.resolve` uses): consumption is a CAS, and the
    transaction is what makes a race decide itself rather than double-grant.

    The signature is checked against `authority_public_key` BEFORE the row is
    touched -- a forged signature must never consume a real pending approval, even
    to mark it "attempted". Verification failure and "no such digest" both refuse
    identically in behaviour (a bad ratification never errors, mirroring
    `approval_ref`'s own "a bad ref never grants" rule); the evidence field is what
    tells them apart afterward.
    """
    from onedoor.guardrail import signing

    row = conn.execute(
        "SELECT id, state FROM approvals WHERE mandate_core_digest=? AND mandate_authority=1",
        (core_digest_value,),
    ).fetchone()
    if row is None:
        return RatificationResult(False, RatificationStatus.UNKNOWN_DIGEST)
    approval_id = int(row["id"])

    if not signing.verify_signature(authority_public_key, core_digest_value, signature_hex):
        _audit_attempt(conn, approval_id, now, RatificationStatus.WRONG_KEY)
        return RatificationResult(False, RatificationStatus.WRONG_KEY, approval_id=approval_id)

    # `expires_at > now`, same guard `cas_approve` uses: no timeout ever turns into
    # a permit (ruling), whether the timeout is onedoor's own TTL or anything else --
    # a ratification arriving after the deadline finds the row no longer pending in
    # onedoor's own terms and is refused exactly like a stale admin approval would be.
    consumed = conn.execute(
        "UPDATE approvals SET state='ratified', decided_at=?, decided_by_session=? "
        "WHERE id=? AND state='pending' AND expires_at > ?",
        (to_iso(now), "mandate-authority", approval_id, to_iso(now)),
    )
    if consumed.rowcount == 0:
        _audit_attempt(conn, approval_id, now, RatificationStatus.ALREADY_RESOLVED)
        return RatificationResult(
            False, RatificationStatus.ALREADY_RESOLVED, approval_id=approval_id
        )
    _audit_attempt(conn, approval_id, now, RatificationStatus.RATIFIED)
    from onedoor.guardrail.approvals import loads_request

    request_json = conn.execute(
        "SELECT request_json FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()["request_json"]
    return RatificationResult(
        True,
        RatificationStatus.RATIFIED,
        approval_id=approval_id,
        request=loads_request(request_json),
    )
