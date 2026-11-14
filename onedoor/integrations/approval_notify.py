"""Signed approval links: the notify adapter (onedoor 0.11).

Given an approval id and a policy-configured recipient, builds the
approve link and the deny link (two separate tokens, signed under the
currently-configured signing key id) and calls a deployment-supplied
``send_email(to, subject, body)`` or ``send_webhook(url, payload)`` -- the
same "deployment supplies the mechanism" shape as `mandate_resolver` and
`escalation_resolver`. Neither sender has a default implementation here:
this module never constructs a socket of its own, only calls whatever
callable it was given.

A send failure never touches the underlying approval's own state -- the
Tier-3 hold stands exactly as it would have if no link had ever been
sent; a failed notification is logged, never mistaken for a denied or
approved action.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from onedoor.guardrail import approval_link
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.guardrail.models import ApprovalNotify

log = logging.getLogger("onedoor.integrations.approval_notify")

_TOKEN_SHAPE_RE = re.compile(r"[A-Za-z0-9_-]{20,}")
"""A link token is a long base64url run,
whatever surrounds it (the configured base URL, a sender's own retry
message). Matched and redacted by that SHAPE -- not by truncating the
whole message to some length, which only keeps a token out by the
coincidence of it, and a sender error even one character under the old
200-character cutoff, with the token placed early, would still have put
the whole thing in the log."""


def _redact_token_shaped_text(text: str) -> str:
    return _TOKEN_SHAPE_RE.sub("<redacted>", text)


class EmailSender(Protocol):
    def __call__(self, to: str, subject: str, body: str) -> None: ...


class WebhookSender(Protocol):
    def __call__(self, url: str, payload: dict[str, object]) -> None: ...


def _link_url(config: NotifyConfig, token: str) -> str:
    return f"{config.approval_link_base_url}/{token}"


@dataclass(frozen=True)
class NotifyResult:
    approve_url: str
    deny_url: str
    sent: bool
    """`True` only once a configured sender for the
    policy's own channel actually ran without raising -- the design
    note's own receipt wording promises a link "built and dispatched",
    not merely built. `False` for a missing sender or a sender that
    raised; the links are still valid and returned either way, only this
    flag says whether dispatch itself happened."""


def notify(
    *,
    approval_id: int,
    notify_policy: ApprovalNotify,
    config: NotifyConfig,
    now: datetime,
    ttl_seconds: int,
    request_digest: str,
    send_email: EmailSender | None = None,
    send_webhook: WebhookSender | None = None,
) -> NotifyResult | None:
    """Build the approve and deny links for one approval and dispatch them
    via `notify_policy.channel`. Returns a `NotifyResult` on success --
    its `approve_url`/`deny_url` are valid whether or not the send itself
    succeeded (presentable through the by-link routes directly, or read
    back by an operator), and its `sent` flag says
    whether dispatch actually happened. Returns `None`
    if a link could not even be ISSUED -- there is then nothing valid to
    return at all.

    `request_digest` is the approval's own
    `approvals.resume_digest(action_type, params)` -- required, not
    computed here, since this module has no database access of its own
    and the caller already has the request in hand.

    Never raises: a missing sender for the configured channel, a sender
    that itself raises, or `issue()` itself raising
    (`NotifyConfig` already validates its signing key id at construction,
    but issuing stays inside this function's own guard regardless, so
    nothing this module does can crash the propose path that triggered
    this call AFTER its approval row was already written) is logged and
    swallowed.
    """
    try:
        approve_token = approval_link.issue(
            approval_id=approval_id,
            action="approve",
            recipient=notify_policy.recipient,
            now=now,
            ttl_seconds=ttl_seconds,
            signing_keys=config.approval_link_signing_keys,
            key_id=config.approval_link_signing_key_id,
            issuer=config.approval_link_issuer,
            request_digest=request_digest,
        )
        deny_token = approval_link.issue(
            approval_id=approval_id,
            action="deny",
            recipient=notify_policy.recipient,
            now=now,
            ttl_seconds=ttl_seconds,
            signing_keys=config.approval_link_signing_keys,
            key_id=config.approval_link_signing_key_id,
            issuer=config.approval_link_issuer,
            request_digest=request_digest,
        )
    except Exception as exc:
        log.warning(
            "approval #%s: failed to issue a link: %s",
            approval_id,
            _redact_token_shaped_text(str(exc))[:200],
        )
        return None
    approve_url = _link_url(config, approve_token)
    deny_url = _link_url(config, deny_token)

    sent = False
    try:
        if notify_policy.channel == "email":
            if send_email is None:
                log.warning(
                    "approval #%s: channel is email, but no send_email configured", approval_id
                )
            else:
                send_email(
                    notify_policy.recipient,
                    f"onedoor approval #{approval_id}",
                    f"Approve: {approve_url}\nDeny: {deny_url}",
                )
                sent = True
        elif notify_policy.channel == "webhook":
            if send_webhook is None:
                log.warning(
                    "approval #%s: channel is webhook, but no send_webhook configured", approval_id
                )
            else:
                send_webhook(
                    notify_policy.recipient,
                    {
                        "approval_id": approval_id,
                        "approve_url": approve_url,
                        "deny_url": deny_url,
                    },
                )
                sent = True
    except Exception as exc:  # a send failure must never touch the approval's own state
        sent = False
        log.warning(
            "approval #%s notify failed: %s",
            approval_id,
            _redact_token_shaped_text(str(exc))[:200],
        )

    return NotifyResult(approve_url=approve_url, deny_url=deny_url, sent=sent)
