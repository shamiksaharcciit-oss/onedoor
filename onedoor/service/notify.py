"""Approval notifications — pluggable, webhook as the reference implementation.

Set ``ONEDOOR_APPROVAL_WEBHOOK`` to a URL and every Tier-3 proposal POSTs a
Slack-compatible payload there:

    {"text": "onedoor approval #12: mcp.send_payment ...", "onedoor": {...}}

No URL configured -> the null notifier (a log line). Failures are swallowed
after a short timeout: a broken webhook must never block or fail a decision —
notification is an obligation of the operator, not of the pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Protocol

log = logging.getLogger("onedoor.notify")


class Notifier(Protocol):
    def proposed(
        self, approval_id: int, action_type: str, params: dict[str, Any], rationale: str
    ) -> None: ...


class NullNotifier:
    def proposed(
        self, approval_id: int, action_type: str, params: dict[str, Any], rationale: str
    ) -> None:
        log.info("approval #%s pending: %s %s", approval_id, action_type, params)


class WebhookNotifier:
    def __init__(self, url: str, timeout: float = 3.0) -> None:
        self.url = url
        self.timeout = timeout

    def proposed(
        self, approval_id: int, action_type: str, params: dict[str, Any], rationale: str
    ) -> None:
        body = {
            "text": (
                f"onedoor approval #{approval_id}: `{action_type}` "
                f"params={json.dumps(params, default=str)[:300]} — {rationale or 'no rationale'}"
            ),
            "onedoor": {
                "approval_id": approval_id,
                "action_type": action_type,
                "params": params,
                "rationale": rationale,
            },
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(body, default=str).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=self.timeout).close()
        except Exception as exc:  # notification must never break a decision
            log.warning("approval webhook failed: %s", str(exc)[:120])


def build_notifier() -> Notifier:
    url = os.environ.get("ONEDOOR_APPROVAL_WEBHOOK", "").strip()
    return WebhookNotifier(url) if url else NullNotifier()
