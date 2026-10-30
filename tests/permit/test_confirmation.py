"""`onedoor.permit.confirmation`: the recipient confirmation (bound-permit
profile §10, V22), built from a real `recipient.verify()` result and checked
back against reference values, independently of `verify()` itself.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from onedoor.permit import confirmation, jws
from onedoor.permit.models import RefusalReason, VerificationResult, VerificationStatus
from onedoor.permit.recipient import InMemoryConsumeStore, complete_reservation
from tests.permit.test_recipient import NOW, _build, _verify


def _recipient_identity() -> tuple[str, Ed25519PrivateKey]:
    from onedoor.permit.jwk import thumbprint

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)
    return thumbprint(public), private


# ---------------------------------------------------------------------------
# build(): the happy path and the "once step N passed" rule
# ---------------------------------------------------------------------------


def test_build_on_a_verified_result_carries_every_digest() -> None:
    fx = _build()
    result = _verify(fx)
    assert result.status is VerificationStatus.VERIFIED
    kid, priv = _recipient_identity()

    token = confirmation.build(
        fx.request,
        result,
        recipient_key_id=kid,
        recipient_private_key=priv,
        now=NOW,
        outcome="effected",
        recipient_action_id="TX-1",
    )
    _, payload = jws.verify(token, priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert payload["outcome"] == "effected"
    assert payload["recipient_action_id"] == "TX-1"
    assert "permit" in payload
    assert "signature_base_digest" in payload["request"]
    assert "action_digest" in payload
    assert "step" not in payload
    assert "reason" not in payload


def test_build_effected_requires_a_recipient_action_id() -> None:
    fx = _build()
    result = _verify(fx)
    kid, priv = _recipient_identity()
    with pytest.raises(confirmation.ConfirmationError):
        confirmation.build(
            fx.request,
            result,
            recipient_key_id=kid,
            recipient_private_key=priv,
            now=NOW,
            outcome="effected",
        )


def test_build_on_a_refused_result_fixes_outcome_and_carries_step_and_reason() -> None:
    fx = _build(amount_max="2000.00")  # over the issuer's own 1000.00 limit -> step 6
    result = _verify(fx)
    assert result.status is VerificationStatus.REFUSED
    assert result.step == 6
    kid, priv = _recipient_identity()

    token = confirmation.build(
        fx.request, result, recipient_key_id=kid, recipient_private_key=priv, now=NOW
    )
    _, payload = jws.verify(token, priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert payload["outcome"] == "refused"
    assert payload["step"] == 6
    assert payload["reason"] == RefusalReason.ISSUER_OUT_OF_SCOPE.value
    # Step 6 failed after step 1 (permit parsed) but before step 7 (content
    # digest) -- the permit is cited, the request digests are not.
    assert "permit" in payload
    assert "request" not in payload
    assert "action_digest" not in payload


def test_build_on_a_refusal_before_the_permit_parses_cites_no_permit() -> None:
    fx = _build()
    broken = replace(fx.request, permit_token="not-a-jws")
    result = _verify(replace(fx, request=broken))
    assert result.status is VerificationStatus.REFUSED
    assert result.step == 1
    kid, priv = _recipient_identity()

    token = confirmation.build(
        broken, result, recipient_key_id=kid, recipient_private_key=priv, now=NOW
    )
    _, payload = jws.verify(token, priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert "permit" not in payload  # nothing to cite before step 1 passes


def test_build_on_a_could_not_check_result_fixes_outcome_refused_with_dependency() -> None:
    """A could-not-check confirmation has `outcome: "refused"` and
    `dependency`, never `step` or `reason` -- the recipient did not act, and
    does not know which numbered step it would have failed or passed."""
    fx = _build()
    result = VerificationResult(
        status=VerificationStatus.COULD_NOT_CHECK, dependency="consume-store"
    )
    kid, priv = _recipient_identity()

    token = confirmation.build(
        fx.request, result, recipient_key_id=kid, recipient_private_key=priv, now=NOW
    )
    _, payload = jws.verify(token, priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert payload["outcome"] == "refused"
    assert payload["dependency"] == "consume-store"
    assert "step" not in payload
    assert "reason" not in payload
    # consume-store is step 13's own dependency: steps 1-12 passed, so permit,
    # request and action_digest are all legitimately established.
    assert "permit" in payload
    assert "action_digest" in payload


def test_build_on_a_could_not_check_at_step_8_cites_no_request_digests() -> None:
    fx = _build()
    result = VerificationResult(
        status=VerificationStatus.COULD_NOT_CHECK, dependency="presenter-key-directory"
    )
    kid, priv = _recipient_identity()

    token = confirmation.build(
        fx.request, result, recipient_key_id=kid, recipient_private_key=priv, now=NOW
    )
    _, payload = jws.verify(token, priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert payload["dependency"] == "presenter-key-directory"
    assert "permit" in payload  # step 1-7 passed
    assert payload["request"] == {"content_digest": payload["request"]["content_digest"]}
    assert "signature_base_digest" not in payload["request"]  # step 8 itself never completed
    assert "action_digest" not in payload


def test_sabotage_an_unrecognised_dependency_is_treated_conservatively() -> None:
    """If the step-in-progress mapping were missing an entry, the conservative
    default (step 1: nothing established) is what stands between an unmapped
    dependency string and an over-inclusive confirmation."""
    import onedoor.permit.confirmation as mod

    fx = _build()
    result = VerificationResult(
        status=VerificationStatus.COULD_NOT_CHECK, dependency="consume-store"
    )
    kid, priv = _recipient_identity()

    original = dict(mod._COULD_NOT_CHECK_STEP_IN_PROGRESS)
    try:
        mod._COULD_NOT_CHECK_STEP_IN_PROGRESS.pop("consume-store")  # SABOTAGE
        token = confirmation.build(
            fx.request, result, recipient_key_id=kid, recipient_private_key=priv, now=NOW
        )
    finally:
        mod._COULD_NOT_CHECK_STEP_IN_PROGRESS.clear()
        mod._COULD_NOT_CHECK_STEP_IN_PROGRESS.update(original)
    _, payload = jws.verify(token, priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
    assert "permit" not in payload, (
        "with the mapping entry removed, the unmapped dependency falls back to "
        "step 1 (nothing established) -- confirming the default is load-bearing, "
        "not merely cosmetic, since consume-store (step 13) would otherwise "
        "legitimately include the permit"
    )


# ---------------------------------------------------------------------------
# check(): unknown payload members are ignored and named in the key row's
# own detail, never refused.
# ---------------------------------------------------------------------------


def _signed(kid: str, priv: Ed25519PrivateKey, payload: dict) -> str:  # type: ignore[type-arg]
    return jws.encode({"alg": "EdDSA", "kid": kid, "typ": "aadp-confirmation+jwt"}, payload, priv)


def _check(token, **over):  # type: ignore[no-untyped-def]
    kwargs: dict[str, object] = dict(
        permit_token="x.y.z",
        permit_aud="https://r.example",
        content_digest="sha-256=::",
        signature_base="",
        action_digest="sha-256=::",
        step_started=0,
        step_ended=1_000_000_000,
        step_outcome_ok=False,
        recipients={},
    )
    kwargs.update(over)
    return confirmation.check(token, **kwargs)  # type: ignore[arg-type]


def test_check_ignores_an_unknown_payload_member_and_names_it() -> None:
    kid, priv = _recipient_identity()
    token = _signed(
        kid, priv, {"iss": "https://r.example", "outcome": "refused", "iat": 1, "extra": 1}
    )
    result = _check(
        token,
        recipients={
            "https://r.example": {
                kid: priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            }
        },
    )
    assert result.status is VerificationStatus.VERIFIED
    assert "extra" in result.detail


def test_sabotage_without_the_known_field_check_an_unknown_member_is_not_named() -> None:
    import onedoor.permit.confirmation as mod

    kid, priv = _recipient_identity()
    token = _signed(
        kid, priv, {"iss": "https://r.example", "outcome": "refused", "iat": 1, "extra": 1}
    )
    recipients = {
        "https://r.example": {kid: priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}
    }

    original = mod._KNOWN_PAYLOAD_FIELDS
    try:
        mod._KNOWN_PAYLOAD_FIELDS = original | {"extra"}  # SABOTAGE: widen the allow-list
        result = _check(token, recipients=recipients)
    finally:
        mod._KNOWN_PAYLOAD_FIELDS = original
    assert result.detail == "", (
        "with 'extra' allow-listed, it is no longer unknown -- confirming the "
        "allow-list is what test_check_ignores_an_unknown_payload_member_and_names_it "
        "actually exercises"
    )


def test_check_distinguishes_no_list_from_not_listed() -> None:
    kid, priv = _recipient_identity()
    token = _signed(kid, priv, {"iss": "https://r.example", "outcome": "refused", "iat": 1})
    no_list = _check(token, recipients={})
    assert no_list.status is VerificationStatus.COULD_NOT_CHECK
    assert "no recipient list given" in no_list.detail

    not_listed = _check(token, recipients={"https://someone-else.example": {}})
    assert not_listed.status is VerificationStatus.COULD_NOT_CHECK
    assert "is not on the list" in not_listed.detail


def test_check_c20_no_confirmation_recorded_is_could_not_check() -> None:
    result = _check(None, step_outcome_ok=True)
    assert result.status is VerificationStatus.COULD_NOT_CHECK
    assert "no confirmation recorded" in result.detail


def test_check_no_confirmation_and_step_was_not_ok_passes() -> None:
    result = _check(None, step_outcome_ok=False)
    assert result.status is VerificationStatus.VERIFIED


def test_check_iat_window_fails_the_request_row() -> None:
    kid, priv = _recipient_identity()
    token = _signed(kid, priv, {"iss": "https://r.example", "outcome": "refused", "iat": 10_000})
    result = _check(
        token,
        recipients={
            "https://r.example": {
                kid: priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            }
        },
        step_started=0,
        step_ended=100,
    )
    assert result.status is VerificationStatus.REFUSED
    assert "outside the step" in result.detail


def test_check_permit_aud_mismatch_fails_the_permit_row() -> None:
    kid, priv = _recipient_identity()
    token = _signed(kid, priv, {"iss": "https://ledger.example", "outcome": "refused", "iat": 1})
    result = _check(
        token,
        permit_aud="https://payments.example",
        recipients={
            "https://ledger.example": {
                kid: priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            }
        },
    )
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.CONFIRMATION_PERMIT_MISMATCH
    assert "but the permit is for" in result.detail


def test_check_not_ok_but_effected_fails_the_outcome_row() -> None:
    kid, priv = _recipient_identity()
    token = _signed(
        kid,
        priv,
        {
            "iss": "https://r.example",
            "outcome": "effected",
            "recipient_action_id": "TX-1",
            "iat": 1,
        },
    )
    result = _check(
        token,
        recipients={
            "https://r.example": {
                kid: priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            }
        },
        step_outcome_ok=False,
    )
    assert result.status is VerificationStatus.REFUSED
    assert result.reason is RefusalReason.CONFIRMATION_OUTCOME_MISMATCH
    assert "it acted" in result.detail


# ---------------------------------------------------------------------------
# Repeats: the stored confirmation token (StoredConsumption.confirmation_token)
# ---------------------------------------------------------------------------


def test_a_repeat_returns_the_attached_confirmation_token_byte_for_byte() -> None:
    fx = _build()
    store = InMemoryConsumeStore()
    first = _verify(fx, consume_store=store)
    assert first.status is VerificationStatus.VERIFIED
    assert first.repeat is False
    assert first.confirmation_token is None

    kid, priv = _recipient_identity()
    token = confirmation.build(
        fx.request,
        first,
        recipient_key_id=kid,
        recipient_private_key=priv,
        now=NOW,
        outcome="effected",
        recipient_action_id="TX-1",
    )
    iss = fx.claims["iss"]
    jti = fx.claims["jti"]
    content_digest = fx.request.content_digest_header.strip()
    complete_reservation(store, iss, jti, content_digest=content_digest, confirmation_token=token)

    second = _verify(fx, consume_store=store)
    assert second.status is VerificationStatus.VERIFIED
    assert second.repeat is True
    assert second.confirmation_token == token


def test_sabotage_dropping_the_field_a_repeat_forgets_its_own_token() -> None:
    """If `verify()`'s repeat branch stopped forwarding `confirmation_token`,
    a repeat would come back with no token at all -- exactly the "repeat does
    not return the same token" failure draft §5 forbids."""
    import tests.permit.test_recipient as recipient_test_mod

    fx = _build()
    store = InMemoryConsumeStore()
    first = _verify(fx, consume_store=store)
    kid, priv = _recipient_identity()
    token = confirmation.build(
        fx.request,
        first,
        recipient_key_id=kid,
        recipient_private_key=priv,
        now=NOW,
        outcome="effected",
        recipient_action_id="TX-1",
    )
    iss, jti = fx.claims["iss"], fx.claims["jti"]
    complete_reservation(
        store,
        iss,
        jti,
        content_digest=fx.request.content_digest_header.strip(),
        confirmation_token=token,
    )

    original_verify = recipient_test_mod.verify

    def sabotaged(*args, **kwargs):  # type: ignore[no-untyped-def]
        result = original_verify(*args, **kwargs)
        if result.repeat:
            return replace(result, confirmation_token=None)  # SABOTAGE
        return result

    recipient_test_mod.verify = sabotaged
    try:
        second = _verify(fx, consume_store=store)
    finally:
        recipient_test_mod.verify = original_verify
    assert second.repeat is True
    assert second.confirmation_token is None, "sabotage should have dropped the token"


# ---------------------------------------------------------------------------
# find_reused_permits
# ---------------------------------------------------------------------------


def test_find_reused_permits_skips_tokens_that_do_not_parse() -> None:
    assert confirmation.find_reused_permits(["not-a-jws"]) == []


def test_find_reused_permits_ignores_non_effected_tokens() -> None:
    kid, priv = _recipient_identity()
    token = _signed(
        kid,
        priv,
        {
            "iss": "r",
            "permit": {"iss": "i", "jti": "j", "digest": "d"},
            "outcome": "refused",
            "iat": 1,
        },
    )
    assert confirmation.find_reused_permits([token, token]) == []
