"""The four-value report outcome and its settlement dispositions (ND-039 / W6).

Core asked (R021) that these tests make the §implstatus disclosure sentence
*checkable*. That sentence, locked in R013, says:

    the report path cannot express `not_attempted` or `timeout`; both collapse to
    `failed`, and because the reservation settles before the outcome is examined, a
    conformant `not_attempted` permanently charges budget for an action that never
    occurred. The implementation's next minor release corrects this by releasing the
    reservation, as an audited event, when the report asserts the action was not
    attempted.

Each clause gets a test, named for the clause it discharges, so a reader can check
the draft against the suite rather than against a promise:

    "cannot express not_attempted or timeout"  -> test_all_four_outcomes_are_expressible
    "both collapse to failed"                  -> test_the_four_outcomes_do_not_collapse
    "settles before the outcome is examined"   -> test_settlement_depends_on_the_outcome
    "permanently charges budget"               -> test_not_attempted_does_not_charge_budget
    "releasing the reservation"                -> test_not_attempted_releases_the_reservation
    "as an audited event"                      -> test_the_release_is_audited_not_silent

The disposition itself is R005's, and the invariant behind it is **settle on doubt**:
release requires a positive assertion of non-occurrence, never an absence of
information. A timeout is doubt -- the action may well have happened -- so it settles.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    Outcome,
    Policy,
    Source,
    Tier,
)
from onedoor.store.db import Database

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
CONFIG = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC"))

SETTLES = [Outcome.SUCCESS, Outcome.FAILURE, Outcome.TIMEOUT]
RELEASES = [Outcome.NOT_ATTEMPTED]


@pytest.fixture
def spend(tmp_path: Path) -> Database:
    database = Database(str(tmp_path / "outcome.db"))
    database.init()
    conn = database.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.spend",
            caps=Caps(eur_day=Decimal("100.00")),
            bounds=Bounds(strict_params=False),
        ),
    )
    conn.close()
    return database


def _permit(conn: object, amount: str = "10.00") -> PermittedIntent:
    out = decide_and_reserve(
        ActionRequest(
            request_id=uuid4(),
            action_type="demo.spend",
            params={},
            source=Source.UI,
            rationale="outcome",
            cost_eur=Decimal(amount),
            created_at=NOW,
        ),
        conn=conn,  # type: ignore[arg-type]
        config=CONFIG,
        now=NOW,
    )
    assert isinstance(out, PermittedIntent)
    return out


def _spent(conn: object) -> Decimal:
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT eur_total FROM cap_counters WHERE window_kind='eur_day'"
    ).fetchone()
    return Decimal(row["eur_total"]) if row else Decimal(0)


def test_all_four_outcomes_are_expressible() -> None:
    """ "the report path cannot express not_attempted or timeout" -- it can now."""
    assert {o.value for o in Outcome} == {"success", "failure", "timeout", "not_attempted"}


@pytest.mark.parametrize("outcome", list(Outcome))
def test_the_four_outcomes_do_not_collapse(spend: Database, outcome: Outcome) -> None:
    """ "both collapse to failed" -- each outcome is recorded as itself."""
    conn = spend.connect()
    try:
        intent = _permit(conn)
        report_result(intent, conn=conn, outcome=outcome, payload=None, error=None, now=NOW)
        row = conn.execute(
            "SELECT outcome, connector_ok FROM actions_audit WHERE kind='exec_result'"
        ).fetchone()
        assert row["outcome"] == outcome.value, "the outcome must survive to the evidence row"
        if outcome is Outcome.NOT_ATTEMPTED:
            assert row["connector_ok"] is None, (
                "connector_ok must be NULL for an action never attempted -- recording "
                "False would assert an attempt that did not happen"
            )
    finally:
        conn.close()


@pytest.mark.parametrize("outcome", SETTLES + RELEASES)
def test_settlement_depends_on_the_outcome(spend: Database, outcome: Outcome) -> None:
    """ "the reservation settles before the outcome is examined" -- it no longer does."""
    conn = spend.connect()
    try:
        intent = _permit(conn)
        report_result(intent, conn=conn, outcome=outcome, payload=None, error=None, now=NOW)
        status = conn.execute(
            "SELECT status FROM cap_reservations WHERE intent_audit_id=?",
            (intent.intent_audit_id,),
        ).fetchone()["status"]
        expected = "released" if outcome in RELEASES else "settled"
        assert status == expected, f"{outcome.value} must {expected[:-1]}, got {status}"
    finally:
        conn.close()


def test_not_attempted_does_not_charge_budget(spend: Database) -> None:
    """ "permanently charges budget for an action that never occurred" -- the defect."""
    conn = spend.connect()
    try:
        intent = _permit(conn, "10.00")
        assert _spent(conn) == Decimal("10.00"), "the permit reserves up front, as designed"
        report_result(
            intent, conn=conn, outcome=Outcome.NOT_ATTEMPTED, payload=None, error=None, now=NOW
        )
        assert _spent(conn) == Decimal(0), (
            "budget was charged for an action the enforcement point said never happened"
        )
    finally:
        conn.close()


def test_a_timeout_still_charges_because_doubt_is_not_non_occurrence(spend: Database) -> None:
    """Settle on doubt. The counterpart that makes the release safe.

    A timeout is not evidence the action did not happen -- the connector may have
    acted and simply not returned. Releasing on doubt would let a caller free budget
    by timing out, which is the failure mode the strict reading exists to prevent.
    """
    conn = spend.connect()
    try:
        intent = _permit(conn, "10.00")
        report_result(
            intent, conn=conn, outcome=Outcome.TIMEOUT, payload=None, error="timeout", now=NOW
        )
        assert _spent(conn) == Decimal("10.00"), "a timeout must settle, not release"
    finally:
        conn.close()


def test_not_attempted_releases_the_reservation(spend: Database) -> None:
    """ "releasing the reservation" -- and the budget is usable again afterwards."""
    conn = spend.connect()
    try:
        first = _permit(conn, "100.00")  # the entire daily cap
        report_result(
            first, conn=conn, outcome=Outcome.NOT_ATTEMPTED, payload=None, error=None, now=NOW
        )
        # the whole cap must be available again: the first action never happened
        second = _permit(conn, "100.00")
        assert isinstance(second, PermittedIntent)
    finally:
        conn.close()


def test_the_release_is_audited_not_silent(spend: Database) -> None:
    """ "as an audited event" -- symmetric with reclamation expiry, never silent.

    The audit's job is to make a false report attributable, not to prevent a trusted
    reporter from lying: a PEP filing a false `not_attempted` could equally file a
    false `failure` today. So the release leaves a row naming itself.
    """
    conn = spend.connect()
    try:
        intent = _permit(conn)
        report_result(
            intent, conn=conn, outcome=Outcome.NOT_ATTEMPTED, payload=None, error=None, now=NOW
        )
        rows = list(
            conn.execute(
                "SELECT kind, parent_id, detail FROM actions_audit WHERE kind=?",
                ("reservation_released",),
            )
        )
        assert len(rows) == 1, "the release must be an audited event, not a silent adjustment"
        assert rows[0]["parent_id"] == intent.intent_audit_id, "it must link to the permit it voids"
        assert "not_attempted" in rows[0]["detail"]
    finally:
        conn.close()


def test_a_release_is_distinguishable_from_a_reclamation(spend: Database) -> None:
    """Both give budget back; an evidence reader must tell them apart.

    `reservation_expired` means a deadline passed with no report at all.
    `reservation_released` means the enforcement point positively said it did not act.
    Same shape, different kind -- collapsing them would lose which one happened.
    """
    conn = spend.connect()
    try:
        intent = _permit(conn)
        report_result(
            intent, conn=conn, outcome=Outcome.NOT_ATTEMPTED, payload=None, error=None, now=NOW
        )
        kinds = {r["kind"] for r in conn.execute("SELECT kind FROM actions_audit")}
        assert "reservation_released" in kinds
        assert "reservation_expired" not in kinds, "nothing expired; the PEP reported"
    finally:
        conn.close()


def test_reporting_not_attempted_after_reclamation_does_not_double_release(
    spend: Database,
) -> None:
    """A permit already reclaimed stays reclaimed; the counter is not driven negative.

    The late report is still recorded for audit -- it is evidence about a void permit
    -- but it must not give budget back twice.
    """
    conn = spend.connect()
    try:
        intent = _permit(conn, "10.00")
        conn.execute(
            "UPDATE cap_reservations SET status='expired' WHERE intent_audit_id=?",
            (intent.intent_audit_id,),
        )
        conn.commit()
        before = _spent(conn)
        report_result(
            intent, conn=conn, outcome=Outcome.NOT_ATTEMPTED, payload=None, error=None, now=NOW
        )
        assert _spent(conn) == before, "an expired reservation must not be released again"
    finally:
        conn.close()
