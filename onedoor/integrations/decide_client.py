"""An HTTP client for the decision service, authenticated with a decide-only key.

onedoor/service/app.py already draws the line this client needs: a key in
``ONEDOOR_DECIDE_KEYS`` may call ``POST /v1/decide`` and ``POST /v1/report``, and
nothing else, so a process holding one holds no database connection and no approver
credential. This client is the thing that was missing, not a new server mechanism.

Idempotency is already a server property, not something this client adds: a
repeated ``request_id`` against one service process returns the already-recorded
result outright (``decide_and_reserve``'s prior-result check, under the same
process-wide lock ``/v1/decide`` holds for the whole call), so it is never a second
reservation. What this client contributes is the discipline of actually reusing one
``request_id`` across every retry of one logical call, instead of minting a fresh
one per attempt -- that is the whole of "a client-generated idempotency key, the
same on every retry."

A call that never gets an answer -- every retry inside the deadline dropped or
timed out -- raises :class:`NotAttempted` rather than returning anything shaped like
a decision. There is deliberately no result object a caller could mistake for one:
the only way to get a decision back from :meth:`DecideKeyClient.decide` is for the
service to have actually answered.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


class NotAttempted(Exception):
    """A decide call's retries were exhausted, or its deadline passed, with no
    answer from the service. The action was NOT taken, and nothing about it is
    assumed granted -- the caller holds exactly the information a call that never
    reached the service would leave it with, because for all this client can tell,
    it may not have.
    """

    def __init__(self, reason: str, *, request_id: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.request_id = request_id


@dataclass
class DecideKeyClient:
    """Retries under one idempotency key, inside one deadline, with conservative
    defaults -- all three settable, since a conservative default is a starting
    point, not every deployment's right answer.

    `client` is a configured `httpx.Client` (base_url set, the decide key's
    `Authorization: Bearer` header already attached) -- constructing one is
    :meth:`connect`'s job, not this dataclass's, so a test can hand in a client
    wired to an in-process ASGI app or a transport that drops every call, without
    this class knowing the difference.
    """

    client: httpx.Client
    max_retries: int = 3
    backoff_base_seconds: float = 0.5
    backoff_cap_seconds: float = 4.0
    total_deadline_seconds: float = 10.0
    _sleep: Any = field(default=time.sleep, repr=False, compare=False)

    @classmethod
    def connect(
        cls,
        base_url: str,
        decide_key: str,
        **kwargs: Any,
    ) -> DecideKeyClient:
        """The production constructor: a real `httpx.Client` against a real service."""
        client = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {decide_key}"})
        return cls(client=client, **kwargs)

    def close(self) -> None:
        self.client.close()

    def decide(self, body: dict[str, Any], *, request_id: str | None = None) -> dict[str, Any]:
        """POST /v1/decide. `request_id`, generated here if absent, is the one
        value every retry of this call sends identically -- the idempotency key.
        """
        rid = request_id or str(uuid.uuid4())
        payload = {**body, "request_id": rid}
        return self._post_with_retry("/v1/decide", payload, request_id=rid)

    def report(self, body: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        """POST /v1/report. Takes the same `request_id` as a label for
        :class:`NotAttempted`, not as a wire idempotency key -- `/v1/report` is
        already bound to one `intent_audit_id`, once, by the decide_principal check.
        """
        return self._post_with_retry("/v1/report", body, request_id=request_id)

    def _post_with_retry(
        self, path: str, payload: dict[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self.total_deadline_seconds
        attempt = 0
        while attempt < self.max_retries:
            attempt += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                response = self.client.post(path, json=payload, timeout=remaining)
            except httpx.TransportError:
                # No answer at all -- dropped, refused, or timed out. The one case
                # this client retries; anything the service actually answered
                # (including a 4xx/5xx) is a response, not a drop, and is not
                # retried here.
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                backoff = min(
                    self.backoff_base_seconds * (2 ** (attempt - 1)), self.backoff_cap_seconds
                )
                self._sleep(min(backoff, remaining))
                continue
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        raise NotAttempted("the decision was not received", request_id=request_id)
