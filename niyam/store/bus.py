"""Trivial in-process publish/subscribe event bus.

The guardrail engine publishes ``action.*`` lifecycle events here; in M2 the rules
engine will subscribe. It also appends every event to the ``events`` table for a
durable trail. Kept deliberately minimal — synchronous callbacks, no threads.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Callable

from niyam.store.clock import now_utc, to_iso

Subscriber = Callable[[str, dict[str, object]], None]

_subscribers: list[Subscriber] = []


def subscribe(callback: Subscriber) -> None:
    _subscribers.append(callback)


def clear_subscribers() -> None:
    """Test helper — drop all subscribers."""
    _subscribers.clear()


def publish(conn: sqlite3.Connection, topic: str, payload: dict[str, object]) -> None:
    """Persist the event and fan out to subscribers.

    Subscriber exceptions are swallowed so a bad subscriber can never crash the
    action pipeline (fail-soft).
    """
    conn.execute(
        "INSERT INTO events (topic, payload_json, created_at) VALUES (?, ?, ?)",
        (topic, json.dumps(payload, default=str), to_iso(now_utc())),
    )
    for callback in list(_subscribers):
        # fail-soft: a bad subscriber must never crash the action pipeline
        with contextlib.suppress(Exception):
            callback(topic, payload)
