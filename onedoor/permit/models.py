"""Shared vocabulary: refusal reasons (profile §9), verification states (§8.3),
the issuer table (§6), and one concrete action-type registration (§17.3) used
throughout this package's own tests and conformance vectors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class RefusalReason(StrEnum):
    """The reason column of §8.1, plus §5.3's mandate-* codes and §11's."""

    MALFORMED = "malformed"
    ISSUER_UNKNOWN = "issuer-unknown"
    SIGNATURE_INVALID = "signature-invalid"
    AUDIENCE_MISMATCH = "audience-mismatch"
    EXPIRED = "expired"
    NOT_YET_VALID = "not-yet-valid"
    LIFETIME_INVALID = "lifetime-invalid"
    UNKNOWN_AUTHORIZATION_TYPE = "unknown-authorization-type"
    ISSUER_OUT_OF_SCOPE = "issuer-out-of-scope"
    CONTENT_MISMATCH = "content-mismatch"
    REQUEST_SIGNATURE_MISSING = "request-signature-missing"
    PRESENTER_KEY_MISMATCH = "presenter-key-mismatch"
    REQUEST_SIGNATURE_INVALID = "request-signature-invalid"
    BINDING_INCOMPLETE = "binding-incomplete"
    ACTION_MISMATCH = "action-mismatch"
    STALE_POLICY = "stale-policy"
    MANDATE_REVOKED = "mandate-revoked"
    STATUS_UNAVAILABLE = "status-unavailable"
    MANDATE_MISMATCH = "mandate-mismatch"
    MANDATE_DENIED = "mandate-denied"
    MANDATE_PENDING = "mandate-pending"
    MANDATE_UNAVAILABLE = "mandate-unavailable"
    LOCAL_POLICY = "local-policy"
    REPLAYED = "replayed"
    IDEMPOTENCY_CONFLICT = "idempotency-conflict"
    CHAINED_PERMIT_UNSUPPORTED = "chained-permit-unsupported"


class VerificationStatus(StrEnum):
    """§8.3: exactly one of three, never "partially verified"."""

    VERIFIED = "verified"
    REFUSED = "refused"
    COULD_NOT_CHECK = "could-not-check"


@dataclass(frozen=True)
class VerificationResult:
    """One request's verification outcome, per §8.3.

    `status is VERIFIED` iff `reason is None and dependency is None`. A `REFUSED`
    result always carries `reason` and the `step` (§8.1's numbered order) at which
    it stopped; a `COULD_NOT_CHECK` result always carries `dependency` -- never
    both, and never neither, so a reader can never mistake one for the other.
    """

    status: VerificationStatus
    step: int | None = None
    reason: RefusalReason | None = None
    dependency: str | None = None
    detail: str = ""
    repeat: bool = False
    """VERIFIED but this exact (iss, jti, Content-Digest) was already consumed
    (profile §12: "same (iss, jti), same Content-Digest, after completion: return
    the stored result"). Distinguishes a repeat from a first, effecting pass."""


@dataclass(frozen=True)
class ActionTypeRegistration:
    """One registered action type (profile §17.3): how to check an
    `authorization_details` entry against an issuer's scope limits.

    `scope_check` takes the entry's own field value and the issuer's configured
    limit for that field, and returns whether the entry is within it. Kept as an
    explicit callable per field rather than one generic comparator, because the
    profile leaves the comparison rule to each type's own registration -- a
    single hard-coded numeric comparison would be correct for money and wrong for
    a field whose limit is a set of allowed values.
    """

    name: str
    limited_fields: dict[str, Callable[[object, object], bool]] = field(default_factory=dict)


def _decimal_amount_within(entry_amount: object, limit_max: object) -> bool:
    """The profile's own worked example: `amount.max <= EUR 1,000.00`.

    `entry_amount` is `authorization_details[i].amount` (`{"currency": ..., "max":
    "<decimal string>"}`); `limit_max` is the issuer table's configured ceiling for
    the same currency, as a decimal string. Currency mismatch is out of scope, not
    in scope -- refuse rather than compare across currencies.
    """
    if not isinstance(entry_amount, dict) or not isinstance(limit_max, dict):
        return False
    if entry_amount.get("currency") != limit_max.get("currency"):
        return False
    try:
        return Decimal(str(entry_amount["max"])) <= Decimal(str(limit_max["max"]))
    except (KeyError, TypeError, ValueError):
        return False


PAYMENTS_TRANSFER_V1 = ActionTypeRegistration(
    name="payments.transfer/1",
    limited_fields={"amount": _decimal_amount_within},
)
"""profile §3.4's own worked example action type, used throughout this package's
tests and the §16 conformance vectors."""

REGISTRY: dict[str, ActionTypeRegistration] = {PAYMENTS_TRANSFER_V1.name: PAYMENTS_TRANSFER_V1}


@dataclass(frozen=True)
class IssuerTableEntry:
    """One row of the recipient's issuer table (profile §6.1)."""

    issuer: str
    public_key: bytes
    """Raw 32-byte Ed25519 public key, pinned. No `jwks_uri` fetch is implemented
    (out of scope: no network fetch of keys)."""
    action_types: frozenset[str]
    limits: dict[str, dict[str, object]] = field(default_factory=dict)
    """Per action type, per limited field: the configured ceiling, in the shape
    that type's `scope_check` callables expect."""
    not_after: str | None = None
    min_currentness: str = "time-bounded"
