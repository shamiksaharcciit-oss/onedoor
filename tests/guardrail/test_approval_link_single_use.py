"""Signed approval links: single-use tracking against the database
(migration 0045). The token's own shape (pure,
no database) is `test_approval_link.py`; this is the consuming resolution
a POST route takes, and the pruning that keeps the nonce table bounded.
"""

from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

from onedoor.guardrail import approval_link
from onedoor.guardrail.approval_link import LinkVerifyStatus
from tests.conftest import FROZEN_NOW

KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}


def _issue(*, action: str = "approve") -> str:
    return approval_link.issue(
        approval_id=42,
        action=action,
        recipient="approver@example.test",
        now=FROZEN_NOW,
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer="test-issuer",
        request_digest="test-digest",
    )


def test_a_valid_link_resolves_and_consumes_its_nonce_exactly_once(conn: Connection) -> None:
    token = _issue()
    first = approval_link.resolve(conn, token, signing_keys=KEYS, now=FROZEN_NOW)
    assert first.status == LinkVerifyStatus.VALID

    second = approval_link.resolve(conn, token, signing_keys=KEYS, now=FROZEN_NOW)
    assert second.status == LinkVerifyStatus.CONSUMED
    assert second.claims is not None  # consumed is still evidence


def test_verify_alone_never_consumes_the_nonce(conn: Connection) -> None:
    """The GET route (a confirmation page only, never acting) must use
    `verify()`, not `resolve()` -- checked directly here: calling `verify`
    any number of times never touches the nonce table, so a later `resolve`
    still succeeds."""
    token = _issue()
    for _ in range(5):
        result = approval_link.verify(token, signing_keys=KEYS, now=FROZEN_NOW)
        assert result.status == LinkVerifyStatus.VALID

    resolved = approval_link.resolve(conn, token, signing_keys=KEYS, now=FROZEN_NOW)
    assert resolved.status == LinkVerifyStatus.VALID


def test_an_expired_links_resolution_never_consumes_the_nonce(conn: Connection) -> None:
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
    result = approval_link.resolve(conn, token, signing_keys=KEYS, now=later)
    assert result.status == LinkVerifyStatus.EXPIRED

    rows = conn.execute("SELECT COUNT(*) FROM approval_link_uses").fetchone()[0]
    assert rows == 0, "nothing to consume for a ref that was never going to grant anything"


def test_an_approve_and_a_deny_token_for_the_same_approval_consume_independently(
    conn: Connection,
) -> None:
    approve = _issue(action="approve")
    deny = _issue(action="deny")

    first = approval_link.resolve(conn, approve, signing_keys=KEYS, now=FROZEN_NOW)
    assert first.status == LinkVerifyStatus.VALID
    second = approval_link.resolve(conn, deny, signing_keys=KEYS, now=FROZEN_NOW)
    assert second.status == LinkVerifyStatus.VALID  # a different nonce, not blocked by the first

    # Each is still single-use on its own.
    assert approval_link.resolve(conn, approve, signing_keys=KEYS, now=FROZEN_NOW).status == (
        LinkVerifyStatus.CONSUMED
    )
    assert approval_link.resolve(conn, deny, signing_keys=KEYS, now=FROZEN_NOW).status == (
        LinkVerifyStatus.CONSUMED
    )


def test_pruning_removes_only_nonces_past_their_own_expiry(conn: Connection) -> None:
    short_lived = approval_link.issue(
        approval_id=1,
        action="approve",
        recipient="a@example.test",
        now=FROZEN_NOW,
        ttl_seconds=60,
        signing_keys=KEYS,
        key_id="k1",
        issuer="test-issuer",
        request_digest="test-digest",
    )
    long_lived = approval_link.issue(
        approval_id=2,
        action="approve",
        recipient="b@example.test",
        now=FROZEN_NOW,
        ttl_seconds=3600,
        signing_keys=KEYS,
        key_id="k1",
        issuer="test-issuer",
        request_digest="test-digest",
    )
    approval_link.resolve(conn, short_lived, signing_keys=KEYS, now=FROZEN_NOW)
    approval_link.resolve(conn, long_lived, signing_keys=KEYS, now=FROZEN_NOW)
    assert conn.execute("SELECT COUNT(*) FROM approval_link_uses").fetchone()[0] == 2

    later = FROZEN_NOW + timedelta(seconds=120)
    pruned = approval_link.prune_expired_uses(conn, now=later)
    assert pruned == 1
    remaining = conn.execute("SELECT approval_id FROM approval_link_uses").fetchall()
    assert [r[0] for r in remaining] == [2]
