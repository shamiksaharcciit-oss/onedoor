"""`issue()` raising must not crash the propose path
that triggered `notify()`, after its approval row was already written.
`NotifyConfig` already validates its signing key id at construction,
but issuing stays inside this module's own guard regardless --
nothing it does can turn into an uncaught exception.
"""

from __future__ import annotations

from unittest.mock import patch

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


def test_issue_raising_is_swallowed_and_returns_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = ApprovalNotify(channel="email", recipient="approver@example.test")
    with patch(
        "onedoor.integrations.approval_notify.approval_link.issue",
        side_effect=RuntimeError("stand-in issue failure"),
    ):
        with caplog.at_level("WARNING", logger="onedoor.integrations.approval_notify"):
            result = approval_notify.notify(
                approval_id=1,
                notify_policy=policy,
                config=CONFIG,
                now=FROZEN_NOW,
                ttl_seconds=3600,
                request_digest="test-digest",
            )
    assert result is None  # did not raise, and nothing valid to return
    assert any("failed to issue" in m for m in caplog.messages)
