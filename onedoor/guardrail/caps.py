"""Cap accounting: daily rate, and €/day + €/month for Tier 2.

``check_and_reserve`` reads and increments counters *within the caller's
transaction* so two concurrent requests cannot double-spend a cap — the
IMMEDIATE transaction serializes them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from onedoor._vendor.canonical import canon_datetime, canon_decimal
from onedoor.guardrail.models import ActionRequest, Budget, Caps, CheckId, Policy


@dataclass(frozen=True)
class CapResult:
    exceeded: bool
    reason: CheckId | None = None
    detail: str = ""
    # On a successful reservation, the exact counter deltas applied, so the
    # reservation can be reversed later if the permit is never reported. Each
    # entry is (counter_key, window_kind, window_key, count_delta, eur_delta).
    deltas: tuple[tuple[str, str, str, int, str], ...] = ()
    # ND-003: machine-readable budget state, set only on a cap denial. The free-text
    # `detail` above is what this replaces -- prose cannot say which window broke in
    # a form an evidence reader can act on.
    budget: Budget | None = None


def _day_key(now: datetime, tz: ZoneInfo) -> str:
    return now.astimezone(tz).strftime("%Y-%m-%d")


def _month_key(now: datetime, tz: ZoneInfo) -> str:
    return now.astimezone(tz).strftime("%Y-%m")


def _day_resets_at(now: datetime, tz: ZoneInfo) -> str:
    """The instant the day window rolls, in the policy's timezone, rendered UTC.

    Computed from the SAME clock and timezone that produced the window key, so the
    budget object can never name a reset instant that disagrees with the counter it
    describes -- two answers to one question is a disagreement waiting for its first
    bug (X-14).
    """
    local = now.astimezone(tz)
    start_of_next = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return canon_datetime(start_of_next.astimezone(UTC))


def _month_resets_at(now: datetime, tz: ZoneInfo) -> str:
    local = now.astimezone(tz)
    year, month = (local.year + 1, 1) if local.month == 12 else (local.year, local.month + 1)
    start_of_next = local.replace(
        year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return canon_datetime(start_of_next.astimezone(UTC))


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
        # Decimal belongs here for the same reason it belongs in bounds.py: E10 parses
        # JSON numbers with parse_float=Decimal, so the amount arrives as a Decimal.
        # Omitting it does not fail open -- resolve_cost returning None denies with
        # cost_unknown -- but it denies EVERY euro-capped action, which is the
        # half-landed fix wearing its other face. Found by the end-to-end guard test.
        if isinstance(raw, bool) or not isinstance(raw, int | float | str | Decimal):
            return None
        try:
            value = raw if isinstance(raw, Decimal) else Decimal(str(raw))
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
    now: datetime,
    tz: ZoneInfo,
) -> CapResult:
    if caps.daily_rate is not None:
        count, _ = counters.get((key, "rate", day), (0, Decimal(0)))
        if count + 1 > caps.daily_rate:
            return CapResult(
                True,
                CheckId.CAP_RATE,
                f"daily rate {caps.daily_rate} reached{label}",
                budget=Budget(
                    dimension="rate",
                    unit="calls",  # a token, not a currency: the dimension is not money
                    window="day",
                    limit=canon_decimal(Decimal(caps.daily_rate)),
                    consumed=canon_decimal(Decimal(count)),
                    remaining=canon_decimal(max(Decimal(0), Decimal(caps.daily_rate - count))),
                    window_resets_at=_day_resets_at(now, tz),
                ),
            )
    if caps.eur_day is not None:
        _, total = counters.get((key, "eur_day", day), (0, Decimal(0)))
        if total + cost > caps.eur_day:
            return CapResult(
                True,
                CheckId.CAP_VALUE,
                f"€/day cap {caps.eur_day} reached{label}",
                budget=_value_budget("day", caps.eur_day, total, _day_resets_at(now, tz)),
            )
    if caps.eur_month is not None:
        _, total = counters.get((key, "eur_month", month), (0, Decimal(0)))
        if total + cost > caps.eur_month:
            return CapResult(
                True,
                CheckId.CAP_VALUE,
                f"€/month cap {caps.eur_month} reached{label}",
                budget=_value_budget("month", caps.eur_month, total, _month_resets_at(now, tz)),
            )
    return CapResult(False)


def _value_budget(window: str, limit: Decimal, consumed: Decimal, resets_at: str) -> Budget:
    """A euro-dimension budget. `window` is what `cap_value` no longer says by itself.

    Both euro caps now deny with the same reason code, so this object is the only
    thing that distinguishes a day breach from a month one. That is the granularity
    `0.3.5` carried in the reason code and `aadp/0.2` moved here on purpose.
    """
    return Budget(
        dimension="value",
        unit="EUR",  # currency lives in `unit`, never in a field name
        window=window,
        limit=canon_decimal(limit),
        consumed=canon_decimal(consumed),
        remaining=canon_decimal(max(Decimal(0), limit - consumed)),
        window_resets_at=resets_at,
    )


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
        result = _check_one(counters, key, caps, amount, day, month, label, now, tz)
        if result.exceeded:
            return result
    deltas = _reserve_all(conn, counters, sources, amount, day, month)  # then reserve everything
    return CapResult(False, deltas=deltas)
