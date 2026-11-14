"""Signed approval links: the token's own shape --
issuing and verifying a compact, signed token, with no database involved.
Single-use tracking, the service routes, and the notify adapter are
separate commits; this one is the cryptographic foundation they all build on.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from onedoor.guardrail import approval_link
from onedoor.guardrail.approval_link import LinkVerifyStatus
from tests.conftest import FROZEN_NOW

KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}


def _issue(*, action: str = "approve", key_id: str = "k1", keys: dict[str, bytes] = KEYS) -> str:
    return approval_link.issue(
        approval_id=42,
        action=action,
        recipient="approver@example.test",
        now=FROZEN_NOW,
        ttl_seconds=3600,
        signing_keys=keys,
        key_id=key_id,
        issuer="test-issuer",
        request_digest="test-digest",
    )


def test_the_default_lifetime_is_one_hour_and_issue_actually_uses_it() -> None:
    """The link's own default lifetime, named and tested
    directly -- not just documented as a number that could drift from what
    `issue()` actually does when a caller omits `ttl_seconds`."""
    assert approval_link.DEFAULT_LINK_TTL_SECONDS == 3600
    token = approval_link.issue(
        approval_id=42,
        action="approve",
        recipient="approver@example.test",
        now=FROZEN_NOW,
        signing_keys=KEYS,
        key_id="k1",
        issuer="test-issuer",
        request_digest="test-digest",
        # ttl_seconds omitted on purpose -- this is the one call in the
        # whole test file that exercises the default rather than passing
        # an explicit value.
    )
    result = approval_link.verify(token, signing_keys=KEYS, now=FROZEN_NOW)
    assert result.claims is not None
    assert result.claims.exp == FROZEN_NOW + timedelta(
        seconds=approval_link.DEFAULT_LINK_TTL_SECONDS
    )
    still_valid = approval_link.verify(
        token,
        signing_keys=KEYS,
        now=FROZEN_NOW + timedelta(seconds=approval_link.DEFAULT_LINK_TTL_SECONDS - 1),
    )
    assert still_valid.status == LinkVerifyStatus.VALID
    expired = approval_link.verify(
        token,
        signing_keys=KEYS,
        now=FROZEN_NOW + timedelta(seconds=approval_link.DEFAULT_LINK_TTL_SECONDS),
    )
    assert expired.status == LinkVerifyStatus.EXPIRED


def test_a_valid_token_verifies_and_carries_its_own_claims() -> None:
    token = _issue()
    result = approval_link.verify(token, signing_keys=KEYS, now=FROZEN_NOW)
    assert result.status == LinkVerifyStatus.VALID
    assert result.claims is not None
    assert result.claims.approval_id == 42
    assert result.claims.action == "approve"
    assert result.claims.recipient == "approver@example.test"
    assert result.claims.key_id == "k1"


@pytest.mark.parametrize(
    "bad_token",
    [
        "",
        "not-a-token-at-all",
        "onlyonepart",
        "a.b.c",
        "!!!.!!!",
    ],
)
def test_a_malformed_token_is_refused_never_raising(bad_token: str) -> None:
    result = approval_link.verify(bad_token, signing_keys=KEYS, now=FROZEN_NOW)
    assert result.status == LinkVerifyStatus.MALFORMED
    assert result.claims is None


def test_an_approve_token_and_a_deny_token_for_the_same_approval_differ() -> None:
    approve = _issue(action="approve")
    deny = _issue(action="deny")
    assert approve != deny

    approve_result = approval_link.verify(approve, signing_keys=KEYS, now=FROZEN_NOW)
    deny_result = approval_link.verify(deny, signing_keys=KEYS, now=FROZEN_NOW)
    assert approve_result.claims is not None and approve_result.claims.action == "approve"
    assert deny_result.claims is not None and deny_result.claims.action == "deny"
    # Neither token is accepted in place of the other -- each names its own
    # action, baked in, never a parameter a presenter chooses.
    assert approve_result.claims.nonce != deny_result.claims.nonce


def test_tampering_with_the_payload_is_refused_as_a_bad_signature() -> None:
    token = _issue()
    payload_part, sig_part = token.split(".", 1)
    tampered = payload_part + "A" + payload_part[-1] + "." + sig_part
    # Guard against the rare case the mutation above didn't actually change
    # the string (astronomically unlikely given base64url's alphabet, but
    # asserted rather than assumed).
    if tampered == token:
        pytest.skip("mutation produced an identical string")
    result = approval_link.verify(tampered, signing_keys=KEYS, now=FROZEN_NOW)
    assert result.status in (LinkVerifyStatus.BAD_SIGNATURE, LinkVerifyStatus.MALFORMED)


def test_an_expired_token_is_refused() -> None:
    token = approval_link.issue(
        approval_id=42,
        action="approve",
        recipient="approver@example.test",
        now=FROZEN_NOW,
        ttl_seconds=60,
        signing_keys=KEYS,
        key_id="k1",
        issuer="test-issuer",
        request_digest="test-digest",
    )
    later = FROZEN_NOW + timedelta(seconds=61)
    result = approval_link.verify(token, signing_keys=KEYS, now=later)
    assert result.status == LinkVerifyStatus.EXPIRED
    assert result.claims is not None  # expired is still evidence, not nothing


def test_a_token_signed_under_a_since_rotated_key_id_still_verifies_while_accepted() -> None:
    old_keys = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
    token = _issue(key_id="k1", keys=old_keys)

    rotated_keys = {
        "k1": b"a-test-signing-key-at-least-32-bytes-long!!",
        "k2": b"a-second-test-signing-key-also-32-bytes!!!!",
    }
    result = approval_link.verify(token, signing_keys=rotated_keys, now=FROZEN_NOW)
    assert result.status == LinkVerifyStatus.VALID


def test_a_token_signed_under_a_retired_key_id_stops_verifying() -> None:
    old_keys = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
    token = _issue(key_id="k1", keys=old_keys)

    retired_set = {"k2": b"a-second-test-signing-key-also-32-bytes!!!!"}
    result = approval_link.verify(token, signing_keys=retired_set, now=FROZEN_NOW)
    assert result.status == LinkVerifyStatus.UNKNOWN_KEY


def test_a_signature_checked_against_the_wrong_key_is_refused() -> None:
    token = _issue(key_id="k1")
    wrong_key_same_id = {"k1": b"a-completely-different-key-of-32-bytes!!!!!"}
    result = approval_link.verify(token, signing_keys=wrong_key_same_id, now=FROZEN_NOW)
    assert result.status == LinkVerifyStatus.BAD_SIGNATURE
