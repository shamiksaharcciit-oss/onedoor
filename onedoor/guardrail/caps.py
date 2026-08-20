"""Cap accounting: daily rate, and €/day + €/month for Tier 2.

``check_and_reserve`` reads and increments counters *within the caller's
transaction* so two concurrent requests cannot double-spend a cap — the
IMMEDIATE transaction serializes them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from onedoor.guardrail.models import ActionRequest, Caps, CheckId, Policy


@dataclass(frozen=True)
class CapResult:
    exceeded: bool
    reason: CheckId | None = None
    detail: str = ""
    # On a successful reservation, the exact counter deltas applied, so the
    # reservation can be reversed later if the permit is never reported. Each
    # entry is (counter_key, window_kind, window_key, count_delta, eur_delta).
    deltas: tuple[tuple[str, str, str, int, str], ...] = ()


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


def _read_all(
    conn: sqlite3.Connection, keys: list[str], day: str, month: str
) -> dict[tuple[str, str, str], tuple[int, Decimal]]:
    """Every counter these keys could touch, in ONE statement.

    The previous form issued a SELECT per (key, window) — four round trips for an
    action with one effect label, before any reservation. The check is still
    check-everything-before-reserving-anything; only the number of statements
    changes, and it all still happens inside the caller's IMMEDIATE transaction.
    """
    if not keys:
        return {}
    placeholders = ",".join("?" * len(keys))
    rows = conn.execute(
        f"SELECT action_type, window_kind, window_key, count, eur_total FROM cap_counters "
        f"WHERE action_type IN ({placeholders}) AND window_key IN (?, ?)",
        (*keys, day, month),
    ).fetchall()
    return {
        (r["action_type"], r["window_kind"], r["window_key"]): (
            int(r["count"]),
            Decimal(r["eur_total"]),
        )
        for r in rows
    }


def resolve_cost(policy: Policy, request: ActionRequest) -> Decimal | None:
    """The amount this request will move, or None if it cannot be determined.

    None is not zero. A euro cap evaluated against an assumed zero permits
    everything forever, which is exactly what happened to every integration
    that did not set `cost_eur` by hand. Callers must treat None as a denial.

    Order: the policy's declared parameter wins, because policy is the trusted
    input; otherwise the request's own `cost_eur`, for callers that compute it.
    """
    if policy.cost_param is not None:
        raw = request.params.get(policy.cost_param)
        if isinstance(raw, bool) or not isinstance(raw, int | float | str):
            return None
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None
        if not value.is_finite() or value < 0:
            return None
        return value
    # No declared parameter: fall back to what the caller computed. A caller
    # that never set `cost_eur` is indistinguishable from one that set it to
    # zero, so under a euro cap both must be treated as unknown -- the whole
    # defect was reading "unset" as "free".
    return request.cost_eur if request.cost_eur > 0 else None


def _has_euro_cap(caps: Caps) -> bool:
    return caps.eur_day is not None or caps.eur_month is not None


def _check_one(
    counters: dict[tuple[str, str, str], tuple[int, Decimal]],
    key: str,
    caps: Caps,
    cost: Decimal,
    day: str,
    month: str,
    label: str,
) -> CapResult:
    if caps.daily_rate is not None:
        count, _ = counters.get((key, "rate", day), (0, Decimal(0)))
        if count + 1 > caps.daily_rate:
            return CapResult(
                True, CheckId.CAP_DAILY_RATE, f"daily rate {caps.daily_rate} reached{label}"
            )
    if caps.eur_day is not None:
        _, total = counters.get((key, "eur_day", day), (0, Decimal(0)))
        if total + cost > caps.eur_day:
            return CapResult(True, CheckId.CAP_EUR_DAY, f"€/day cap {caps.eur_day} reached{label}")
    if caps.eur_month is not None:
        _, total = counters.get((key, "eur_month", month), (0, Decimal(0)))
        if total + cost > caps.eur_month:
            return CapResult(
                True, CheckId.CAP_EUR_MONTH, f"€/month cap {caps.eur_month} reached{label}"
            )
    return CapResult(False)


def _reserve_all(
    conn: sqlite3.Connection,
    counters: dict[tuple[str, str, str], tuple[int, Decimal]],
    sources: list[tuple[str, Caps, str]],
    cost: Decimal,
    day: str,
    month: str,
) -> tuple[tuple[str, str, str, int, str], ...]:
    """Write every reservation in one executemany -- all or nothing, one round trip.

    Returns the per-counter *deltas* applied (not the resulting totals), so a
    caller can persist them and reverse the exact reservation later
    (:func:`release`) if the permit is never reported.
    """
    rows: list[tuple[str, str, str, int, str]] = []
    deltas: list[tuple[str, str, str, int, str]] = []
    for key, caps, _ in sources:
        if caps.daily_rate is not None:
            count, total = counters.get((key, "rate", day), (0, Decimal(0)))
            rows.append((key, "rate", day, count + 1, str(total)))
            deltas.append((key, "rate", day, 1, "0"))
        if caps.eur_day is not None:
            count, total = counters.get((key, "eur_day", day), (0, Decimal(0)))
            rows.append((key, "eur_day", day, count, str(total + cost)))
            deltas.append((key, "eur_day", day, 0, str(cost)))
        if caps.eur_month is not None:
            count, total = counters.get((key, "eur_month", month), (0, Decimal(0)))
            rows.append((key, "eur_month", month, count, str(total + cost)))
            deltas.append((key, "eur_month", month, 0, str(cost)))
    if rows:
        conn.executemany(
            "INSERT INTO cap_counters (action_type, window_kind, window_key, count, eur_total) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(action_type, window_kind, window_key) "
            "DO UPDATE SET count=excluded.count, eur_total=excluded.eur_total",
            rows,
        )
    return tuple(deltas)


def release(
    conn: sqlite3.Connection,
    deltas: list[tuple[str, str, str, int, str]] | tuple[tuple[str, str, str, int, str], ...],
) -> None:
    """Subtract a previously-applied reservation back out of the counters.

    The inverse of the reservation written by :func:`_reserve_all`. Counters are
    clamped at zero: a release can never drive a counter negative, so a double
    release (or a release after the window rolled) is harmless rather than
    corrupting. Callers run this inside their own transaction.
    """
    for key, kind, wkey, count_delta, eur_delta in deltas:
        count, total = _read(conn, key, kind, wkey)
        new_count = max(0, count - int(count_delta))
        new_total = total - Decimal(str(eur_delta))
        if new_total < 0:
            new_total = Decimal(0)
        conn.execute(
            "INSERT INTO cap_counters (action_type, window_kind, window_key, count, eur_total) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(action_type, window_kind, window_key) "
            "DO UPDATE SET count=excluded.count, eur_total=excluded.eur_total",
            (key, kind, wkey, new_count, str(new_total)),
        )


def check_and_reserve(
    conn: sqlite3.Connection,
    policy: Policy,
    request: ActionRequest,
    now: datetime,
    tz: ZoneInfo,
    effect_caps: list[tuple[str, Caps]] | None = None,
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

    cost = resolve_cost(policy, request)
    if cost is None and any(_has_euro_cap(caps) for _, caps, _ in sources):
        # A budget we cannot measure against is not a budget. Deny rather than
        # assume zero -- assuming zero is what made every euro cap inert for
        # callers that never set cost_eur.
        where = (
            f"policy declares cost_param '{policy.cost_param}' but the request "
            "carries no usable value for it"
            if policy.cost_param is not None
            else "no cost_param declared and the request carries no cost_eur"
        )
        return CapResult(
            True, CheckId.COST_UNKNOWN, f"euro cap applies but the amount is unknown ({where})"
        )
    amount = cost if cost is not None else Decimal(0)

    counters = _read_all(conn, [k for k, _, _ in sources], day, month)
    for key, caps, label in sources:  # check everything first
        result = _check_one(counters, key, caps, amount, day, month, label)
        if result.exceeded:
            return result
    deltas = _reserve_all(conn, counters, sources, amount, day, month)  # then reserve everything
    return CapResult(False, deltas=deltas)
