"""Cap accounting: daily rate, and €/day + €/month for Tier 2.

``check_and_reserve`` reads and increments counters *within the caller's
transaction* so two concurrent requests cannot double-spend a cap — the
IMMEDIATE transaction serializes them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from onedoor.guardrail.models import ActionRequest, CheckId, Policy


@dataclass(frozen=True)
class CapResult:
    exceeded: bool
    reason: CheckId | None = None
    detail: str = ""


def _day_key(now: datetime, tz: ZoneInfo) -> str:
    return now.astimezone(tz).strftime("%Y-%m-%d")


def _month_key(now: datetime, tz: ZoneInfo) -> str:
    return now.astimezone(tz).strftime("%Y-%m")


def _read(conn: sqlite3.Connection, action_type: str, kind: str, key: str) -> tuple[int, Decimal]:
    row = conn.execute(
        "SELECT count, eur_total FROM cap_counters "
        "WHERE action_type=? AND window_kind=? AND window_key=?",
        (action_type, kind, key),
    ).fetchone()
    if row is None:
        return 0, Decimal(0)
    return int(row["count"]), Decimal(row["eur_total"])


def _bump(
    conn: sqlite3.Connection,
    action_type: str,
    kind: str,
    key: str,
    *,
    count_delta: int = 0,
    eur_delta: Decimal = Decimal(0),
) -> None:
    count, total = _read(conn, action_type, kind, key)
    conn.execute(
        "INSERT INTO cap_counters (action_type, window_kind, window_key, count, eur_total) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(action_type, window_kind, window_key) "
        "DO UPDATE SET count=excluded.count, eur_total=excluded.eur_total",
        (action_type, kind, key, count + count_delta, str(total + eur_delta)),
    )


def _check_one(
    conn: sqlite3.Connection,
    key: str,
    caps: "Caps",
    request: ActionRequest,
    day: str,
    month: str,
    label: str,
) -> CapResult:
    if caps.daily_rate is not None:
        count, _ = _read(conn, key, "rate", day)
        if count + 1 > caps.daily_rate:
            return CapResult(
                True, CheckId.CAP_DAILY_RATE, f"daily rate {caps.daily_rate} reached{label}"
            )
    if caps.eur_day is not None:
        _, total = _read(conn, key, "eur_day", day)
        if total + request.cost_eur > caps.eur_day:
            return CapResult(True, CheckId.CAP_EUR_DAY, f"€/day cap {caps.eur_day} reached{label}")
    if caps.eur_month is not None:
        _, total = _read(conn, key, "eur_month", month)
        if total + request.cost_eur > caps.eur_month:
            return CapResult(
                True, CheckId.CAP_EUR_MONTH, f"€/month cap {caps.eur_month} reached{label}"
            )
    return CapResult(False)


def _reserve_one(
    conn: sqlite3.Connection, key: str, caps: "Caps", request: ActionRequest, day: str, month: str
) -> None:
    if caps.daily_rate is not None:
        _bump(conn, key, "rate", day, count_delta=1)
    if caps.eur_day is not None:
        _bump(conn, key, "eur_day", day, eur_delta=request.cost_eur)
    if caps.eur_month is not None:
        _bump(conn, key, "eur_month", month, eur_delta=request.cost_eur)


def check_and_reserve(
    conn: sqlite3.Connection,
    policy: Policy,
    request: ActionRequest,
    now: datetime,
    tz: ZoneInfo,
    effect_caps: list[tuple[str, "Caps"]] | None = None,
) -> CapResult:
    """Check the action's caps AND every effect-level cap; reserve all or none.

    Effect counters share the cap_counters table under the key
    ``effect:<name>`` — so every action carrying the label draws from the same
    budget, atomically, inside the caller's IMMEDIATE transaction. Checks run
    over all sources before any reservation, so a failure reserves nothing.
    """
    day = _day_key(now, tz)
    month = _month_key(now, tz)
    sources: list[tuple[str, Caps, str]] = [(policy.action_type, policy.caps, "")]
    for name, ecaps in effect_caps or []:
        sources.append((f"effect:{name}", ecaps, f" (effect {name})"))

    for key, caps, label in sources:  # check everything first
        result = _check_one(conn, key, caps, request, day, month, label)
        if result.exceeded:
            return result
    for key, caps, _ in sources:  # then reserve everything
        _reserve_one(conn, key, caps, request, day, month)
    return CapResult(False)
