"""Time helpers.

A single, injectable source of 'now'. Tests pass an explicit ``now`` into the
guardrail engine; production uses :func:`now_utc`. Keeping this in one place means
the engine never calls ``datetime.now()`` directly, which keeps it testable.
"""

from __future__ import annotations

from datetime import UTC, datetime


def now_utc() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    """Serialize a datetime to ISO-8601 for storage."""
    return dt.astimezone(UTC).isoformat()


def from_iso(value: str) -> datetime:
    """Parse a stored ISO-8601 timestamp back to an aware datetime."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt
