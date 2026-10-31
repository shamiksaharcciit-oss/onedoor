"""The recipient confirmation: a signed joint record closing bound-permit
profile §10 (bound-permit profile, "The Recipient Confirmation"), per the gaps
a separate, not-yet-public format note closes (§§1-5; cited by
section number in this module's docstrings, the same convention `recipient.py`
uses for the profile itself). Appendix B lists this as V22, not implemented;
this module implements it.

Importable without onedoor's engine, store or service -- the same standalone
promise `recipient.py` makes. Two sides, kept separate for the same reason
`jws.py`/`httpsig.py`/`jcs.py` are separate modules already: `build`, called by
a recipient once it has `recipient.verify()`'s result and (for a verified
permit) has attempted the real-world effect; `check`, called by a presenter
against reference values it already has, with no re-verification of the
permit itself. Single use across many confirmations (the format note's §7 row
4) is deliberately not this module's job -- a reader that keeps a record
across steps (onetrace) is where that belongs; `find_reused_permits` below is
the one helper this module exposes for it, operating on tokens the reader
already has rather than any state this module keeps.

Known, disclosed gap: `mandate_verdict` (REQUIRED when an AAE was evaluated)
is not populated. `VerificationResult` does not carry the evaluated mandate's
own digest back out of `verify()` (only whether it passed), so there is
nothing for `build` to read -- the same gap `docs/design/bound-permit-next.md`
already names for the issuer side's own `mandate` claim.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Sequence
from typing import Any

from onedoor.permit import httpsig, jws
from onedoor.permit.action import action_digest as compute_action_digest
from onedoor.permit.models import RefusalReason, VerificationResult, VerificationStatus
from onedoor.permit.recipient import RecipientRequest

CONFIRMATION_TYP = "aadp-confirmation+jwt"
"""`typ` lives in the JWS header only -- the payload never repeats it,
unlike a permit's own `typ` (which this profile also keeps header-only, so a
verifier's `typ` check is the same shape on both sides of the boundary)."""

EFFECT_OUTCOMES: tuple[str, ...] = ("effected", "effect-unknown")
"""The two outcomes a caller may choose for a `VERIFIED` result -- the permit
itself was fine; what happened to the real-world effect is the caller's own
news, not something `recipient.verify()` ever knew. `"refused"` is not offered
here: this package's own `verify()` already runs local policy at step 12, so
every check-time refusal already comes from `verify()` itself (see `build`
below); a `COULD_NOT_CHECK` result is also always `"refused"`, fixed, below."""

_KNOWN_PAYLOAD_FIELDS = frozenset(
    {
        "iss",
        "permit",
        "request",
        "action_digest",
        "mandate_verdict",
        "outcome",
        "step",
        "reason",
        "dependency",
        "recipient_action_id",
        "iat",
    }
)
"""A payload member outside this set is *ignored* and named in the key row's
own detail (`check`), not refused -- so a reader
on an older revision of this format is not broken by an additive member a
newer revision adds."""

_COULD_NOT_CHECK_STEP_IN_PROGRESS: dict[str, int] = {
    "presenter-key-directory": 8,
    "status-unavailable": 10,
    "consume-store": 13,
}
"""`recipient.verify`'s three dependencies, and the step that was in progress
when each could not be reached -- used only to gate `build`'s "once step N
passed" fields the same way a `REFUSED` result's own `.step` does; an
unrecognised dependency string is treated as step 1 (nothing yet established),
the conservative reading rather than risking over-inclusion."""

_IAT_WINDOW_SKEW_SECONDS = 60
"""The step's own recorded start/end, widened by this on each side -- onedoor's
own clock-skew ceiling (`recipient.DEFAULT_CLOCK_SKEW_SECONDS`), reused here
for the confirmation's `iat` window (format note §7 row 1)."""

_DEPENDENCY_PAYLOAD_NAME: dict[str, str] = {"status-unavailable": "status"}
"""Format note §2.1/§10 name the status dependency `status`, one of exactly
three (`consume-store`, `presenter-key-directory`, `status`). `"status-unavailable"`
is `recipient.verify`'s own internal name for the same dependency (it is also
`RefusalReason.STATUS_UNAVAILABLE`'s value, reused there for logging/metrics,
not the format note's own vocabulary) -- translated here, once, at the point
this module writes the payload's own `dependency` member, rather than renamed
at its source and risking every other reader of `result.dependency`. The other
two dependency strings already equal the format note's own names, so they pass
through unchanged."""

_OUTCOMES = frozenset({"effected", "refused", "effect-unknown"})

_DEPENDENCIES = frozenset({"consume-store", "presenter-key-directory", "status"})

_PERMIT_MEMBERS = frozenset({"iss", "jti", "digest"})
_REQUEST_MEMBERS = frozenset({"content_digest", "signature_base_digest"})


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _shape_problem(payload: dict[str, object]) -> str | None:
    """Format note §2's presence rules (§2.1, §2.2), checked before the
    signature so a payload that breaks them is malformed (§2.4) whatever it is
    signed with -- a valid signature over a shape draft 3 forbids is still a
    malformed confirmation, never a verified one. Returns a problem string, or
    `None` when the shape is clean. Ported from the format note's own
    reference checker (`tests/vectors/check_confirmation_rows_3.py`'s
    `shape_problem`), adapted to this module's own dict-based payload rather
    than that script's JSON-only one."""
    if not isinstance(payload.get("iss"), str):
        return "iss missing or not a string"
    if not _is_int(payload.get("iat")):
        return "iat missing or not an integer"
    outcome = payload.get("outcome")
    if outcome not in _OUTCOMES:
        return "outcome missing or unknown"
    if outcome == "effected" and "recipient_action_id" not in payload:
        return "effected without recipient_action_id"
    if outcome != "effected" and "recipient_action_id" in payload:
        return f"recipient_action_id on a {outcome!r} confirmation"
    if outcome != "refused" and any(k in payload for k in ("step", "reason", "dependency")):
        return f"step, reason or dependency on a {outcome!r} confirmation"
    if outcome == "refused":
        by_check = "step" in payload or "reason" in payload
        if by_check and "dependency" in payload:
            return "both a check refusal and a dependency"
        if by_check:
            step = payload.get("step")
            if not isinstance(step, int) or isinstance(step, bool) or not (1 <= step <= 13):
                return "step missing or outside 1 to 13"
            if not isinstance(payload.get("reason"), str):
                return "reason missing"
        elif payload.get("dependency") not in _DEPENDENCIES:
            return "a refusal with neither step and reason nor a known dependency"
    for key, members in (("permit", _PERMIT_MEMBERS), ("request", _REQUEST_MEMBERS)):
        nested = payload.get(key)
        if key in payload:
            if not isinstance(nested, dict):
                return f"{key} is not an object"
            for member in members:
                if member in nested and not isinstance(nested[member], str):
                    return f"{key}.{member} not a string"
    if outcome == "refused" and "step" in payload:
        step = payload["step"]
        assert isinstance(step, int)
        need = {
            "permit": step > 1,
            "request.content_digest": step > 7,
            "request.signature_base_digest": step > 8,
            "action_digest": step > 9,
        }
    elif outcome in ("effected", "effect-unknown"):
        need = dict.fromkeys(
            ("permit", "request.content_digest", "request.signature_base_digest", "action_digest"),
            True,
        )
    else:
        need = None  # a dependency refusal: nothing is required
    if need is not None:
        request = payload.get("request")
        request = request if isinstance(request, dict) else {}
        have = {
            "permit": "permit" in payload,
            "request.content_digest": "content_digest" in request,
            "request.signature_base_digest": "signature_base_digest" in request,
            "action_digest": "action_digest" in payload,
        }
        for key, required in need.items():
            if required and not have[key]:
                return f"{key} missing"
            if not required and have[key]:
                return f"{key} present before its step passed"
    return None


class ConfirmationError(ValueError):
    """`build` cannot produce a confirmation for this result."""


def _structured_digest(data: bytes) -> str:
    """RFC 9530's `sha-256=:...:` form, over a byte string, no domain tag:
    `permit.digest` and `request.signature_base_digest` digest a byte string
    with its own format, not a JSON value -- the same reasoning `Content-Digest`
    itself follows, and the opposite choice from `action_digest`'s domain-tagged
    digest over a JSON value (profile §4.3)."""
    return "sha-256=:" + base64.b64encode(hashlib.sha256(data).digest()).decode("ascii") + ":"


def build(
    request: RecipientRequest,
    result: VerificationResult,
    *,
    recipient_key_id: str,
    recipient_private_key: Any,
    now: Any,
    outcome: str | None = None,
    recipient_action_id: str | None = None,
) -> str:
    """Build and sign the confirmation (format note §§1-3), from exactly the
    inputs `recipient.verify()` already had (`request`) and the result it
    returned (`result`).

    A `REFUSED` result fixes `outcome="refused"`, with `step` and `reason`
    taken from `result` -- the "once step N passed" rule (§2) follows directly
    from `result.step`: fields that depend on a later step than the one that
    refused are simply never computed, so a refusal can never carry a value
    the recipient had not actually established.

    A `COULD_NOT_CHECK` result also fixes `outcome="refused"` (a
    could-not-check confirmation has no step and no reason, only
    `dependency` -- the recipient did not act, and does not know which
    numbered step it would have failed or passed). The "once step N passed"
    gating uses `_COULD_NOT_CHECK_STEP_IN_PROGRESS` to find the step that was
    in progress, the same way `REFUSED.step` does.

    A `VERIFIED` result means the permit itself was fine; the caller supplies
    `outcome` (one of `EFFECT_OUTCOMES`) for what happened when it acted on
    that permit, and `recipient_action_id` when `outcome="effected"`.

    Raises `ConfirmationError` for a missing/invalid `outcome` on a `VERIFIED`
    result, or for `effected` with no `recipient_action_id`.
    """
    if result.status is VerificationStatus.REFUSED:
        step_reached = result.step - 1  # type: ignore[operator]
    elif result.status is VerificationStatus.COULD_NOT_CHECK:
        step_in_progress = _COULD_NOT_CHECK_STEP_IN_PROGRESS.get(result.dependency or "", 1)
        step_reached = step_in_progress - 1
    else:
        step_reached = 13

    payload: dict[str, object] = {"iss": request.recipient_audience}

    claims: dict[str, object] | None = None
    permit_token = request.permit_token
    if step_reached < 1 or not permit_token:
        permit_token = None
    else:
        try:
            _, claims, _, _ = jws.parse(permit_token)
        except jws.MalformedJWS:
            claims = None
    if claims is not None and permit_token is not None:
        payload["permit"] = {
            "iss": claims.get("iss"),
            "jti": claims.get("jti"),
            "digest": _structured_digest(permit_token.encode("ascii")),
        }

    if step_reached >= 7:
        payload["request"] = {"content_digest": _structured_digest(request.body)}

    if step_reached >= 8 and claims is not None:
        cnf = claims.get("cnf")
        jkt = cnf.get("jkt") if isinstance(cnf, dict) else None
        if jkt is not None and request.signature_created is not None:
            assert permit_token is not None  # step_reached >= 8 implies >= 1
            components = {
                "@method": request.method.upper(),
                "@authority": request.authority.lower(),
                "@path": request.path,
                "@query": request.query,
                "content-digest": (request.content_digest_header or "").strip(),
                "idempotency-key": (request.idempotency_key_header or "").strip(),
                "aadp-permit": permit_token,
            }
            base = httpsig.signature_base(components, created=request.signature_created, keyid=jkt)
            request_claim = payload.setdefault("request", {})
            assert isinstance(request_claim, dict)
            request_claim["signature_base_digest"] = _structured_digest(base.encode("ascii"))

    if step_reached >= 9 and request.action_object is not None:
        payload["action_digest"] = compute_action_digest(request.action_object)

    if result.status is VerificationStatus.VERIFIED:
        if outcome not in EFFECT_OUTCOMES:
            raise ConfirmationError(f"outcome must be one of {EFFECT_OUTCOMES}, got {outcome!r}")
        payload["outcome"] = outcome
        if outcome == "effected":
            if not recipient_action_id:
                raise ConfirmationError("outcome 'effected' requires recipient_action_id")
            payload["recipient_action_id"] = recipient_action_id
    else:
        payload["outcome"] = "refused"

    payload["iat"] = int(now.timestamp())

    if result.status is VerificationStatus.REFUSED:
        payload["reason"] = result.reason.value if result.reason is not None else None
        payload["step"] = result.step
    elif result.status is VerificationStatus.COULD_NOT_CHECK:
        dependency = result.dependency
        payload["dependency"] = (
            _DEPENDENCY_PAYLOAD_NAME.get(dependency, dependency) if dependency is not None else None
        )

    header = {"alg": "EdDSA", "kid": recipient_key_id, "typ": CONFIRMATION_TYP}
    return jws.encode(header, payload, recipient_private_key)


def check(
    token: str | None,
    *,
    permit_token: str,
    permit_aud: str,
    content_digest: str,
    signature_base: str,
    action_digest: str,
    step_started: int,
    step_ended: int,
    step_outcome_ok: bool,
    recipients: dict[str, dict[str, bytes]],
) -> VerificationResult:
    """The presenter side (format note §7), onedoor's own four of its
    five rows -- single use (row 4) is excluded on purpose; see
    `find_reused_permits`. In order: key and `typ`, permit, request, outcome.
    Stops at the first failure, the same discipline `recipient.verify` follows.
    Before any of that, the key row also applies §1's `alg` rule and §2's
    full shape (`_shape_problem`) -- a payload that breaks either is malformed
    (§2.4) and refused with its own reason before the signature is ever
    checked, so a validly signed but malformed token is never read as
    verified.

    `token` is `None` when the step presented a permit but no confirmation was
    ever recorded (C20) -- only the outcome row has anything to say about that.

    `recipients` maps a recipient `iss` to its pinned Ed25519 public keys, by
    `kid` thumbprint, with no fetch (format note §4) -- `IssuerTableEntry`'s own
    rule, the same way. `permit_token`, `permit_aud`, `content_digest`,
    `signature_base` and `action_digest` are the reference values the step
    itself recorded; this function never recomputes them, only compares.
    `step_started`/`step_ended` (Unix seconds) bound the confirmation's `iat`,
    widened by `_IAT_WINDOW_SKEW_SECONDS` each way.
    """
    if token is None:
        return VerificationResult(
            status=VerificationStatus.COULD_NOT_CHECK,
            dependency="step-confirmation",
            detail="presented a permit; no confirmation recorded",
        )

    try:
        header, payload, signing_input, signature = jws.parse(token)
    except jws.MalformedJWS as exc:
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=1,
            reason=RefusalReason.MALFORMED,
            detail=str(exc),
        )

    unknown = sorted(set(payload) - _KNOWN_PAYLOAD_FIELDS)

    # --- 1. key and typ ---
    if header.get("typ") != CONFIRMATION_TYP:
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=1,
            reason=RefusalReason.MALFORMED,
            detail=f"not a recipient confirmation (typ {header.get('typ')!r})",
        )
    crit = header.get("crit")
    if crit:
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=1,
            reason=RefusalReason.MALFORMED,
            detail=f"unimplemented critical header parameter(s): {crit}",
        )
    if header.get("alg") != "EdDSA":
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=1,
            reason=RefusalReason.MALFORMED,
            detail=f"malformed confirmation (alg {header.get('alg')!r})",
        )
    shape_problem = _shape_problem(payload)
    if shape_problem is not None:
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=1,
            reason=RefusalReason.MALFORMED,
            detail=f"malformed confirmation ({shape_problem})",
        )
    iss = payload.get("iss")
    kid = header.get("kid")
    recipient_keys = recipients.get(iss) if isinstance(iss, str) else None
    if recipient_keys is None:
        return VerificationResult(
            status=VerificationStatus.COULD_NOT_CHECK,
            dependency="recipient-trust-list",
            detail="no recipient list given (pass --recipients)"
            if not recipients
            else f"recipient {iss!r} is not on the list",
        )
    public_key = recipient_keys.get(kid) if isinstance(kid, str) else None
    if public_key is None:
        return VerificationResult(
            status=VerificationStatus.COULD_NOT_CHECK,
            dependency="recipient-trust-list",
            detail=f"recipient {iss!r} has no listed key for kid {kid!r}",
        )
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519

    try:
        ed25519.Ed25519PublicKey.from_public_bytes(public_key).verify(signature, signing_input)
    except (InvalidSignature, ValueError, TypeError):
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=1,
            reason=RefusalReason.SIGNATURE_INVALID,
            detail="the confirmation does not verify under the recipient's listed key",
        )

    # --- 2. permit ---
    permit = payload.get("permit")
    if isinstance(permit, dict):
        expected_permit_digest = _structured_digest(permit_token.encode("ascii"))
        expected_iss: object = None
        expected_jti: object = None
        try:
            _, permit_claims, _, _ = jws.parse(permit_token)
        except jws.MalformedJWS:
            permit_claims = None
        if permit_claims is not None:
            expected_iss = permit_claims.get("iss")
            expected_jti = permit_claims.get("jti")
        if (
            permit.get("digest") != expected_permit_digest
            or permit.get("iss") != expected_iss
            or permit.get("jti") != expected_jti
        ):
            return VerificationResult(
                status=VerificationStatus.REFUSED,
                step=2,
                reason=RefusalReason.CONFIRMATION_PERMIT_MISMATCH,
                detail="the confirmation cites another permit",
            )
    if iss != permit_aud:
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=2,
            reason=RefusalReason.CONFIRMATION_PERMIT_MISMATCH,
            detail=f"confirmed by {iss!r}, but the permit is for {permit_aud!r}",
        )

    # --- 3. request ---
    request_claim = payload.get("request")
    if isinstance(request_claim, dict):
        if "content_digest" in request_claim and request_claim["content_digest"] != content_digest:
            return VerificationResult(
                status=VerificationStatus.REFUSED,
                step=3,
                reason=RefusalReason.CONTENT_MISMATCH,
                detail="the recipient confirmed a different request body",
            )
        expected_signature_base_digest = _structured_digest(signature_base.encode("ascii"))
        if (
            "signature_base_digest" in request_claim
            and request_claim["signature_base_digest"] != expected_signature_base_digest
        ):
            return VerificationResult(
                status=VerificationStatus.REFUSED,
                step=3,
                reason=RefusalReason.CONTENT_MISMATCH,
                detail="the recipient confirmed a different signature base",
            )
    if payload.get("action_digest") is not None and payload.get("action_digest") != action_digest:
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=3,
            reason=RefusalReason.ACTION_MISMATCH,
            detail="the recipient confirmed a different action",
        )
    iat = payload.get("iat")
    if isinstance(iat, int) and not isinstance(iat, bool):
        low = step_started - _IAT_WINDOW_SKEW_SECONDS
        high = step_ended + _IAT_WINDOW_SKEW_SECONDS
        if iat > high:
            return VerificationResult(
                status=VerificationStatus.REFUSED,
                step=3,
                reason=RefusalReason.CONTENT_MISMATCH,
                detail=f"the confirmation is dated outside the step (iat {iat - step_ended} s after it ended)",
            )
        if iat < low:
            return VerificationResult(
                status=VerificationStatus.REFUSED,
                step=3,
                reason=RefusalReason.CONTENT_MISMATCH,
                detail=f"the confirmation is dated outside the step (iat {step_started - iat} s before it started)",
            )

    # --- 4. outcome ---
    confirmed_outcome = payload.get("outcome")
    if step_outcome_ok and confirmed_outcome != "effected":
        dependency = payload.get("dependency")
        if confirmed_outcome == "refused" and dependency is not None:
            detail = f"reported ok, but the recipient could not check ({dependency})"
        elif confirmed_outcome == "refused":
            step_number = payload.get("step")
            reason_code = payload.get("reason")
            detail = (
                f"reported ok, but the recipient says 'refused' ({reason_code}, step {step_number})"
            )
        else:
            detail = f"reported ok, but the recipient says {confirmed_outcome!r}"
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=4,
            reason=RefusalReason.CONFIRMATION_OUTCOME_MISMATCH,
            detail=detail,
        )
    if not step_outcome_ok and confirmed_outcome == "effected":
        action_id = payload.get("recipient_action_id")
        return VerificationResult(
            status=VerificationStatus.REFUSED,
            step=4,
            reason=RefusalReason.CONFIRMATION_OUTCOME_MISMATCH,
            detail=f"reported error, but the recipient says it acted ({action_id})",
        )

    if unknown:
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            detail=f"ignored unknown payload member(s): {unknown}",
        )
    return VerificationResult(status=VerificationStatus.VERIFIED)


def find_reused_permits(tokens: Sequence[str]) -> list[tuple[object, object]]:
    """format note §7 row 4 (single use), across many confirmations at once --
    the one piece of that row this package exposes, since keeping a record
    across steps is the reader's own job (onetrace), not something this
    standalone package does.

    Given several confirmation tokens, names every `(permit.iss, permit.jti)`
    that appears on two or more *different* tokens both claiming
    `outcome: "effected"`. A byte-identical repeat (format note §5) is the same
    token twice, never a conflict; a refusal for the same permit, before or
    after an effected token, is also never a conflict (format note §5 narrows
    this to two different *effected* tokens only). Tokens that do not parse,
    are not `effected`, or carry no usable `permit` claim are silently skipped
    -- this helper reports conflicts among the tokens it can read, not
    malformed input.
    """
    first_effected_token: dict[tuple[object, object], str] = {}
    conflicts: list[tuple[object, object]] = []
    for token in tokens:
        try:
            _, payload, _, _ = jws.parse(token)
        except jws.MalformedJWS:
            continue
        if payload.get("outcome") != "effected":
            continue
        permit = payload.get("permit")
        if not isinstance(permit, dict):
            continue
        key = (permit.get("iss"), permit.get("jti"))
        if key[0] is None or key[1] is None:
            continue
        prior = first_effected_token.get(key)
        if prior is None:
            first_effected_token[key] = token
        elif prior != token and key not in conflicts:
            conflicts.append(key)
    return conflicts
