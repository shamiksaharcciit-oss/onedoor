"""The recipient side: a standalone check (bound-permit profile §8).

Importable without onedoor's engine, store or service -- a Recipient Enforcement
Point that never runs onedoor's own decision engine verifies a permit issued by one
using only this module and its siblings in `onedoor.permit`.

Implements the verification order of §8.1 (stopping at the first failure, so a
request refused for any reason before step 13 never consumes its permit), the
fail-closed rule of §8.2, and the three-outcome record of §8.3.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from onedoor.permit import httpsig, jcs, jwk, jws
from onedoor.permit.action import action_digest as compute_action_digest
from onedoor.permit.models import (
    ActionTypeRegistration,
    IssuerTableEntry,
    RefusalReason,
    VerificationResult,
    VerificationStatus,
)

MAX_LIFETIME_SECONDS = 120
"""profile §3.3: absent `execute_within`, `exp - iat` MUST NOT exceed this."""

DEFAULT_CLOCK_SKEW_SECONDS = 60
"""profile §3.3's own ceiling on the declared skew allowance."""


class MandateVerdict:
    """The three AAE outcomes this package reasons about, never evaluates itself
    (profile §5.3: this repository does not implement AAE). PERMIT/DENY/PENDING as
    plain strings, not an enum shared with `onedoor.guardrail.mandate` -- this
    package must not import the engine."""

    PERMIT = "permit"
    DENY = "deny"
    PENDING = "pending"


@dataclass(frozen=True)
class MandateEvaluation:
    verdict: str
    core_digest: str | None = None


MandateEvaluator = Callable[[dict[str, object]], MandateEvaluation]
"""A deployment's own AAE evaluator: given the mandate reference claim, returns the
verdict and the evaluated AAE's own `mandate_digest`. `None` (the default) means
this recipient supports no mandate type at all."""

LocalPolicy = Callable[[dict[str, object]], bool]
"""profile §8.1 step 12: the recipient's own policy, given the permit's claims."""


@dataclass(frozen=True)
class StoredConsumption:
    """What the consume store remembers for one `(iss, jti)` (profile §12)."""

    content_digest: str
    result: VerificationResult


class ConsumeStore(Protocol):
    """Durable, atomic storage keyed by `(iss, jti)` (profile §12). A recipient
    that cannot keep one MUST NOT accept bound permits -- this package does not
    supply a durable implementation; deployments provide their own."""

    def get(self, iss: str, jti: str) -> StoredConsumption | None: ...
    def put(self, iss: str, jti: str, consumption: StoredConsumption) -> None: ...
    def in_progress(self, iss: str, jti: str) -> bool: ...
    def mark_in_progress(self, iss: str, jti: str) -> None: ...


class InMemoryConsumeStore:
    """A reference implementation for tests. Not durable, not shared across
    processes -- exactly the shape profile §12 says a real recipient must not use."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], StoredConsumption] = {}
        self._in_progress: set[tuple[str, str]] = set()

    def get(self, iss: str, jti: str) -> StoredConsumption | None:
        return self._store.get((iss, jti))

    def put(self, iss: str, jti: str, consumption: StoredConsumption) -> None:
        self._store[(iss, jti)] = consumption
        self._in_progress.discard((iss, jti))

    def in_progress(self, iss: str, jti: str) -> bool:
        return (iss, jti) in self._in_progress

    def mark_in_progress(self, iss: str, jti: str) -> None:
        self._in_progress.add((iss, jti))


@dataclass(frozen=True)
class RecipientRequest:
    """Everything the REP needs about one incoming request."""

    permit_token: str | None
    """The bytes of the `AADP-Permit` field (profile §17.2), or `None` if absent."""
    method: str
    authority: str
    path: str
    query: str
    """Includes the leading `?` if present, per RFC 9421 §2.2.7; `""` if absent."""
    body: bytes
    """The exact bytes received, before any parsing (profile §4.1)."""
    content_digest_header: str | None
    signature_input_header: str | None
    signature_header: str | None
    signature_created: int | None
    """The `created` parameter the presenter claims to have signed under. Recipients
    resolve `keyid` themselves (from `cnf.jkt`, via `resolve_presenter_key`), so it
    is not read from the header's own claimed value -- see `httpsig.verify`."""
    idempotency_key_header: str | None
    recipient_audience: str
    action_object: dict[str, object] | None
    """`A`, already derived from this request by the action type's own rule
    (profile §4.3). Derivation is specific to each registered action type and is
    not this module's job; a caller that cannot derive A yet (an unknown
    authorization type) passes `None`."""


def _fail(step: int, reason: RefusalReason, detail: str = "") -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.REFUSED, step=step, reason=reason, detail=detail
    )


def _could_not_check(dependency: str, detail: str = "") -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.COULD_NOT_CHECK, dependency=dependency, detail=detail
    )


def _as_int(value: object) -> int | None:
    """A JSON NumericDate claim, strictly: an `int`, never a `bool` (an `int`
    subclass) and never coerced from a string -- a claim that is not already an
    integer is malformed, not merely differently spelled."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def verify(
    request: RecipientRequest,
    *,
    issuer_table: dict[str, IssuerTableEntry],
    registry: dict[str, ActionTypeRegistration],
    resolve_presenter_key: Callable[[str], bytes | None],
    consume_store: ConsumeStore,
    now: datetime,
    local_policy: LocalPolicy,
    mandate_evaluator: MandateEvaluator | None = None,
    mandate_optional_action_types: frozenset[str] = frozenset(),
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
) -> VerificationResult:
    """The 13 ordered steps of profile §8.1. Stops at the first failure.

    `resolve_presenter_key(jkt) -> bytes | None` is the out-of-band lookup from a
    JWK thumbprint to the actual public key bytes (profile §1.3: establishing that
    mapping is outside this profile's scope). Returning `None` means the key could
    not be resolved, which is `could-not-check` (§8.2), not a refusal -- the
    recipient cannot tell a wrong key from an unreachable directory.
    """
    # --- 1. Permit present, parses, typ, crit ---
    if not request.permit_token:
        return _fail(1, RefusalReason.MALFORMED, "no bound permit was presented")
    try:
        header, claims, signing_input, signature = jws.parse(request.permit_token)
    except jws.MalformedJWS as exc:
        return _fail(1, RefusalReason.MALFORMED, str(exc))
    if header.get("typ") != "aadp-permit+jwt":
        return _fail(
            1, RefusalReason.MALFORMED, f"typ is {header.get('typ')!r}, not aadp-permit+jwt"
        )
    crit = header.get("crit")
    if crit:
        return _fail(
            1, RefusalReason.MALFORMED, f"unimplemented critical header parameter(s): {crit}"
        )
    for required in (
        "iss",
        "sub",
        "aud",
        "jti",
        "iat",
        "nbf",
        "exp",
        "authorization_details",
        "action_digest",
        "verdict",
        "currentness",
    ):
        if required not in claims:
            return _fail(1, RefusalReason.MALFORMED, f"missing required claim: {required}")
    if claims.get("verdict") != "permit":
        return _fail(1, RefusalReason.MALFORMED, "verdict is not 'permit'")
    if "parent" in claims:
        # profile §11: version 0 is single-hop. "A capability declared unsupported
        # must be refused by the code, not merely left out of the text" -- checked
        # structurally, alongside the other claim-shape checks, before any
        # cryptographic or state work runs.
        return _fail(1, RefusalReason.CHAINED_PERMIT_UNSUPPORTED, "permit carries a parent claim")

    iss_raw, jti_raw = claims["iss"], claims["jti"]
    if not isinstance(iss_raw, str) or not isinstance(jti_raw, str):
        return _fail(1, RefusalReason.MALFORMED, "iss and jti must both be strings")
    iss, jti = iss_raw, jti_raw

    # --- 2. iss in table; signature verifies under a current key ---
    entry = issuer_table.get(iss)
    if entry is None:
        return _fail(2, RefusalReason.ISSUER_UNKNOWN, f"issuer {iss!r} is not in the issuer table")
    try:
        key = __import__(
            "cryptography.hazmat.primitives.asymmetric.ed25519", fromlist=["Ed25519PublicKey"]
        )
        pub = key.Ed25519PublicKey.from_public_bytes(entry.public_key)
        pub.verify(signature, signing_input)
    except Exception:  # noqa: BLE001 - any verification failure is signature-invalid, never a crash
        return _fail(
            2, RefusalReason.SIGNATURE_INVALID, "the permit's own signature does not verify"
        )

    # --- 3. aud identifies this recipient; single value ---
    aud = claims.get("aud")
    if isinstance(aud, list) or aud != request.recipient_audience:
        return _fail(3, RefusalReason.AUDIENCE_MISMATCH, f"aud={aud!r}")

    # --- 4. nbf <= now <= exp within skew; exp rule ---
    iat = _as_int(claims.get("iat"))
    nbf = _as_int(claims.get("nbf"))
    exp = _as_int(claims.get("exp"))
    if iat is None or nbf is None or exp is None:
        return _fail(4, RefusalReason.LIFETIME_INVALID, "iat/nbf/exp are not integers")
    skew = timedelta(seconds=min(clock_skew_seconds, DEFAULT_CLOCK_SKEW_SECONDS))
    now_ts = now.timestamp()
    if exp - iat > MAX_LIFETIME_SECONDS:
        return _fail(
            4,
            RefusalReason.LIFETIME_INVALID,
            f"exp-iat={exp - iat}s exceeds {MAX_LIFETIME_SECONDS}s",
        )
    if now_ts > exp + skew.total_seconds():
        return _fail(4, RefusalReason.EXPIRED, "past exp (within declared skew)")
    if now_ts < nbf - skew.total_seconds():
        return _fail(4, RefusalReason.NOT_YET_VALID, "before nbf (within declared skew)")

    # --- 5. every authorization_details type implemented ---
    auth_details = claims.get("authorization_details")
    if not isinstance(auth_details, list) or not auth_details:
        return _fail(
            5,
            RefusalReason.UNKNOWN_AUTHORIZATION_TYPE,
            "authorization_details is empty or not a list",
        )
    registrations: list[ActionTypeRegistration] = []
    for entry_ad in auth_details:
        type_name = entry_ad.get("type") if isinstance(entry_ad, dict) else None
        reg = registry.get(type_name) if isinstance(type_name, str) else None
        if reg is None:
            return _fail(5, RefusalReason.UNKNOWN_AUTHORIZATION_TYPE, f"type={type_name!r}")
        registrations.append(reg)

    # --- 6. every entry within the issuer's scope ---
    for entry_ad, reg in zip(auth_details, registrations):
        if reg.name not in entry.action_types:
            return _fail(
                6, RefusalReason.ISSUER_OUT_OF_SCOPE, f"{reg.name} not listed for issuer {iss!r}"
            )
        limits = entry.limits.get(reg.name, {})
        for field_name, checker in reg.limited_fields.items():
            if field_name not in entry_ad:
                continue
            limit = limits.get(field_name)
            if limit is None or not checker(entry_ad[field_name], limit):
                return _fail(
                    6,
                    RefusalReason.ISSUER_OUT_OF_SCOPE,
                    f"{reg.name}.{field_name} outside issuer scope",
                )

    # --- 7. Content-Digest recomputed over received bytes ---
    if not request.content_digest_header:
        return _fail(7, RefusalReason.CONTENT_MISMATCH, "no Content-Digest field")
    import base64
    import hashlib

    computed = (
        "sha-256=:" + base64.b64encode(hashlib.sha256(request.body).digest()).decode("ascii") + ":"
    )
    if request.content_digest_header.strip() != computed:
        return _fail(
            7, RefusalReason.CONTENT_MISMATCH, "Content-Digest does not match the received bytes"
        )

    # --- 8. HTTP message signature over cnf.jkt's key ---
    cnf = claims.get("cnf")
    jkt = cnf.get("jkt") if isinstance(cnf, dict) else None
    if not jkt:
        return _fail(8, RefusalReason.BINDING_INCOMPLETE, "permit carries no cnf.jkt")
    if not request.signature_header or not request.signature_input_header:
        return _fail(
            8, RefusalReason.REQUEST_SIGNATURE_MISSING, "no HTTP message signature present"
        )
    # The claimed key is checked before any cryptography or key-directory lookup
    # runs (profile V09): a signature that honestly names a key other than
    # cnf.jkt is presenter-key-mismatch on that basis alone. Only once the claim
    # itself matches does verifying it become a question `httpsig.verify` (and
    # the directory) can answer.
    claimed_keyid = httpsig.extract_keyid(request.signature_input_header)
    if claimed_keyid is None:
        return _fail(8, RefusalReason.BINDING_INCOMPLETE, "Signature-Input carries no keyid")
    if claimed_keyid != jkt:
        return _fail(
            8,
            RefusalReason.PRESENTER_KEY_MISMATCH,
            f"signature claims key {claimed_keyid!r}; permit binds to {jkt!r}",
        )
    if request.signature_created is None:
        return _fail(8, RefusalReason.BINDING_INCOMPLETE, "no created parameter")
    presenter_key = resolve_presenter_key(jkt)
    if presenter_key is None:
        return _could_not_check(
            "presenter-key-directory", f"could not resolve a key for jkt={jkt!r}"
        )
    try:
        resolved_matches = jwk.thumbprint(presenter_key) == jkt
    except (ValueError, TypeError) as exc:
        # A directory is free to be wrong, but it must never crash the
        # recipient: a key of the wrong length or type behind cnf.jkt is a
        # refusal, not an uncaught exception (profile item 8's wrong-key-type
        # case -- `jwk.thumbprint` itself raises for anything that is not a
        # 32-byte value, by design; this is the boundary that must not let it
        # propagate).
        return _fail(
            8,
            RefusalReason.PRESENTER_KEY_MISMATCH,
            f"resolved key is not a usable Ed25519 key: {exc}",
        )
    if not resolved_matches:
        return _fail(
            8,
            RefusalReason.PRESENTER_KEY_MISMATCH,
            "resolved key's thumbprint does not match cnf.jkt",
        )
    components = {
        "@method": request.method.upper(),
        "@authority": request.authority.lower(),
        "@path": request.path,
        "@query": request.query,
        "content-digest": request.content_digest_header.strip(),
        "idempotency-key": (request.idempotency_key_header or "").strip(),
        "aadp-permit": request.permit_token,
    }
    try:
        httpsig.verify(
            components,
            created=request.signature_created,
            keyid=jkt,
            signature_input_header=request.signature_input_header,
            signature_header=request.signature_header,
            public_key_bytes=presenter_key,
        )
    except httpsig.SignatureVerificationError as exc:
        detail = str(exc)
        if "binding-incomplete" in detail:
            return _fail(8, RefusalReason.BINDING_INCOMPLETE, detail)
        return _fail(8, RefusalReason.REQUEST_SIGNATURE_INVALID, detail)

    # --- 9. A derived from the request; digest equals action_digest ---
    if request.action_object is None:
        return _fail(
            9, RefusalReason.ACTION_MISMATCH, "no action object could be derived from the request"
        )
    try:
        recomputed_digest = compute_action_digest(request.action_object)
    except jcs.NotCanonicalizable as exc:
        return _fail(9, RefusalReason.ACTION_MISMATCH, f"action object not canonicalizable: {exc}")
    if recomputed_digest != claims.get("action_digest"):
        return _fail(
            9, RefusalReason.ACTION_MISMATCH, "recomputed action_digest does not match the permit's"
        )

    # --- 10. currentness ---
    currentness = claims.get("currentness")
    if currentness == "status-checked":
        return _could_not_check(
            RefusalReason.STATUS_UNAVAILABLE.value,
            "status-checked currentness is declared but no status mechanism is configured",
        )
    if currentness != "time-bounded":
        return _fail(
            10, RefusalReason.LIFETIME_INVALID, f"unknown currentness mode: {currentness!r}"
        )

    # --- 11. referenced mandate evaluated ---
    mandate = claims.get("mandate")
    if mandate is not None:
        if not isinstance(mandate, dict):
            return _fail(11, RefusalReason.MALFORMED, "mandate reference is not a JSON object")
        if mandate_evaluator is None:
            reg_names = {r.name for r in registrations}
            if not (reg_names & mandate_optional_action_types):
                return _fail(
                    11, RefusalReason.MANDATE_UNAVAILABLE, "no mandate evaluator configured"
                )
        else:
            evaluation = mandate_evaluator(mandate)
            if evaluation.core_digest != mandate.get("digest"):
                return _fail(
                    11,
                    RefusalReason.MANDATE_MISMATCH,
                    "evaluated mandate digest differs from the reference",
                )
            if evaluation.verdict == MandateVerdict.DENY:
                return _fail(11, RefusalReason.MANDATE_DENIED)
            if evaluation.verdict == MandateVerdict.PENDING:
                return _fail(11, RefusalReason.MANDATE_PENDING)

    # --- 12. recipient-local policy ---
    if not local_policy(claims):
        return _fail(12, RefusalReason.LOCAL_POLICY)

    # --- 13. (iss, jti) consumed atomically ---
    # A consume-store failure is a dependency the recipient cannot reach, not a
    # policy denial -- it must not collapse into a refusal (R010's three outcomes,
    # this package's own version of it), and a permit refused by an unavailable
    # store must not read as "the recipient looked and said no".
    try:
        existing = consume_store.get(iss, jti)
        if existing is not None:
            if existing.content_digest == request.content_digest_header.strip():
                return VerificationResult(
                    status=VerificationStatus.VERIFIED, repeat=True, detail="stored result returned"
                )
            return _fail(
                13, RefusalReason.IDEMPOTENCY_CONFLICT, "same (iss, jti), different Content-Digest"
            )
        if consume_store.in_progress(iss, jti):
            return _fail(
                13, RefusalReason.IDEMPOTENCY_CONFLICT, "same (iss, jti) still in progress"
            )
        consume_store.mark_in_progress(iss, jti)
        result = VerificationResult(status=VerificationStatus.VERIFIED)
        consume_store.put(
            iss,
            jti,
            StoredConsumption(content_digest=request.content_digest_header.strip(), result=result),
        )
    except Exception as exc:  # noqa: BLE001 - any consume-store failure is could-not-check
        return _could_not_check("consume-store", f"consume store unavailable: {exc}")
    return result
