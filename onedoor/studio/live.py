"""V4 / S5 — the live room: budgets, reservations, approvals, and the kill switch.

What the engine's state is *right now*, read and never written.

## The kill switch is rendered read-only, and this is the escalation R055 V4 asked for

R055 V4: *"Engage/release only through an admin API that already exists; if none does,
render read-only and escalate."* R059 §5 adds that a half-existing API is still the
read-only case.

**An admin API exists — and it is not one the Studio may use.** `POST /v1/killswitch`
lives on `onedoor.service`, the PDP. There are two ways the Studio could reach the
switch and both break something load-bearing:

1. **`killswitch.set_engaged(state.enforcer, …)` directly.** R047 §2 is that *the
   enforcer's database contains no row the Studio can edit* — the ratification ceremony
   is the single exception, and it is sealed on arrival. A second write path would make
   that sentence false, and it is the sentence the whole two-process design rests on.
2. **Calling the service over HTTP.** That needs the PDP's admin credential inside the
   Studio, which is precisely what R047 §1 separates the processes to prevent — *one
   leaked credential both answers decisions and rewrites the rules those decisions are
   made under*. It would also make a page that promises *nothing leaves this machine*
   open a socket.

So the state is shown and the control is not offered. **A control that renders as
operable and is not would be the right-typed lie as a button** (R059 §5).

## What the switch does not stop, said on the page

The engine's own note: the switch *"does not stop policy-making… nothing ratified can
move while the switch holds, so a mid-incident ratification cannot cause an effect."*
An operator who reads "ENGAGED" and assumes ratification is blocked has the wrong model
of their own incident, so the screen says it.

## Consumed, reserved, free — and why the arithmetic is not the obvious one

**A reservation is already written into `cap_counters`.** `caps._reserve_all` bumps the
counter at reserve time, so the counter is *consumed plus reserved*, not consumed.
Rendering the counter as "consumed" would double-count every open reservation as spend
— a budget bar that reads as money gone when it is money held. So:

    reserved = the deltas of reservations still `held`
    consumed = counter - reserved
    free     = limit - counter

which is why `reserved` is read from `cap_reservations` and subtracted, rather than
added to anything.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from onedoor.guardrail import killswitch, policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Policy
from onedoor.store.clock import now_utc

RANK = (
    "The kill switch outranks everything, including granted approvals: the engine reads "
    "it before any policy lookup, and while it holds, every acting tier is clamped to "
    "propose-only."
)
"""R055 V4: *"its rank stated plainly"*. Checked against `decision.py`, where the switch
is step 1 and the clamp is unconditional — not inferred from the name."""

DOES_NOT_STOP = (
    "It does not stop policy-making. Nothing ratified can move while the switch holds, "
    "so a rule changed now cannot cause an effect — and the release path reports any "
    "version change that happened while the door was shut."
)
"""The counterintuitive half, from `killswitch`'s own docstring. An operator who assumes
ratification is blocked has the wrong model of their own incident."""

NO_CONTROL = (
    "This Studio cannot engage or release the switch. The control lives on the decision "
    "service, behind its own admin credential, and reaching it from here would need "
    "either a second write path into the enforcer's database or the PDP's credential "
    "inside a policy editor — the two things the split between these processes exists "
    "to prevent. The state is shown; the switch is thrown where it is answerable."
)
"""Read-only, with the reason. An absent control that is silently absent reads as a
control that is missing by oversight."""

WINDOWS = {
    "rate": ("actions", "day"),
    "eur_day": ("EUR", "day"),
    "eur_month": ("EUR", "month"),
}
"""`window_kind` -> (unit, window). Read from `caps._reserve_all`, which writes them."""


def _decimal(value: object) -> str:
    text = format(Decimal(str(value or 0)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class Bar:
    """One cap window: what it allows, what is spent, what is held, what is left."""

    action_type: str
    kind: str
    window_key: str
    limit: Decimal | None
    counter: Decimal
    reserved: Decimal

    @property
    def unit(self) -> str:
        return WINDOWS.get(self.kind, ("", ""))[0]

    @property
    def window(self) -> str:
        return WINDOWS.get(self.kind, ("", ""))[1]

    @property
    def consumed(self) -> Decimal:
        """Spent, with held-but-unsettled money taken back out. Never below zero.

        A reservation released between the two reads would otherwise show as negative
        spend; the clamp says *this is a view of a moving store*, not that the store is
        wrong.
        """
        return max(Decimal(0), self.counter - self.reserved)

    @property
    def free(self) -> Decimal | None:
        return None if self.limit is None else max(Decimal(0), self.limit - self.counter)

    @property
    def unbounded(self) -> bool:
        """True when the counter has no cap behind it.

        A window with no limit is not a full bar or an empty one — it is **not a bar**,
        and drawing it as either would state a proportion nobody declared.
        """
        return self.limit is None

    def pct(self, part: Decimal) -> float:
        if self.limit is None or self.limit == 0:
            return 0.0
        return min(100.0, float(part / self.limit * 100))

    def texts(self) -> tuple[str, str, str, str]:
        return (
            _decimal(self.consumed),
            _decimal(self.reserved),
            "unbounded" if self.free is None else _decimal(self.free),
            "none declared" if self.limit is None else _decimal(self.limit),
        )


@dataclass(frozen=True)
class Reservation:
    intent_audit_id: int
    request_id: str
    deadline: str
    created: str
    deltas: tuple[tuple[str, str, str], ...]
    """`(action_type, window_kind, amount)` — what this reservation is holding."""

    def age_seconds(self, now: datetime) -> int | None:
        try:
            started = datetime.fromisoformat(self.created.replace("Z", "+00:00"))
        except ValueError:
            return None
        return int((now - started).total_seconds())

    def overdue(self, now: datetime) -> bool | None:
        """Past its deadline and still held — reclamation has not run yet.

        `None` when the deadline cannot be parsed: unparseable is not "fine", and a
        three-outcome screen must not answer a question it could not evaluate.
        """
        try:
            deadline = datetime.fromisoformat(self.deadline.replace("Z", "+00:00"))
        except ValueError:
            return None
        return now > deadline


@dataclass(frozen=True)
class Approval:
    approval_id: int
    action_type: str
    state: str
    created_at: str
    expires_at: str | None
    decided_at: str | None
    decided_by_session: str | None


@dataclass(frozen=True)
class LiveState:
    engaged: bool
    engaged_since: str | None
    engaged_origin: str | None
    version_at_engagement: str | None
    bars: tuple[Bar, ...]
    reservations: tuple[Reservation, ...]
    approvals: tuple[Approval, ...]
    now: datetime


def _limits(policies: list[Policy]) -> dict[tuple[str, str], Decimal]:
    out: dict[tuple[str, str], Decimal] = {}
    for policy in policies:
        caps = policy.caps
        if caps is None:
            continue
        if caps.daily_rate is not None:
            out[(policy.action_type, "rate")] = Decimal(str(caps.daily_rate))
        if caps.eur_day is not None:
            out[(policy.action_type, "eur_day")] = Decimal(str(caps.eur_day))
        if caps.eur_month is not None:
            out[(policy.action_type, "eur_month")] = Decimal(str(caps.eur_month))
    return out


def _held(
    ledger: sqlite3.Connection,
) -> tuple[tuple[Reservation, ...], dict[tuple[str, str], Decimal]]:
    """Open reservations, and what they are holding per counter."""
    rows = ledger.execute(
        "SELECT intent_audit_id, request_id, deadline_utc, created_utc, deltas_json "
        "FROM cap_reservations WHERE status='held' ORDER BY intent_audit_id DESC"
    ).fetchall()
    reservations: list[Reservation] = []
    holding: dict[tuple[str, str], Decimal] = {}
    for row in rows:
        deltas = []
        for entry in json.loads(row["deltas_json"] or "[]"):
            key, kind, _window_key, count_delta, eur_delta = entry
            amount = Decimal(str(count_delta)) if kind == "rate" else Decimal(str(eur_delta))
            holding[(key, kind)] = holding.get((key, kind), Decimal(0)) + amount
            deltas.append((key, kind, _decimal(amount)))
        reservations.append(
            Reservation(
                intent_audit_id=int(row["intent_audit_id"]),
                request_id=str(row["request_id"] or ""),
                deadline=str(row["deadline_utc"] or ""),
                created=str(row["created_utc"] or ""),
                deltas=tuple(deltas),
            )
        )
    return tuple(reservations), holding


def build(
    ledger: sqlite3.Connection, config: EngineConfig, now: datetime | None = None
) -> LiveState:
    """The live room. Reads only; writes nothing anywhere."""
    now = now or now_utc()
    episode = killswitch.open_episode(ledger)

    limits = _limits(_policies_in_force(ledger))
    reservations, holding = _held(ledger)

    bars = []
    counters = ledger.execute(
        "SELECT action_type, window_kind, window_key, count, eur_total FROM cap_counters "
        "ORDER BY action_type, window_kind, window_key"
    ).fetchall()
    seen = set()
    for row in counters:
        action, kind = str(row["action_type"]), str(row["window_kind"])
        counter = (
            Decimal(str(row["count"])) if kind == "rate" else Decimal(str(row["eur_total"] or 0))
        )
        seen.add((action, kind))
        bars.append(
            Bar(
                action_type=action,
                kind=kind,
                window_key=str(row["window_key"]),
                limit=limits.get((action, kind)),
                counter=counter,
                reserved=holding.get((action, kind), Decimal(0)),
            )
        )
    # A declared cap with no counter yet is a real window at zero, not an absent one.
    # Omitting it would make a fresh deployment look as though it had no budgets.
    for (action, kind), limit in sorted(limits.items()):
        if (action, kind) not in seen:
            bars.append(
                Bar(
                    action_type=action,
                    kind=kind,
                    window_key="",
                    limit=limit,
                    counter=Decimal(0),
                    reserved=Decimal(0),
                )
            )

    approvals = tuple(
        Approval(
            approval_id=int(r["id"]),
            action_type=str(r["action_type"] or ""),
            state=str(r["state"] or ""),
            created_at=str(r["created_at"] or ""),
            expires_at=r["expires_at"],
            decided_at=r["decided_at"],
            decided_by_session=r["decided_by_session"],
        )
        for r in ledger.execute("SELECT * FROM approvals ORDER BY id DESC LIMIT 50").fetchall()
    )

    return LiveState(
        engaged=killswitch.is_engaged(ledger),
        engaged_since=None if episode is None else str(episode["engaged_at"]),
        engaged_origin=None if episode is None else str(episode["origin"]),
        version_at_engagement=(None if episode is None else episode["version_hash_at_engagement"]),
        bars=tuple(bars),
        reservations=reservations,
        approvals=approvals,
        now=now,
    )


def _policies_in_force(ledger: sqlite3.Connection) -> list[Policy]:
    """The policy set behind the pinned version — R058 §1's law, applied here too.

    The caps a bar is measured against must come from the same snapshot the header's
    digest names, or the page draws a limit the engine is not enforcing.
    """
    from onedoor.studio import ratify

    return ratify._policies_at(ledger, policy_loader.current_version(ledger))
