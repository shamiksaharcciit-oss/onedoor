"""The hand-rolled JWS/JCS/httpsig codecs are public and other people will read
and copy them, so the well-known JWT failure modes must be shown refused, one
test per item, not merely asserted safe in prose.

Every test here either builds a genuinely valid permit via `test_recipient`'s
own `_build`/`_verify` helpers and mutates exactly one thing, or constructs a
deliberately adversarial token by hand when the mutation cannot be expressed as
an override (an empty signature segment, a header with no `typ` at all, a
payload whose raw JSON text carries a duplicate key). Nothing here signs a
token normally and then claims the header value was "accepted" without it
actually mattering -- see `test_alg_is_never_consulted` for why `alg` cannot
be attacked here at all.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import replace
from decimal import Decimal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from onedoor.permit import httpsig, jcs, jws
from onedoor.permit.action import action_digest
from onedoor.permit.models import RefusalReason, VerificationStatus
from tests.permit.test_recipient import ISSUER, _build, _keypair, _verify


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _raw_token(header_json: str, payload_json: str, signature: bytes = b"") -> str:
    """Build a compact JWS from RAW JSON TEXT for header/payload, bypassing
    `jws.encode` entirely -- the only way to get a duplicate object key into a
    segment, since a Python `dict` cannot hold one by construction."""
    header_b64 = _b64url(header_json.encode("utf-8"))
    payload_b64 = _b64url(payload_json.encode("utf-8"))
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


def _swap_token(fx, token: str):  # type: ignore[no-untyped-def]
    """Swap in a hand-built token for a fixture's real one. Every test in this
    file targets steps 1-2 or step 9 of verification, both of which run before
    step 8 checks the HTTP message signature -- so the (now-stale) httpsig
    signature over the ORIGINAL token is never reached and does not need
    re-signing."""
    return replace(fx, request=replace(fx.request, permit_token=token))


# --- Item 1: alg: none ------------------------------------------------------------


def test_alg_none_with_no_signature_is_refused() -> None:
    fx = _build()
    header = {"alg": "none", "typ": "aadp-permit+jwt", "kid": "k1"}
    token = _raw_token(json.dumps(header), json.dumps(fx.claims), signature=b"")
    result = _verify(_swap_token(fx, token))
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.SIGNATURE_INVALID
    assert result.step == 2


def test_alg_is_never_consulted_a_real_signature_is_still_required() -> None:
    """The header's `alg` is not read anywhere in this package: verification
    always attempts a real Ed25519 check against the issuer's configured key,
    whatever the header claims. Demonstrated the other direction from the test
    above: even the CORRECT header value doesn't matter if the bytes aren't a
    real signature."""
    fx = _build()
    header = {"alg": "EdDSA", "typ": "aadp-permit+jwt", "kid": "k1"}
    token = _raw_token(json.dumps(header), json.dumps(fx.claims), signature=b"\x00" * 64)
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.SIGNATURE_INVALID
    assert result.step == 2


# --- Item 2: alg other than EdDSA, including HS256 keyed with the public key ------


def test_hs256_keyed_with_the_issuers_public_key_is_refused() -> None:
    """The classic algorithm-confusion attack: claim `alg: HS256` and compute an
    HMAC over the signing input using the issuer's PUBLIC key bytes as the HMAC
    secret, hoping a verifier that trusts the header's own algorithm will
    downgrade to a symmetric check keyed with public material. This package
    never branches on `alg` at all, so the HMAC digest is simply handed to
    Ed25519 verification as if it were a signature, which refuses it."""
    fx = _build()
    header = {"alg": "HS256", "typ": "aadp-permit+jwt", "kid": "k1"}
    header_b64 = _b64url(json.dumps(header).encode())
    payload_b64 = _b64url(json.dumps(fx.claims).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    forged_signature = hmac.new(fx.issuer_public, signing_input, hashlib.sha256).digest()
    token = f"{header_b64}.{payload_b64}.{_b64url(forged_signature)}"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.SIGNATURE_INVALID
    assert result.step == 2


def test_an_alg_other_than_eddsa_with_a_real_eddsa_signature_still_verifies_the_bytes_not_the_label() -> (
    None
):
    """A header naming any other algorithm, paired with a genuine Ed25519
    signature, still verifies -- proving the label is decoration and the
    actual bytes are what get checked either way."""
    fx = _build()
    issuer_priv, issuer_pub = _keypair()
    fx = replace(
        fx,
        issuer_public=issuer_pub,
        issuer_table={ISSUER: replace(fx.issuer_table[ISSUER], public_key=issuer_pub)},
    )
    header = {"alg": "RS256", "typ": "aadp-permit+jwt", "kid": "k1"}
    token = jws.encode(header, fx.claims, issuer_priv)
    # This test alone needs to reach VERIFIED, past step 8 -- so, unlike every
    # other test in this file, the HTTP message signature must be re-made over
    # the new token: its own "aadp-permit" covered component is the token's
    # exact string, and the original httpsig signature was made over the OLD
    # one.
    from onedoor.permit.jwk import thumbprint

    req = fx.request
    components = {
        "@method": req.method,
        "@authority": req.authority,
        "@path": req.path,
        "@query": req.query,
        "content-digest": req.content_digest_header,
        "idempotency-key": req.idempotency_key_header or "",
        "aadp-permit": token,
    }
    sig_input, sig = httpsig.sign(
        components,
        created=req.signature_created or 0,
        keyid=thumbprint(fx.presenter_public),
        private_key=fx.presenter_private,
    )
    fx = replace(
        fx,
        request=replace(
            req, permit_token=token, signature_input_header=sig_input, signature_header=sig
        ),
    )
    result = _verify(fx)
    assert result.status is VerificationStatus.VERIFIED


# --- Item 3: a missing or wrong typ -------------------------------------------------


def test_a_wrong_typ_is_malformed() -> None:
    fx = _build(header_overrides={"typ": "jwt"})
    result = _verify(fx)
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_a_missing_typ_entirely_is_malformed() -> None:
    header = {"alg": "EdDSA", "kid": "k1"}  # no "typ" key at all
    fx = _build()
    issuer_priv, issuer_pub = _keypair()
    fx = replace(fx, issuer_table={ISSUER: replace(fx.issuer_table[ISSUER], public_key=issuer_pub)})
    token = jws.encode(header, fx.claims, issuer_priv)
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


# --- Item 4: an unknown crit header --------------------------------------------------


def test_an_unknown_crit_is_malformed() -> None:
    fx = _build(header_overrides={"crit": ["exp"]})
    result = _verify(fx)
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


# --- Item 5: not exactly three segments, and empty segments -------------------------


def test_two_segments_is_malformed() -> None:
    fx = _build()
    token = "abc.def"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_four_segments_is_malformed() -> None:
    fx = _build()
    token = "abc.def.ghi.jkl"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_an_empty_header_segment_is_malformed() -> None:
    fx = _build()
    payload_b64 = _b64url(json.dumps(fx.claims).encode())
    token = f".{payload_b64}.{_b64url(b'x' * 64)}"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_an_empty_payload_segment_is_malformed() -> None:
    fx = _build()
    header_b64 = _b64url(json.dumps({"alg": "EdDSA", "typ": "aadp-permit+jwt"}).encode())
    token = f"{header_b64}..{_b64url(b'x' * 64)}"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def test_an_empty_signature_segment_parses_but_never_verifies() -> None:
    """An empty third segment is structurally well-formed base64url (it decodes
    to zero bytes without error) -- it must still be refused, at the
    cryptographic step, not accepted as some kind of unsigned-but-valid form."""
    fx = _build()
    header_b64 = _b64url(json.dumps({"alg": "EdDSA", "typ": "aadp-permit+jwt"}).encode())
    payload_b64 = _b64url(json.dumps(fx.claims).encode())
    token = f"{header_b64}.{payload_b64}."
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.SIGNATURE_INVALID
    assert result.step == 2


# --- Item 6: non-canonical base64url; the same permit in two encodings ----------------


def test_non_canonical_base64_with_padding_is_rejected() -> None:
    fx = _build()
    assert fx.request.permit_token is not None
    header_b64, payload_b64, sig_b64 = fx.request.permit_token.split(".")
    padded = header_b64 + "="  # compact JWS forbids padding entirely
    token = f"{padded}.{payload_b64}.{sig_b64}"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


def _find_noncanonical_variant(segment: str) -> str | None:
    """A different string that decodes to the same bytes as `segment`, if one
    exists. Only possible when the segment's length leaves unused bits in its
    last symbol (length mod 4 is 2 or 3, never 0) -- returns `None` otherwise
    rather than assume every segment has one."""
    if len(segment) % 4 == 0:
        return None
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    target = base64.urlsafe_b64decode(pad(segment))
    for candidate in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_":
        mutated = segment[:-1] + candidate
        if mutated == segment:
            continue
        try:
            if base64.urlsafe_b64decode(pad(mutated)) == target:
                return mutated
        except (ValueError, TypeError):
            continue
    return None


def test_a_non_canonical_trailing_bit_variant_of_a_valid_permit_does_not_also_verify() -> None:
    """The precise defect this test exists to close: Python's own base64url
    decoder does not validate that the unused bits in a non-4-aligned final
    symbol are zero, so a byte-identical decode can be spelled more than one
    way. Confirmed directly first (`_find_noncanonical_variant`, run against a
    controlled 2-byte value in `test_jws_parse_rejects_a_non_canonical_
    segment_directly`, finds one every time). A signed, genuinely valid
    permit's header or payload segment is re-spelled to one of those
    non-canonical variants (same decoded bytes, different string) and MUST NOT
    also verify -- only the original, canonical spelling may."""
    fx = _build()
    assert fx.request.permit_token is not None
    header_b64, payload_b64, sig_b64 = fx.request.permit_token.split(".")
    original = _verify(fx)
    assert original.status is VerificationStatus.VERIFIED

    for name, segment in (("header", header_b64), ("payload", payload_b64)):
        variant = _find_noncanonical_variant(segment)
        if variant is None:
            continue
        mutated_token = (
            f"{variant}.{payload_b64}.{sig_b64}"
            if name == "header"
            else f"{header_b64}.{variant}.{sig_b64}"
        )
        result = _verify(_swap_token(fx, mutated_token))
        assert result.status is not VerificationStatus.VERIFIED, (
            f"non-canonical {name} spelling {variant!r} of the same bytes as "
            f"{segment!r} must not also verify"
        )
        assert result.reason is RefusalReason.MALFORMED
        return
    raise AssertionError(
        "neither header nor payload segment had unused padding bits to test against"
    )


def test_jws_parse_rejects_a_non_canonical_segment_directly() -> None:
    """The same property, at the codec unit level rather than through the full
    13-step pipeline: `jws.parse` itself must refuse a non-canonical segment."""
    canonical = _b64url(b"\x00\x01")  # 2 bytes: length mod 4 == 3, so unused bits exist
    variant = _find_noncanonical_variant(canonical)
    assert variant is not None, "a 2-byte segment must always have a colliding variant"

    header_b64 = _b64url(json.dumps({"alg": "EdDSA", "typ": "aadp-permit+jwt"}).encode())
    payload_b64 = _b64url(json.dumps({"x": 1}).encode())
    good_token = f"{header_b64}.{payload_b64}.{canonical}"
    bad_token = f"{header_b64}.{payload_b64}.{variant}"
    jws.parse(good_token)  # must not raise
    try:
        jws.parse(bad_token)
    except jws.MalformedJWS:
        pass
    else:
        raise AssertionError(f"non-canonical signature segment {variant!r} was accepted")


# --- Item 7: a signature of the wrong length ----------------------------------------


def test_a_zero_length_signature_is_refused() -> None:
    fx = _build()
    header_b64 = _b64url(json.dumps({"alg": "EdDSA", "typ": "aadp-permit+jwt"}).encode())
    payload_b64 = _b64url(json.dumps(fx.claims).encode())
    token = f"{header_b64}.{payload_b64}.{_b64url(b'')}"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.SIGNATURE_INVALID


def test_a_too_short_signature_is_refused() -> None:
    fx = _build()
    header_b64 = _b64url(json.dumps({"alg": "EdDSA", "typ": "aadp-permit+jwt"}).encode())
    payload_b64 = _b64url(json.dumps(fx.claims).encode())
    token = f"{header_b64}.{payload_b64}.{_b64url(b'x' * 32)}"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.SIGNATURE_INVALID


def test_a_too_long_signature_is_refused() -> None:
    fx = _build()
    header_b64 = _b64url(json.dumps({"alg": "EdDSA", "typ": "aadp-permit+jwt"}).encode())
    payload_b64 = _b64url(json.dumps(fx.claims).encode())
    token = f"{header_b64}.{payload_b64}.{_b64url(b'x' * 128)}"
    result = _verify(_swap_token(fx, token))
    assert result.reason is RefusalReason.SIGNATURE_INVALID


# --- Item 8: a key of the wrong type or curve behind cnf.jkt -------------------------


def test_a_wrong_length_resolved_key_is_refused_not_a_crash() -> None:
    """`resolve_presenter_key` is deployment-supplied; a directory returning a
    key of the wrong length (an EC point, garbage, anything not 32 bytes) must
    be refused, not crash the recipient with an uncaught exception from
    `jwk.thumbprint`."""
    fx = _build()
    result = _verify(fx, resolve_presenter_key=lambda jkt: b"\x00" * 65)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.PRESENTER_KEY_MISMATCH
    assert result.step == 8


def test_a_zero_length_resolved_key_is_refused_not_a_crash() -> None:
    fx = _build()
    result = _verify(fx, resolve_presenter_key=lambda jkt: b"")
    assert result.reason is RefusalReason.PRESENTER_KEY_MISMATCH
    assert result.step == 8


def test_jws_verify_refuses_a_wrong_length_key_cleanly() -> None:
    """`jws.verify` is a public function of this codec, unused by
    `recipient.verify` itself (which does its own inline check) but still part
    of what a reader could reasonably call directly -- it must not crash on a
    key of the wrong length either."""
    fx = _build()
    assert fx.request.permit_token is not None
    try:
        jws.verify(fx.request.permit_token, b"\x00" * 65)
    except jws.SignatureInvalid:
        pass
    else:
        raise AssertionError("a 65-byte key was accepted without crashing or refusing")


def test_a_valid_length_but_wrong_curve_key_fails_verification_cleanly() -> None:
    """32 bytes of the wrong kind of key material (not a real Ed25519 point) is
    accepted by key construction (Ed25519 point validation is lazy) but must
    still fail signature verification cleanly, never crash."""
    fx = _build()
    garbage_32_bytes = b"\x01" * 32
    result = _verify(fx, resolve_presenter_key=lambda jkt: garbage_32_bytes)
    # A 32-byte value that happens not to equal the real presenter key's own
    # thumbprint is refused at the thumbprint-consistency check, before any
    # signature math -- also a clean refusal, not a crash.
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.PRESENTER_KEY_MISMATCH


# --- Item 9: JCS given duplicate keys, lone surrogates, non-integer numbers -----------


def test_jcs_refuses_a_lone_surrogate_cleanly() -> None:
    """Direct unit test: a lone UTF-16 surrogate cannot be encoded to UTF-8, and
    must be refused by this module's own exception type, not let a raw
    `UnicodeEncodeError` escape from the final encode step several calls later."""
    try:
        jcs.canonical_bytes({"x": "\ud800"})
    except jcs.NotCanonicalizable:
        pass
    else:
        raise AssertionError("a lone surrogate was silently canonicalized")


def test_jcs_refuses_a_lone_surrogate_in_an_object_key() -> None:
    try:
        jcs.canonical_bytes({"\ud800": "value"})
    except jcs.NotCanonicalizable:
        pass
    else:
        raise AssertionError("a lone surrogate object key was silently canonicalized")


def test_jcs_refuses_a_float() -> None:
    try:
        jcs.canonical_bytes({"amount": 1.5})
    except jcs.NotCanonicalizable:
        pass
    else:
        raise AssertionError("a float was silently canonicalized")


def test_jcs_refuses_a_decimal() -> None:
    """`Decimal` is not a `float` subclass, so it must be caught by the
    catch-all type check, not silently pass through as some other JSON-legal
    shape -- it is a non-integer number just as much as a float is."""
    try:
        jcs.canonical_bytes({"amount": Decimal("1.5")})
    except jcs.NotCanonicalizable:
        pass
    else:
        raise AssertionError("a Decimal was silently canonicalized")


def test_action_digest_refuses_rather_than_crashes_on_a_lone_surrogate() -> None:
    try:
        action_digest({"note": "\ud800"})
    except jcs.NotCanonicalizable:
        pass
    else:
        raise AssertionError("action_digest silently canonicalized a lone surrogate")


def test_recipient_refuses_cleanly_when_the_derived_action_object_has_a_lone_surrogate() -> None:
    """End to end: a caller-derived action object carrying a lone surrogate
    (something a naive JSON decoder on the recipient's own request-parsing
    side could produce from attacker-controlled bytes) must not crash
    `verify()` -- it is refused at step 9, same as any other action mismatch."""
    fx = _build()
    fx = replace(fx, request=replace(fx.request, action_object={"note": "\ud800"}))
    result = _verify(fx)
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.ACTION_MISMATCH
    assert result.step == 9


def test_jws_parse_rejects_a_duplicate_key_in_the_payload() -> None:
    """A Python `dict` cannot carry a duplicate key by construction, so this
    must be built from raw JSON TEXT rather than through `jws.encode`."""
    header_b64 = _b64url(json.dumps({"alg": "EdDSA", "typ": "aadp-permit+jwt"}).encode())
    payload_json = '{"iss":"https://a.example","iss":"https://b.example","jti":"x"}'
    payload_b64 = _b64url(payload_json.encode())
    token = f"{header_b64}.{payload_b64}.{_b64url(b'x' * 64)}"
    try:
        jws.parse(token)
    except jws.MalformedJWS:
        pass
    else:
        raise AssertionError("a duplicate object key was silently resolved (last-wins)")


def test_jws_parse_rejects_a_duplicate_key_in_the_header() -> None:
    header_json = '{"alg":"EdDSA","typ":"aadp-permit+jwt","typ":"jwt"}'
    header_b64 = _b64url(header_json.encode())
    payload_b64 = _b64url(json.dumps({"a": 1}).encode())
    token = f"{header_b64}.{payload_b64}.{_b64url(b'x' * 64)}"
    try:
        jws.parse(token)
    except jws.MalformedJWS:
        pass
    else:
        raise AssertionError("a duplicate header key was silently resolved (last-wins)")


def test_recipient_refuses_a_permit_with_a_duplicate_claim_key() -> None:
    """End to end: a permit whose payload text names a required claim twice
    must be refused as malformed, not silently resolved to whichever value the
    parser happens to keep."""
    fx = _build()
    header_b64 = _b64url(json.dumps({"alg": "EdDSA", "typ": "aadp-permit+jwt"}).encode())
    claims_with_dup = json.dumps(fx.claims)[:-1] + ',"jti":"a-second-jti"}'
    payload_b64 = _b64url(claims_with_dup.encode())
    token = f"{header_b64}.{payload_b64}.{_b64url(b'x' * 64)}"
    result = _verify(_swap_token(fx, token))
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.MALFORMED
    assert result.step == 1


# --- httpsig: the fixed component set is exactly what gets signed and checked --------


def test_httpsig_covers_exactly_the_seven_declared_components() -> None:
    assert httpsig.COVERED_COMPONENTS == (
        "@method",
        "@authority",
        "@path",
        "@query",
        "content-digest",
        "idempotency-key",
        "aadp-permit",
    )


def test_changing_the_method_after_signing_breaks_verification() -> None:
    fx = _build()
    result = _verify(replace(fx, request=replace(fx.request, method="GET")))
    assert result.status is not VerificationStatus.VERIFIED
    assert result.reason is RefusalReason.REQUEST_SIGNATURE_INVALID


def test_changing_the_authority_after_signing_breaks_verification() -> None:
    fx = _build()
    result = _verify(replace(fx, request=replace(fx.request, authority="evil.example")))
    assert result.status is not VerificationStatus.VERIFIED
    assert result.reason is RefusalReason.REQUEST_SIGNATURE_INVALID


def test_changing_the_query_after_signing_breaks_verification() -> None:
    fx = _build()
    result = _verify(replace(fx, request=replace(fx.request, query="?evil=1")))
    assert result.status is not VerificationStatus.VERIFIED
    assert result.reason is RefusalReason.REQUEST_SIGNATURE_INVALID


def test_changing_the_idempotency_key_after_signing_breaks_verification() -> None:
    fx = _build()
    result = _verify(replace(fx, request=replace(fx.request, idempotency_key_header="different")))
    assert result.status is not VerificationStatus.VERIFIED
    assert result.reason is RefusalReason.REQUEST_SIGNATURE_INVALID


def test_a_component_the_presenter_never_signed_over_cannot_be_added_and_still_verify() -> None:
    """Proves the set is fixed, not extensible by a presenter: `sign`/`verify`
    only ever construct a base over `COVERED_COMPONENTS`, so a component value
    passed in addition to those seven is silently ignored by `signature_base`
    itself -- there is no way for a caller of this module to cover anything
    beyond the fixed seven, whatever extra dict entries it supplies."""
    fx = _build()
    extra = {
        "@method": fx.request.method.upper(),
        "@authority": fx.request.authority.lower(),
        "@path": fx.request.path,
        "@query": fx.request.query,
        "content-digest": fx.request.content_digest_header,
        "idempotency-key": fx.request.idempotency_key_header,
        "aadp-permit": fx.request.permit_token,
        "x-injected": "attacker-controlled",
    }
    base_with_extra = httpsig.signature_base(extra, created=0, keyid="k")
    base_without_extra = httpsig.signature_base(
        {k: v for k, v in extra.items() if k != "x-injected"}, created=0, keyid="k"
    )
    assert base_with_extra == base_without_extra


def test_httpsig_verify_rejects_a_signature_over_a_bare_ed25519_message_mismatch() -> None:
    """Sanity check on the underlying primitive this module wraps: a signature
    that is well-formed but simply wrong (made over different bytes) is
    InvalidSignature, not silently accepted."""
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    sig = priv.sign(b"message one")
    try:
        pub.verify(sig, b"message two")
    except InvalidSignature:
        pass
    else:
        raise AssertionError("a signature over different bytes verified")
