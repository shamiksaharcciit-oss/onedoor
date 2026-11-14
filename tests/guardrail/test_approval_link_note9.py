"""Small link-mechanism gaps.
- strict base64url decoding (an early padding character refuses rather
  than silently truncating the payload);
- a negative or zero ttl_seconds is refused at issue();
link_used_at (set on the first vote, not overwritten by a second), the
idempotent-notify-on-replay, and the GET "consumed" status are each
exercised at the service layer: the first two in
test_approval_link_first_vote_sets_used_at.py and
test_approval_link_idempotent_notify.py, the third in
test_approval_link_routes.py.
"""

from __future__ import annotations

import pytest

from onedoor.guardrail import approval_link
from onedoor.guardrail.approval_link import LinkVerifyStatus
from tests.conftest import FROZEN_NOW

KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}


def _issue(**overrides: object) -> str:
    kw: dict[str, object] = dict(
        approval_id=42,
        action="approve",
        recipient="approver@example.test",
        now=FROZEN_NOW,
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer="test-issuer",
        request_digest="test-digest",
    )
    kw.update(overrides)
    return approval_link.issue(**kw)  # type: ignore[arg-type]


def test_an_early_padding_character_is_refused_not_silently_truncated() -> None:
    """Non-strict base64 decoding treats an early `=` as the start of
    padding and silently stops there, decoding to a truncated prefix of
    the real data rather than refusing -- demonstrated directly against
    `_b64url_decode` (the unit this fix actually changed), since at the
    full `verify()` level a truncated payload also fails to parse as
    JSON, a second, independent safety net that would mask the
    difference between strict and non-strict decoding for this
    particular wire format. Strict decoding (`validate=True`) refuses
    this ("excess data after padding") rather than truncating."""
    from onedoor.guardrail.approval_link import _b64url_decode

    good = approval_link._b64url_encode(b"hello world, this is a longer payload for testing")
    tampered = good[:3] + "=" + good[3:]
    with pytest.raises(Exception, match="xcess data"):
        _b64url_decode(tampered)


def test_a_tampered_token_is_still_refused_end_to_end() -> None:
    """Sanity check at the full verify() level: the same tampering above
    is refused end to end too (via JSON-parse failure on the truncated
    bytes, a second line of defense -- not the assertion this fix is
    actually tested by, see the unit test above)."""
    token = _issue()
    payload_part, sig_part = token.split(".", 1)
    tampered = payload_part[:3] + "=" + payload_part[3:] + "." + sig_part
    result = approval_link.verify(tampered, signing_keys=KEYS, now=FROZEN_NOW)
    assert result.status == LinkVerifyStatus.MALFORMED


def test_a_negative_ttl_is_refused_at_issue() -> None:
    with pytest.raises(ValueError, match="positive"):
        _issue(ttl_seconds=-1)


def test_a_zero_ttl_is_refused_at_issue() -> None:
    with pytest.raises(ValueError, match="positive"):
        _issue(ttl_seconds=0)
