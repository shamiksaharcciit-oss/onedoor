"""Reservation reclamation: a permit that is never reported must not hold its
budget forever (AADP section 6). The reclaimer releases the reserved budget
once the deadline passes, as an audited event, and voids the permit.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from sqlite3 import Connection
from zoneinfo import ZoneInfo

from onedoor.guardrail.decision import (
    PermittedIntent,
    decide_and_reserve,
    reclaim_expired_reservations,
    report_result,
)
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Outcome
from tests.conftest import make_request

TZ = ZoneInfo("Europe/Amsterdam")


def _config(ttl: int = 60) -> EngineConfig:
    return EngineConfig(
        approval_ttl_seconds=3600,
        connector_timeout_seconds=1.0,
        tz=TZ,
        reservation_ttl_seconds=ttl,
    )


def _reserved_eur_day(conn: Connection) -> Decimal:
    row = conn.execute(
        "SELECT eur_total FROM cap_counters "
        "WHERE action_type='demo.tier2' AND window_kind='eur_day'"
    ).fetchone()
    return Decimal(row["eur_total"]) if row else Decimal(0)


def _expiry_rows(conn: Connection) -> list:
    return list(
        conn.execute("SELECT * FROM actions_audit WHERE kind='reservation_expired' ORDER BY id")
    )


def test_unreported_permit_holds_budget_until_reclaimed(conn: Connection) -> None:
    cfg = _config(ttl=60)
    now = make_request("demo.tier2").created_at

    first = decide_and_reserve(
        make_request("demo.tier2", cost_eur=Decimal("6")), conn=conn, config=cfg, now=now
    )
    assert isinstance(first, PermittedIntent)  # 6 reserved, never reported
    assert _reserved_eur_day(conn) == Decimal("6")

    # A second 6 would breach the 10/day cap while the first reservation stands.
    blocked = decide_and_reserve(
        make_request("demo.tier2", cost_eur=Decimal("6")), conn=conn, config=cfg, now=now
    )
    assert not isinstance(blocked, PermittedIntent)
    assert blocked.decision.reason_code.value == "cap_value"


def test_reclaim_frees_budget_and_audits_the_release(conn: Connection) -> None:
    cfg = _config(ttl=60)
    now = make_request("demo.tier2").created_at

    intent = decide_and_reserve(
        make_request("demo.tier2", cost_eur=Decimal("6")), conn=conn, config=cfg, now=now
    )
    assert isinstance(intent, PermittedIntent)

    later = now + timedelta(seconds=61)
    # A fresh decide past the deadline reclaims the abandoned 6 first, so the
    # new 6 now fits under the 10/day cap.
    after = decide_and_reserve(
        make_request("demo.tier2", cost_eur=Decimal("6")), conn=conn, config=cfg, now=later
    )
    assert isinstance(after, PermittedIntent), "reclaim should have freed the abandoned reservation"

    rows = _expiry_rows(conn)
    assert len(rows) == 1
    assert rows[0]["reason_code"] == "expired"
    assert rows[0]["parent_id"] == intent.intent_audit_id
    # net reserved is the new 6 (old 6 released, new 6 held)
    assert _reserved_eur_day(conn) == Decimal("6")

    res = conn.execute(
        "SELECT status FROM cap_reservations WHERE intent_audit_id=?",
        (intent.intent_audit_id,),
    ).fetchone()
    assert res["status"] == "expired"


def test_reported_permit_is_never_reclaimed(conn: Connection) -> None:
    cfg = _config(ttl=60)
    now = make_request("demo.tier2").created_at

    intent = decide_and_reserve(
        make_request("demo.tier2", cost_eur=Decimal("6")), conn=conn, config=cfg, now=now
    )
    assert isinstance(intent, PermittedIntent)
    report_result(
        intent, conn=conn, config=cfg, outcome=Outcome.SUCCESS, payload=None, error=None, now=now
    )

    n = reclaim_expired_reservations(conn, cfg, now + timedelta(seconds=61))
    assert n == 0, "a reported permit's reservation must not be reclaimed"
    assert _expiry_rows(conn) == []
    assert _reserved_eur_day(conn) == Decimal("6")  # the spend stands


def test_reclaim_is_a_noop_before_the_deadline(conn: Connection) -> None:
    cfg = _config(ttl=600)
    now = make_request("demo.tier2").created_at
    decide_and_reserve(
        make_request("demo.tier2", cost_eur=Decimal("6")), conn=conn, config=cfg, now=now
    )
    assert reclaim_expired_reservations(conn, cfg, now + timedelta(seconds=60)) == 0
    assert _reserved_eur_day(conn) == Decimal("6")


def test_double_reclaim_is_harmless(conn: Connection) -> None:
    cfg = _config(ttl=60)
    now = make_request("demo.tier2").created_at
    decide_and_reserve(
        make_request("demo.tier2", cost_eur=Decimal("6")), conn=conn, config=cfg, now=now
    )
    later = now + timedelta(seconds=61)
    assert reclaim_expired_reservations(conn, cfg, later) == 1
    # second sweep finds nothing still held; counter is not driven negative
    assert reclaim_expired_reservations(conn, cfg, later) == 0
    assert _reserved_eur_day(conn) == Decimal("0")
    assert len(_expiry_rows(conn)) == 1


def test_ttl_zero_disables_reclamation(conn: Connection) -> None:
    cfg = _config(ttl=0)
    now = make_request("demo.tier2").created_at
    decide_and_reserve(
        make_request("demo.tier2", cost_eur=Decimal("6")), conn=conn, config=cfg, now=now
    )
    # no reservation row was written, so nothing is ever reclaimed
    assert reclaim_expired_reservations(conn, cfg, now + timedelta(days=1)) == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM cap_reservations").fetchone()["n"] == 0
