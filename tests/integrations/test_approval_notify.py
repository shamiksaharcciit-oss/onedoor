"""The approval_notify adapter builds the
approve and deny links for one approval and dispatches them via a
deployment-supplied stand-in sender. Tested against stand-in senders
only -- nothing here ever opens a real socket to a mail server or a
webhook host.
"""

from __future__ import annotations

import socket

import pytest

from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import ApprovalNotify
from onedoor.integrations import approval_notify
from tests.conftest import FROZEN_NOW

KEYS = {"k1": b"a-test-signing-key-at-least-32-bytes-long!!"}
CONFIG = NotifyConfig(
    approval_link_base_url="https://onedoor.example/links",
    approval_link_signing_keys=KEYS,
    approval_link_signing_key_id="k1",
    approval_link_issuer="test-deployment",
)


@pytest.fixture(autouse=True)
def _no_real_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """A belt-and-suspenders guard, not the only proof: `socket.socket`
    itself refuses to construct for the duration of every test in this
    file, so even a bug that slipped a real network call in would fail
    loudly here, in addition to the direct call-recording assertions
    below."""

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a real socket was constructed -- this module must never do that")

    monkeypatch.setattr(socket, "socket", _refuse)


def test_the_email_adapter_calls_its_own_stand_in_sender_with_the_right_link() -> None:
    calls: list[tuple[str, str, str]] = []

    def stand_in_send_email(to: str, subject: str, body: str) -> None:
        calls.append((to, subject, body))

    policy = ApprovalNotify(channel="email", recipient="approver@example.test")
    approval_notify.notify(
        approval_id=7,
        notify_policy=policy,
        config=CONFIG,
        now=FROZEN_NOW,
        ttl_seconds=3600,
        request_digest="test-digest",
        send_email=stand_in_send_email,
    )

    assert len(calls) == 1
    to, subject, body = calls[0]
    assert to == "approver@example.test"
    assert "7" in subject
    assert "https://onedoor.example/links/" in body
    # Both an approve and a deny link are included.
    assert body.count("https://onedoor.example/links/") == 2


def test_the_webhook_adapter_calls_its_own_stand_in_sender_with_the_right_link() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def stand_in_send_webhook(url: str, payload: dict[str, object]) -> None:
        calls.append((url, payload))

    policy = ApprovalNotify(channel="webhook", recipient="https://ops.example/hook")
    approval_notify.notify(
        approval_id=9,
        notify_policy=policy,
        config=CONFIG,
        now=FROZEN_NOW,
        ttl_seconds=3600,
        request_digest="test-digest",
        send_webhook=stand_in_send_webhook,
    )

    assert len(calls) == 1
    url, payload = calls[0]
    assert url == "https://ops.example/hook"
    assert payload["approval_id"] == 9
    assert str(payload["approve_url"]).startswith("https://onedoor.example/links/")
    assert str(payload["deny_url"]).startswith("https://onedoor.example/links/")
    assert payload["approve_url"] != payload["deny_url"]


def test_a_send_failure_leaves_the_underlying_approval_reachable_by_other_means() -> None:
    """The notify step is a side effect, never gating the approval itself:
    a raising sender must not propagate, and the approval it was about
    must remain approvable through the ordinary API afterward (proven at
    the service layer in test_approval_link_routes.py; here, proven that
    `notify` itself swallows the failure rather than raising)."""

    def failing_sender(to: str, subject: str, body: str) -> None:
        raise ConnectionError("stand-in failure")

    policy = ApprovalNotify(channel="email", recipient="approver@example.test")
    result = approval_notify.notify(
        approval_id=1,
        notify_policy=policy,
        config=CONFIG,
        now=FROZEN_NOW,
        ttl_seconds=3600,
        request_digest="test-digest",
        send_email=failing_sender,
    )
    assert result is not None  # did not raise


def test_a_failing_senders_message_has_its_own_token_redacted_by_shape(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Narrower case: a sender's own exception message
    can echo back the URL it failed to call -- the link's own token
    included. The logged line must not carry it, caught by the token's
    SHAPE (a long base64url run), not by truncating the whole message to
    some length, which only kept it out by coincidence."""
    captured: dict[str, str] = {}

    def failing_sender(to: str, subject: str, body: str) -> None:
        for line in body.splitlines():
            if line.startswith("Approve: "):
                captured["approve_url"] = line.removeprefix("Approve: ")
        raise ConnectionError(f"POST {captured['approve_url']} refused by upstream")

    policy = ApprovalNotify(channel="email", recipient="approver@example.test")
    with caplog.at_level("WARNING", logger="onedoor.integrations.approval_notify"):
        approval_notify.notify(
            approval_id=1,
            notify_policy=policy,
            config=CONFIG,
            now=FROZEN_NOW,
            ttl_seconds=3600,
            request_digest="test-digest",
            send_email=failing_sender,
        )
    logged = "\n".join(caplog.messages)
    token = captured["approve_url"].rsplit("/", 1)[-1]
    assert token not in logged
    assert "<redacted>" in logged


def test_a_channel_with_no_matching_sender_configured_does_not_raise() -> None:
    """A policy declares `channel: email` but the deployment wired only
    `send_webhook` (or neither) -- a deployment-config gap, not a reason
    to crash the propose path that triggered the notify."""
    policy = ApprovalNotify(channel="email", recipient="approver@example.test")
    approval_notify.notify(
        approval_id=2,
        notify_policy=policy,
        config=CONFIG,
        now=FROZEN_NOW,
        ttl_seconds=3600,
        request_digest="test-digest",
    )
