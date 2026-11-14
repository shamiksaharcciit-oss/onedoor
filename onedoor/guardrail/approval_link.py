"""Signed approval links (onedoor 0.11): a single-use,
expiring, signed approve/deny token for email or a webhook, recorded
against the approver.

This module is the link's own mechanism: issuing and verifying a compact
token (pure -- `issue`/`verify`, no database), and single-use tracking
against the `approval_link_uses` table (`resolve`/`prune_expired_uses`,
migration 0045). The two service routes and the
`onedoor.integrations.approval_notify` adapter that builds and sends the
links are separate modules built on top of this one.

The token carries the approval id, the action it performs (approve or
deny -- baked in, never a parameter a presenter chooses), the identity it
was issued to, an absolute expiry, the id of the signing key that signed
it, and a random single-use nonce. An approve link and a deny link for
the same approval are therefore two distinct tokens, never one token plus
a parameter choosing between them -- a forwarded or logged URL cannot
silently have its action changed by whoever reads it, because there is no
URL-level action to change.

HMAC-SHA256, not a JWS: this is deliberately a separate, simpler artifact
from the bound-permit JWS (`onedoor.permit`) -- a different relying party
(a human clicking a link, not a PEP verifying a cryptographic binding),
verified with a different key under a different rotation schedule
(`NotifyConfig.approval_link_signing_keys`), never `onedoor.guardrail.
signing`'s own permit key.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from base64 import b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from onedoor.store.clock import from_iso, to_iso

LinkAction = Literal["approve", "deny"]

DEFAULT_LINK_TTL_SECONDS = 3600
"""A link's own default lifetime, absent an explicit `ttl_seconds` at
`issue()` -- one hour. The design note's own rule: no longer than the
approval's own TTL (the service's wiring passes `EngineConfig.
approval_ttl_seconds` explicitly, which is 3600 by its own default too,
so the two agree unless a deployment changes one and not the other).

Documented here, not left implicit, because the link is itself a bearer
credential once issued: whoever holds it may act as
its named recipient, once, for exactly this long. A SHORT lifetime and a
channel only the real approver reads (not a wide distribution list, not
a channel the proposer can also read) are what keeps "whoever holds it"
narrow in practice; this default is a starting point for a deployment to
tighten, not a recommendation to use it unexamined."""


MIN_SIGNING_KEY_BYTES = 32
"""An HMAC-SHA256 key shorter than its own digest size
is weaker than the construction built on it -- refused at configuration,
not left to be discovered as a forgeable link at use."""


@dataclass(frozen=True)
class NotifyConfig:
    """Deployment config for signed approval links -- the deployment
    supplies the mechanism, the same "resolver, absent by default" shape
    `mandate_resolver`/`escalation_resolver` already use.

    Validated at construction, not at first use: an
    empty or short signing key, a key given as `str` rather than `bytes`,
    or a key id absent from its own dict, fails the deployment
    at startup, the same "wrong config never serves a single request"
    discipline every other fail-closed check in this engine already
    applies.
    """

    approval_link_base_url: str
    approval_link_signing_keys: dict[str, bytes]
    """Key id to key material. A token carries the signing key's own id
    (see `issue`), so an old link signed under a since-rotated key still
    verifies as long as that key id remains in this set -- rotation adds
    a new key id here and, once every outstanding link under an old one
    has expired, retires it by removing it."""
    approval_link_signing_key_id: str
    """Which key in `approval_link_signing_keys` signs a NEW link. Must be
    a key present in that same dict."""
    approval_link_issuer: str
    """Signed into every token this deployment issues,
    and checked against a presented token's own claim -- a value naming
    THIS deployment (a hostname, an environment name; any non-empty
    string a deployer chooses), so a token issued by a different
    deployment (replayed from a restored backup of one, for instance)
    is refused rather than accepted just because the signature verifies
    under a signing key the two happen to share."""

    def __post_init__(self) -> None:
        if not self.approval_link_issuer:
            raise ValueError("approval_link_issuer must be a non-empty string")
        if self.approval_link_signing_key_id not in self.approval_link_signing_keys:
            raise ValueError(
                f"approval_link_signing_key_id {self.approval_link_signing_key_id!r} "
                "is not a key present in approval_link_signing_keys"
            )
        for key_id, key in self.approval_link_signing_keys.items():
            # A str of sufficient length passes the length check
            # below just as readily as real key material, but hmac.new()
            # (issue()/verify(), at first use, not at construction) refuses
            # it with a TypeError -- the wrong type at the wrong time,
            # against this class's own stated discipline of failing at
            # construction. Checked explicitly rather than relying on the
            # length check to also catch it by accident.
            if not isinstance(key, bytes):
                raise TypeError(
                    f"approval_link_signing_keys[{key_id!r}] is {type(key).__name__}, "
                    "not bytes -- a signing key must be real key material, not text"
                )
            if len(key) < MIN_SIGNING_KEY_BYTES:
                raise ValueError(
                    f"approval_link_signing_keys[{key_id!r}] is {len(key)} byte(s); "
                    f"a signing key needs at least {MIN_SIGNING_KEY_BYTES}"
                )


class LinkVerifyStatus(StrEnum):
    """A link's own verdict -- its own small, separate vocabulary, not a
    `CheckId`: the approval mechanics a link resolves against are the
    engine's own existing ones."""

    VALID = "valid"
    MALFORMED = "malformed"
    UNKNOWN_KEY = "unknown_key"
    BAD_SIGNATURE = "bad_signature"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    """Set only by a caller that also checks single-use (the service
    routes) -- this module's own `verify` never returns it, since nonce
    consumption needs a database."""


@dataclass(frozen=True)
class LinkClaims:
    approval_id: int
    action: LinkAction
    recipient: str
    exp: datetime
    key_id: str
    nonce: str
    issuer: str
    """The deployment that issued this token
    (`NotifyConfig.approval_link_issuer`). Structural only -- this module
    never compares it against anything; a caller with the current
    deployment's own configured issuer in hand (the service routes) does,
    refusing a token issued by a different one, such as one replayed from
    a restored backup of a different deployment."""
    request_digest: str
    """The same digest `approvals.resume_digest` already
    computes from an action's `action_type` and `params` -- binds this
    token to the exact request its approval was created for, structurally
    only, the same as `issuer`. A caller with the approval's own current
    request digest in hand refuses a token whose claimed digest no longer
    matches it, such as one replayed against a different approval id that
    reused the same id after a restore."""


@dataclass(frozen=True)
class LinkVerification:
    status: LinkVerifyStatus
    claims: LinkClaims | None = None
    """Present for every status except `MALFORMED` -- even `EXPIRED` and
    `BAD_SIGNATURE` carry what the token claimed, since that is itself
    evidence. `None` only when the token could not be parsed at all."""


def _b64url_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


_B64URL_TO_STD = str.maketrans("-_", "+/")


def _b64url_decode(text: str) -> bytes:
    """Strict decoding -- `validate=True` refuses any
    character outside the base64 alphabet, rather than `urlsafe_b64decode`'s
    own default of silently discarding one. A token with a stray or
    tampered character must fail structurally (`MALFORMED`), not decode
    to something its signer never produced."""
    pad = "=" * (-len(text) % 4)
    return b64decode((text + pad).translate(_B64URL_TO_STD), validate=True)


def issue(
    *,
    approval_id: int,
    action: LinkAction,
    recipient: str,
    now: datetime,
    signing_keys: dict[str, bytes],
    key_id: str,
    issuer: str,
    request_digest: str,
    ttl_seconds: int = DEFAULT_LINK_TTL_SECONDS,
) -> str:
    """Issue one compact signed token. Raises `KeyError` if `key_id` is not
    in `signing_keys` -- a deployment error (a misconfigured
    `approval_link_signing_key_id`), not a runtime condition to swallow.

    `ttl_seconds` defaults to `DEFAULT_LINK_TTL_SECONDS` -- a caller that
    wants a shorter-lived link (recommended) passes its own value; the
    service's own wiring always passes one explicitly today
    (`EngineConfig.approval_ttl_seconds`), so this default is reached by a
    caller using this function directly, not by the shipped service.

    `issuer` and `request_digest` are required, not
    defaulted -- a caller must supply the deployment's own configured
    issuer and the approval's own current request digest deliberately;
    this module signs them into the token but never itself compares them
    against anything (see `LinkClaims`)."""
    if action not in ("approve", "deny"):
        raise ValueError(f"action must be 'approve' or 'deny', got {action!r}")
    if ttl_seconds <= 0:
        # Refused here, at the one place every link is minted,
        # rather than minting a token already expired (zero) or expired
        # before it was even issued (negative) and discovering that only
        # once someone tries to use it.
        raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")
    nonce = secrets.token_urlsafe(16)
    payload = {
        "approval_id": approval_id,
        "action": action,
        "recipient": recipient,
        "exp": to_iso(now + timedelta(seconds=ttl_seconds)),
        "key_id": key_id,
        "nonce": nonce,
        "issuer": issuer,
        "request_digest": request_digest,
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(signing_keys[key_id], payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(sig)}"


def verify(token: str, *, signing_keys: dict[str, bytes], now: datetime) -> LinkVerification:
    """Resolve a presented token structurally (signature, expiry) -- never
    raises; a malformed token is evidence, not an exception. Single-use
    (nonce consumption) is a separate, database-backed step a caller takes
    after this one returns `VALID`.
    """
    try:
        payload_part, sig_part = token.split(".", 1)
        payload_bytes = _b64url_decode(payload_part)
        sig = _b64url_decode(sig_part)
        payload = json.loads(payload_bytes)
        key_id = str(payload["key_id"])
        approval_id = int(payload["approval_id"])
        action = str(payload["action"])
        recipient = str(payload["recipient"])
        exp = from_iso(str(payload["exp"]))
        nonce = str(payload["nonce"])
        issuer = str(payload["issuer"])
        request_digest = str(payload["request_digest"])
        if action not in ("approve", "deny"):
            raise ValueError("bad action")
    except Exception:
        return LinkVerification(LinkVerifyStatus.MALFORMED)

    key = signing_keys.get(key_id)
    if key is None:
        return LinkVerification(LinkVerifyStatus.UNKNOWN_KEY)

    expected_sig = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected_sig):
        return LinkVerification(LinkVerifyStatus.BAD_SIGNATURE)

    claims = LinkClaims(
        approval_id=approval_id,
        action=action,  # type: ignore[arg-type]
        recipient=recipient,
        exp=exp,
        key_id=key_id,
        nonce=nonce,
        issuer=issuer,
        request_digest=request_digest,
    )
    if exp <= now:
        return LinkVerification(LinkVerifyStatus.EXPIRED, claims)
    return LinkVerification(LinkVerifyStatus.VALID, claims)


def is_consumed(conn: sqlite3.Connection, nonce: str) -> bool:
    """A read-only check of whether a nonce was already
    consumed -- for a `GET` route, which must tell a human a used link is
    used (a distinct, legitimate thing to say about a token already in
    their own hand -- unlike the key/signature distinctions kept
    opaque) without itself consuming anything, the way `resolve`
    does for a `POST`."""
    row = conn.execute("SELECT 1 FROM approval_link_uses WHERE nonce=?", (nonce,)).fetchone()
    return row is not None


def _consume_nonce(
    conn: sqlite3.Connection, *, nonce: str, approval_id: int, expires_at: datetime, now: datetime
) -> bool:
    """Record a nonce's first use. Returns True if this call recorded it
    (first use), False if it was already recorded (a repeat presentation).
    The `nonce` column's own `PRIMARY KEY` is the CAS: the second `INSERT`
    for the same nonce fails with an integrity error, which is the signal,
    not an exception to propagate."""
    try:
        conn.execute(
            "INSERT INTO approval_link_uses (nonce, approval_id, expires_at, used_at) "
            "VALUES (?, ?, ?, ?)",
            (nonce, approval_id, to_iso(expires_at), to_iso(now)),
        )
        return True
    except sqlite3.IntegrityError:
        return False


def resolve(
    conn: sqlite3.Connection, token: str, *, signing_keys: dict[str, bytes], now: datetime
) -> LinkVerification:
    """`verify` plus single-use consumption against the database -- the
    full resolution a POST route takes when a token presented to it would
    otherwise grant something. A `GET` route (a confirmation page only,
    never acting) calls `verify` directly instead, never this function --
    consuming a nonce for a page that only displays would burn the link on
    a request nobody asked to act on.

    Consumption happens only when `verify` itself would return `VALID`:
    `MALFORMED`/`UNKNOWN_KEY`/`BAD_SIGNATURE`/`EXPIRED` never touch the
    nonce table at all -- nothing to consume for a ref that was never
    going to grant anything, the same reasoning `approval_ref.resolve`'s
    own module docstring states for a bad ref. A nonce already consumed
    upgrades the result to `CONSUMED`, still carrying the claims (consumed
    is evidence, not nothing) -- the same lost-race-never-errors shape
    `approval_ref.resolve`'s own CAS already has.
    """
    result = verify(token, signing_keys=signing_keys, now=now)
    if result.status != LinkVerifyStatus.VALID:
        return result
    assert result.claims is not None
    newly_consumed = _consume_nonce(
        conn,
        nonce=result.claims.nonce,
        approval_id=result.claims.approval_id,
        expires_at=result.claims.exp,
        now=now,
    )
    if not newly_consumed:
        return LinkVerification(LinkVerifyStatus.CONSUMED, result.claims)
    return result


def prune_expired_uses(conn: sqlite3.Connection, *, now: datetime) -> int:
    """Delete every recorded nonce past its own token's expiry. Returns the
    count pruned. Safe to call any time: the signature already covers the
    expiry, so a live check refuses an expired token on `EXPIRED` before
    this table is ever consulted -- pruning loses no real protection, only
    bounds the table's growth (the design note's own "State" section)."""
    cur = conn.execute("DELETE FROM approval_link_uses WHERE expires_at <= ?", (to_iso(now),))
    return cur.rowcount
