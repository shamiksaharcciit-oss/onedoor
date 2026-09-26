"""onedoor.permit.recipient: one test per refusal reason it can actually reach,
plus the happy path, the repeat-consumption case, and the two could-not-check
dependencies.

Every test builds a genuinely valid permit + signed request from scratch, then
mutates exactly one thing -- the same discipline as the rest of this codebase's
crypto tests (the mandate-layer deferral tests never assert on a pre-broken
fixture).

Not every `RefusalReason` value is reachable through `verify()` today:
`REPLAYED`, `STALE_POLICY`, `MANDATE_REVOKED` and `STATUS_UNAVAILABLE` are not
returned anywhere in `recipient.py` (the last three are `status-checked`
currentness and mandate-status polling, neither implemented -- see
`docs/design/bound-permit-next.md`). This file does not fabricate tests for
reasons the code cannot produce.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from onedoor.permit import httpsig, jws
from onedoor.permit.action import action_digest
from onedoor.permit.models import (
    PAYMENTS_TRANSFER_V1,
    REGISTRY,
    IssuerTableEntry,
    RefusalReason,
    VerificationResult,
    VerificationStatus,
)
from onedoor.permit.recipient import (
    InMemoryConsumeStore,
    MandateEvaluation,
    MandateVerdict,
    RecipientRequest,
    verify,
)

ISSUER = "https://issuer.example"
AUDIENCE = "https://recipient.example"
ACTION_TYPE = PAYMENTS_TRANSFER_V1.name
NOW = datetime(2026, 1, 1, tzinfo=UTC)
BODY = b'{"ok":true}'


def _keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return private, public


def _content_digest(body: bytes) -> str:
    return "sha-256=:" + base64.b64encode(hashlib.sha256(body).digest()).decode("ascii") + ":"


@dataclass
class Fixture:
    request: RecipientRequest
    issuer_table: dict[str, IssuerTableEntry]
    presenter_public: bytes
    presenter_private: Ed25519PrivateKey
    issuer_public: bytes
    claims: dict[str, object]


def _build(
    *,
    now: datetime = NOW,
    action_object: dict[str, object] | None = None,
    amount_max: str = "40.00",
    limit_max: str = "1000.00",
    lifetime_seconds: int = 100,
    claim_overrides: dict[str, object] | None = None,
    header_overrides: dict[str, object] | None = None,
    body: bytes = BODY,
    sign_with: Ed25519PrivateKey | None = None,
    idempotency_key: str = "idem-1",
) -> Fixture:
    issuer_priv, issuer_pub = _keypair()
    presenter_priv, presenter_pub = _keypair()
    from onedoor.permit.jwk import thumbprint

    jkt = thumbprint(presenter_pub)
    action_object = action_object or {
        "payee": "acme-gmbh",
        "amount": {"currency": "EUR", "max": amount_max},
        "reference": "invoice-1",
    }
    digest = action_digest(action_object)
    iat = int(now.timestamp())
    claims: dict[str, object] = {
        "iss": ISSUER,
        "sub": "urn:test:presenter",
        "aud": AUDIENCE,
        "jti": str(uuid4()),
        "iat": iat,
        "nbf": iat,
        "exp": iat + lifetime_seconds,
        "cnf": {"jkt": jkt},
        "authorization_details": [{"type": ACTION_TYPE, **action_object}],
        "action_digest": digest,
        "verdict": "permit",
        "currentness": "time-bounded",
    }
    if claim_overrides:
        claims.update(claim_overrides)
    header: dict[str, object] = {"alg": "EdDSA", "kid": "k1", "typ": "aadp-permit+jwt"}
    if header_overrides:
        header.update(header_overrides)
    token = jws.encode(header, claims, issuer_priv)

    content_digest = _content_digest(body)
    components = {
        "@method": "POST",
        "@authority": "recipient.example",
        "@path": "/act",
        "@query": "",
        "content-digest": content_digest,
        "idempotency-key": idempotency_key,
        "aadp-permit": token,
    }
    signer = sign_with or presenter_priv
    sig_input, sig = httpsig.sign(components, created=iat, keyid=jkt, private_key=signer)

    req = RecipientRequest(
        permit_token=token,
        method="POST",
        authority="recipient.example",
        path="/act",
        query="",
        body=body,
        content_digest_header=content_digest,
        signature_input_header=sig_input,
        signature_header=sig,
        signature_created=iat,
        idempotency_key_header=idempotency_key,
        recipient_audience=AUDIENCE,
        action_object=action_object,
    )
    issuer_table = {
        ISSUER: IssuerTableEntry(
            issuer=ISSUER,
            public_key=issuer_pub,
            action_types=frozenset({ACTION_TYPE}),
            limits={ACTION_TYPE: {"amount": {"currency": "EUR", "max": limit_max}}},
        )
    }
    return Fixture(
        request=req,
        issuer_table=issuer_table,
        presenter_public=presenter_pub,
        presenter_private=presenter_priv,
        issuer_public=issuer_pub,
        claims=claims,
    )


def _resign_for_body(fx: Fixture, *, body: bytes) -> Fixture:
    """A new, genuinely valid HTTP message signature over the SAME permit token but
    a different body -- what a second, distinct presentation of one permit looks
    like, as opposed to a request whose signature simply no longer matches."""
    assert fx.request.permit_token is not None
    content_digest = _content_digest(body)
    components = {
        "@method": fx.request.method,
        "@authority": fx.request.authority,
        "@path": fx.request.path,
        "@query": fx.request.query,
        "content-digest": content_digest,
        "idempotency-key": fx.request.idempotency_key_header or "",
        "aadp-permit": fx.request.permit_token,
    }
    from onedoor.permit.jwk import thumbprint

    sig_input, sig = httpsig.sign(
        components,
        created=fx.request.signature_created or 0,
        keyid=thumbprint(fx.presenter_public),
        private_key=fx.presenter_private,
    )
    return replace(
        fx,
        request=replace(
            fx.request,
            body=body,
            content_digest_header=content_digest,
            signature_input_header=sig_input,
            signature_header=sig,
        ),
    )


def _verify(fx: Fixture, **overrides: object) -> VerificationResult:
    kwargs: dict[str, object] = dict(
        request=fx.request,
        issuer_table=fx.issuer_table,
        registry=REGISTRY,
        resolve_presenter_key=lambda jkt: fx.presenter_public,
        consume_store=InMemoryConsumeStore(),
        now=NOW,
        local_policy=lambda claims: True,
    )
    kwargs.update(overrides)
    return verify(**kwargs)  # type: ignore[arg-type]


# --- Happy path -----------------------------------------------------------------


def test_a_valid_permit_from_end_to_end_is_verified() -> None:
    fx = _build()
    result = _verify(fx)
    assert result.status is VerificationStatus.VERIFIED
    assert result.reason is None
    assert result.repeat is False


def test_a_repeated_presentation_with_the_same_content_digest_returns_the_stored_result() -> None:
    fx = _build()
    store = InMemoryConsumeStore()
    first = _verify(fx, consume_store=store)
    assert first.status is VerificationStatus.VERIFIED
    second = _verify(fx, consume_store=store)
    assert second.status is VerificationStatus.VERIFIED
    assert second.repeat is True


def test_a_replay_with_a_different_content_digest_is_an_idempotency_conflict() -> None:
    fx = _build()
    store = InMemoryConsumeStore()
    first = _verify(fx, consume_store=store)
    assert first.status is VerificationStatus.VERIFIED
    fx2 = _resign_for_body(fx, body=BODY + b"a-second-distinct-presentation")
    result = _verify(fx2, consume_store=store)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.IDEMPOTENCY_CONFLICT
    assert result.step == 13


# --- Step 1: malformed / chained -------------------------------------------------


def test_no_permit_presented_is_malformed() -> None:
    fx = _build()
    fx = replace(fx, request=replace(fx.request, permit_token=None))
    result = _verify(fx)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_a_structurally_broken_token_is_malformed() -> None:
    fx = _build()
    fx = replace(fx, request=replace(fx.request, permit_token="not-a-jws"))
    result = _verify(fx)
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_the_wrong_typ_is_malformed() -> None:
    fx = _build(header_overrides={"typ": "jwt"})
    result = _verify(fx)
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_a_missing_required_claim_is_malformed() -> None:
    """A claim dropped entirely (not merely null) must be caught at step 1, before
    signature verification even runs -- so re-signing under a fresh, unlisted
    issuer key is fine here: the missing claim must be refused before the issuer
    table is ever consulted."""
    fx = _build()
    claims = dict(fx.claims)
    del claims["exp"]
    issuer_priv, _ = _keypair()
    token = jws.encode({"alg": "EdDSA", "kid": "k1", "typ": "aadp-permit+jwt"}, claims, issuer_priv)
    fx = replace(fx, request=replace(fx.request, permit_token=token))
    result = _verify(fx)
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_a_non_permit_verdict_is_malformed() -> None:
    fx = _build(claim_overrides={"verdict": "deny"})
    result = _verify(fx)
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_a_chained_permit_is_refused_structurally() -> None:
    fx = _build(claim_overrides={"parent": "sha-256=:previous:"})
    result = _verify(fx)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.CHAINED_PERMIT_UNSUPPORTED
    assert result.step == 1


# --- Step 2: issuer / signature ---------------------------------------------------


def test_an_unlisted_issuer_is_refused() -> None:
    fx = _build(claim_overrides={"iss": "https://someone-else.example"})
    result = _verify(fx)
    assert result.reason is RefusalReason.ISSUER_UNKNOWN
    assert result.step == 2


def test_a_tampered_permit_body_fails_signature_verification() -> None:
    """The named 'tampered body' refusal case."""
    fx = _build()
    # Re-sign under a DIFFERENT issuer key than the one in the issuer table, which
    # is indistinguishable in effect from tampering with a signed permit's claims.
    wrong_priv, _ = _keypair()
    header, payload, *_ = jws.parse(fx.request.permit_token)  # type: ignore[arg-type]
    retokened = jws.encode(header, payload, wrong_priv)
    fx = replace(fx, request=replace(fx.request, permit_token=retokened))
    result = _verify(fx)
    assert result.reason is RefusalReason.SIGNATURE_INVALID
    assert result.step == 2


# --- Step 3: audience -------------------------------------------------------------


def test_the_wrong_audience_is_refused() -> None:
    fx = _build(claim_overrides={"aud": "https://not-the-recipient.example"})
    result = _verify(fx)
    assert result.reason is RefusalReason.AUDIENCE_MISMATCH
    assert result.step == 3


def test_a_list_valued_audience_is_refused() -> None:
    fx = _build(claim_overrides={"aud": [AUDIENCE, "https://other.example"]})
    result = _verify(fx)
    assert result.reason is RefusalReason.AUDIENCE_MISMATCH
    assert result.step == 3


# --- Step 4: lifetime --------------------------------------------------------------


def test_an_expired_permit_is_refused() -> None:
    fx = _build(lifetime_seconds=10)
    later = datetime.fromtimestamp(NOW.timestamp() + 10 + 120, tz=UTC)
    result = _verify(fx, now=later)
    assert result.reason is RefusalReason.EXPIRED
    assert result.step == 4


def test_a_not_yet_valid_permit_is_refused() -> None:
    future = datetime.fromtimestamp(NOW.timestamp() + 3600, tz=UTC)
    fx = _build(now=future)
    result = _verify(fx, now=NOW)
    assert result.reason is RefusalReason.NOT_YET_VALID
    assert result.step == 4


def test_a_lifetime_longer_than_the_ceiling_is_refused() -> None:
    fx = _build(lifetime_seconds=121)
    result = _verify(fx)
    assert result.reason is RefusalReason.LIFETIME_INVALID
    assert result.step == 4


def test_non_integer_timestamps_are_refused() -> None:
    fx = _build(claim_overrides={"exp": "soon"})
    result = _verify(fx)
    assert result.reason is RefusalReason.LIFETIME_INVALID
    assert result.step == 4


# --- Step 5/6: authorization type and scope ---------------------------------------


def test_an_unregistered_authorization_type_is_refused() -> None:
    fx = _build(claim_overrides={"authorization_details": [{"type": "unknown.action/1"}]})
    result = _verify(fx)
    assert result.reason is RefusalReason.UNKNOWN_AUTHORIZATION_TYPE
    assert result.step == 5


def test_an_action_type_outside_the_issuer_table_is_out_of_scope() -> None:
    fx = _build()
    entry = fx.issuer_table[ISSUER]
    fx = replace(fx, issuer_table={ISSUER: replace(entry, action_types=frozenset())})
    result = _verify(fx)
    assert result.reason is RefusalReason.ISSUER_OUT_OF_SCOPE
    assert result.step == 6


def test_an_amount_over_the_issuers_limit_is_out_of_scope() -> None:
    fx = _build(amount_max="5000.00", limit_max="1000.00")
    result = _verify(fx)
    assert result.reason is RefusalReason.ISSUER_OUT_OF_SCOPE
    assert result.step == 6


# --- Step 7: Content-Digest ---------------------------------------------------------


def test_a_missing_content_digest_header_is_refused() -> None:
    fx = _build()
    fx = replace(fx, request=replace(fx.request, content_digest_header=None))
    result = _verify(fx)
    assert result.reason is RefusalReason.CONTENT_MISMATCH
    assert result.step == 7


def test_a_body_that_does_not_match_content_digest_is_refused() -> None:
    """The named 'tampered body' case at the transport layer: the bytes received
    do not hash to the Content-Digest the permit's own request signature covers."""
    fx = _build()
    fx = replace(fx, request=replace(fx.request, body=fx.request.body + b"tampered"))
    result = _verify(fx)
    assert result.reason is RefusalReason.CONTENT_MISMATCH
    assert result.step == 7


# --- Step 8: HTTP message signature / key binding -----------------------------------


def test_no_cnf_jkt_is_binding_incomplete() -> None:
    fx = _build(claim_overrides={"cnf": {}})
    result = _verify(fx)
    assert result.reason is RefusalReason.BINDING_INCOMPLETE
    assert result.step == 8


def test_a_missing_http_signature_is_refused() -> None:
    fx = _build()
    fx = replace(fx, request=replace(fx.request, signature_header=None))
    result = _verify(fx)
    assert result.reason is RefusalReason.REQUEST_SIGNATURE_MISSING
    assert result.step == 8


def test_an_unresolvable_presenter_key_could_not_be_checked() -> None:
    fx = _build()
    result = _verify(fx, resolve_presenter_key=lambda jkt: None)
    assert result.status is VerificationStatus.COULD_NOT_CHECK
    assert result.dependency == "presenter-key-directory"


def test_the_wrong_presenter_key_is_refused() -> None:
    """The named 'wrong presenter key' case: the directory resolves a key whose
    own thumbprint does not match the permit's cnf.jkt."""
    fx = _build()
    _, someone_elses_key = _keypair()
    result = _verify(fx, resolve_presenter_key=lambda jkt: someone_elses_key)
    assert result.reason is RefusalReason.PRESENTER_KEY_MISMATCH
    assert result.step == 8


def test_a_request_signed_by_the_wrong_key_is_refused() -> None:
    """A different failure mode from the mismatched-directory-key case above: here
    the directory correctly resolves the REAL presenter key, but the request was
    actually signed by a different key -- so the signature itself fails to verify
    under the key cnf.jkt (and the directory) both name.

    V09, second half: the Signature-Input HONESTLY names cnf.jkt (this is
    exactly what `_build(sign_with=...)` produces -- it always signs the
    `keyid` parameter as the real jkt, whatever key actually does the
    signing), but the bytes were produced by a different private key. Only
    cryptography can tell this apart from a genuine signature, so it is
    refused as request-signature-invalid, never presenter-key-mismatch --
    contrast `test_v09_a_signature_that_honestly_claims_a_different_key_is_
    presenter_key_mismatch` below, V09's other half.
    """
    other_priv, _ = _keypair()
    fx = _build(sign_with=other_priv)
    result = _verify(fx)
    assert result.reason is RefusalReason.REQUEST_SIGNATURE_INVALID
    assert result.step == 8


def test_v09_a_signature_that_honestly_claims_a_different_key_is_presenter_key_mismatch() -> None:
    """V09, first half: the presenter's OWN Signature-Input names a key other
    than cnf.jkt -- not a directory lookup gone wrong, the signature's own
    claim. Checked before any cryptography or key-directory lookup runs: a
    `resolve_presenter_key` that raises if called proves the directory is
    never even consulted."""
    from onedoor.permit.jwk import thumbprint

    other_priv, other_pub = _keypair()
    fx = _build()
    real_jkt = fx.claims["cnf"]["jkt"]  # type: ignore[index]
    other_jkt = thumbprint(other_pub)
    assert other_jkt != real_jkt

    req = fx.request
    components = {
        "@method": req.method,
        "@authority": req.authority,
        "@path": req.path,
        "@query": req.query,
        "content-digest": req.content_digest_header,
        "idempotency-key": req.idempotency_key_header or "",
        "aadp-permit": req.permit_token,
    }
    # A self-consistent signature genuinely made with a DIFFERENT key, honestly
    # claiming that key's own thumbprint -- not cnf.jkt.
    sig_input, sig = httpsig.sign(
        components, created=req.signature_created or 0, keyid=other_jkt, private_key=other_priv
    )
    fx = replace(fx, request=replace(req, signature_input_header=sig_input, signature_header=sig))

    def _must_not_be_called(jkt: str) -> bytes | None:
        raise AssertionError("resolve_presenter_key must not run before the claimed key is checked")

    result = _verify(fx, resolve_presenter_key=_must_not_be_called)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.PRESENTER_KEY_MISMATCH
    assert result.step == 8


def test_a_covered_component_dropped_from_signature_input_is_binding_incomplete() -> None:
    fx = _build()
    # Corrupt the Signature-Input to claim a shorter covered-component list, but
    # keep the real keyid -- otherwise this exercises presenter-key-mismatch
    # (checked first, per V09) rather than the component-set check this test is
    # actually about.
    cnf = fx.claims["cnf"]
    assert isinstance(cnf, dict)
    real_jkt = cnf["jkt"]
    fx = replace(
        fx,
        request=replace(
            fx.request,
            signature_input_header=f'sig1=("@method");created=1;keyid="{real_jkt}"',
        ),
    )
    result = _verify(fx)
    assert result.reason is RefusalReason.BINDING_INCOMPLETE
    assert result.step == 8


# --- Step 9: action digest -----------------------------------------------------------


def test_an_action_object_mismatch_is_refused() -> None:
    fx = _build()
    different_action: dict[str, object] = {
        "payee": "someone-else",
        "amount": {"currency": "EUR", "max": "1.00"},
    }
    fx = replace(fx, request=replace(fx.request, action_object=different_action))
    result = _verify(fx)
    assert result.reason is RefusalReason.ACTION_MISMATCH
    assert result.step == 9


def test_no_derivable_action_object_is_refused() -> None:
    fx = _build()
    fx = replace(fx, request=replace(fx.request, action_object=None))
    result = _verify(fx)
    assert result.reason is RefusalReason.ACTION_MISMATCH
    assert result.step == 9


# --- Step 10: currentness -------------------------------------------------------------


def test_status_checked_currentness_could_not_be_checked() -> None:
    fx = _build(claim_overrides={"currentness": "status-checked"})
    result = _verify(fx)
    assert result.status is VerificationStatus.COULD_NOT_CHECK
    assert result.dependency == "status-unavailable"


def test_an_unknown_currentness_mode_is_refused() -> None:
    fx = _build(claim_overrides={"currentness": "made-up-mode"})
    result = _verify(fx)
    assert result.reason is RefusalReason.LIFETIME_INVALID
    assert result.step == 10


# --- Step 11: mandate reference ---------------------------------------------------------


def test_a_mandate_reference_with_no_evaluator_is_unavailable() -> None:
    fx = _build(claim_overrides={"mandate": {"digest": "abc"}})
    result = _verify(fx)
    assert result.reason is RefusalReason.MANDATE_UNAVAILABLE
    assert result.step == 11


def test_a_mandate_reference_covered_by_the_optional_set_is_not_required() -> None:
    fx = _build(claim_overrides={"mandate": {"digest": "abc"}})
    result = _verify(fx, mandate_optional_action_types=frozenset({ACTION_TYPE}))
    assert result.status is VerificationStatus.VERIFIED


def test_a_mandate_digest_mismatch_is_refused() -> None:
    fx = _build(claim_overrides={"mandate": {"digest": "abc"}})
    result = _verify(
        fx,
        mandate_evaluator=lambda ref: MandateEvaluation(
            verdict=MandateVerdict.PERMIT, core_digest="different"
        ),
    )
    assert result.reason is RefusalReason.MANDATE_MISMATCH
    assert result.step == 11


def test_a_mandate_deny_is_refused() -> None:
    fx = _build(claim_overrides={"mandate": {"digest": "abc"}})
    result = _verify(
        fx,
        mandate_evaluator=lambda ref: MandateEvaluation(
            verdict=MandateVerdict.DENY, core_digest="abc"
        ),
    )
    assert result.reason is RefusalReason.MANDATE_DENIED
    assert result.step == 11


def test_a_mandate_pending_is_refused() -> None:
    fx = _build(claim_overrides={"mandate": {"digest": "abc"}})
    result = _verify(
        fx,
        mandate_evaluator=lambda ref: MandateEvaluation(
            verdict=MandateVerdict.PENDING, core_digest="abc"
        ),
    )
    assert result.reason is RefusalReason.MANDATE_PENDING
    assert result.step == 11


def test_a_non_object_mandate_reference_is_malformed() -> None:
    fx = _build(claim_overrides={"mandate": "not-an-object"})
    result = _verify(fx)
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 11


# --- Step 12: local policy ---------------------------------------------------------------


def test_a_refused_local_policy_is_refused() -> None:
    fx = _build()
    result = _verify(fx, local_policy=lambda claims: False)
    assert result.reason is RefusalReason.LOCAL_POLICY
    assert result.step == 12
