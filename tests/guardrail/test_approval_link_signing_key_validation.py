"""`NotifyConfig` validates its own signing keys at construction:
an empty or short key, or a key id absent from its own dict, fails
a deployment at startup rather than being discovered as a forgeable link
the first time one is ever issued or verified.
"""

from __future__ import annotations

import pytest

from onedoor.guardrail.approval_link import MIN_SIGNING_KEY_BYTES, NotifyConfig

GOOD_KEY = b"a-test-signing-key-at-least-32-bytes-long!!"
assert len(GOOD_KEY) >= MIN_SIGNING_KEY_BYTES


def test_a_key_shorter_than_the_minimum_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="byte"):
        NotifyConfig(
            approval_link_base_url="https://onedoor.example/links",
            approval_link_signing_keys={"k1": b"too-short"},
            approval_link_signing_key_id="k1",
            approval_link_issuer="test-deployment",
        )


def test_an_empty_key_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="byte"):
        NotifyConfig(
            approval_link_base_url="https://onedoor.example/links",
            approval_link_signing_keys={"k1": b""},
            approval_link_signing_key_id="k1",
            approval_link_issuer="test-deployment",
        )


def test_a_signing_key_id_absent_from_its_own_dict_is_refused() -> None:
    with pytest.raises(ValueError, match="not a key present"):
        NotifyConfig(
            approval_link_base_url="https://onedoor.example/links",
            approval_link_signing_keys={"k1": GOOD_KEY},
            approval_link_signing_key_id="k2",
            approval_link_issuer="test-deployment",
        )


def test_a_str_key_is_refused_even_at_sufficient_length() -> None:
    """A `str` of sufficient length passes the length check just
    as readily as real key material, but `hmac.new()` (at first use, in
    `issue()`/`verify()`) refuses it with a `TypeError` -- the wrong
    failure, at the wrong time, against this class's own "validated at
    construction" discipline. Checked explicitly instead of relying on
    the length check to catch it by accident."""
    text_key = "x" * MIN_SIGNING_KEY_BYTES
    with pytest.raises(TypeError, match="not bytes"):
        NotifyConfig(
            approval_link_base_url="https://onedoor.example/links",
            approval_link_signing_keys={"k1": text_key},  # type: ignore[dict-item]
            approval_link_signing_key_id="k1",
            approval_link_issuer="test-deployment",
        )


def test_a_key_at_exactly_the_minimum_length_is_accepted() -> None:
    key = b"x" * MIN_SIGNING_KEY_BYTES
    config = NotifyConfig(
        approval_link_base_url="https://onedoor.example/links",
        approval_link_signing_keys={"k1": key},
        approval_link_signing_key_id="k1",
        approval_link_issuer="test-deployment",
    )
    assert config.approval_link_signing_keys["k1"] == key
