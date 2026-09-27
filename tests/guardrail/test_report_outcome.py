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

from onedoor.guardrail import caps, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    ActionResult,
    Bounds,
    Caps,
    CheckId,
    Decision,
    Outcome,
    Policy,
    Source,
    Tier,
)
from onedoor.store.db import Database, tx

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


# --- no_effect on failure reports (AADP -03 §4.1) ---------------------------------


@pytest.fixture
def spend_and_call(tmp_path: Path) -> Database:
    """Both dimensions capped, so a `no_effect` release can be checked on each."""
    database = Database(str(tmp_path / "no_effect.db"))
    database.init()
    conn = database.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.spend",
            caps=Caps(daily_rate=5, eur_day=Decimal("100.00")),
            bounds=Bounds(strict_params=False),
        ),
    )
    conn.close()
    return database


def _calls(conn: object) -> int:
    row = conn.execute(  # type: ignore[attr-defined]
        "SELECT count FROM cap_counters WHERE window_kind='rate'"
    ).fetchone()
    return int(row["count"]) if row else 0


def test_a_plain_failure_still_settles(spend: Database) -> None:
    """no_effect defaults to False: a bare failure changes nothing from today."""
    conn = spend.connect()
    try:
        intent = _permit(conn, "10.00")
        report_result(
            intent, conn=conn, outcome=Outcome.FAILURE, payload=None, error="boom", now=NOW
        )
        assert _spent(conn) == Decimal("10.00"), "a failure without no_effect must settle"
        status = conn.execute(
            "SELECT status FROM cap_reservations WHERE intent_audit_id=?",
            (intent.intent_audit_id,),
        ).fetchone()["status"]
        assert status == "settled"
    finally:
        conn.close()


def test_no_effect_on_a_timeout_is_accepted_and_ignored(spend: Database) -> None:
    """AADP -03 §4.1 requires a PDP to IGNORE no_effect on any outcome but
    failure, never refuse the report over it -- the 0.8.0 behaviour (a stated
    `ReportError`) was itself the divergence."""
    conn = spend.connect()
    try:
        intent = _permit(conn, "10.00")
        result = report_result(
            intent,
            conn=conn,
            outcome=Outcome.TIMEOUT,
            payload=None,
            error="t",
            no_effect=True,
            now=NOW,
        )
        assert result.decision.decision == Decision.FAILED
        assert _spent(conn) == Decimal("10.00"), "a timeout still settles; no_effect had no bearing"
    finally:
        conn.close()


@pytest.mark.parametrize("outcome", [Outcome.SUCCESS, Outcome.NOT_ATTEMPTED])
def test_no_effect_on_success_or_not_attempted_is_accepted_and_ignored(
    spend: Database, outcome: Outcome
) -> None:
    """Accepted as if `no_effect` were absent: the disposition follows `outcome`
    alone, exactly as `test_the_four_outcomes_do_not_collapse`'s own family
    already proves for a report with no `no_effect` at all."""
    conn = spend.connect()
    try:
        intent = _permit(conn, "10.00")
        report_result(
            intent,
            conn=conn,
            outcome=outcome,
            payload=None,
            error=None,
            no_effect=True,
            now=NOW,
        )
        expected_spent = Decimal(0) if outcome is Outcome.NOT_ATTEMPTED else Decimal("10.00")
        assert _spent(conn) == expected_spent, (
            "no_effect must not change a disposition it does not apply to"
        )
    finally:
        conn.close()


def test_no_effect_ignored_is_recorded_in_the_exec_result_rows_own_detail(spend: Database) -> None:
    """A `no_effect` asserted where it does not apply is not silently dropped --
    it is recorded, once, on the row it was asserted against."""
    conn = spend.connect()
    try:
        intent = _permit(conn, "10.00")
        report_result(
            intent,
            conn=conn,
            outcome=Outcome.SUCCESS,
            payload=None,
            error=None,
            no_effect=True,
            now=NOW,
        )
        row = conn.execute("SELECT detail FROM actions_audit WHERE kind='exec_result'").fetchone()
        assert "no_effect" in row["detail"] and "ignored" in row["detail"]
    finally:
        conn.close()


def test_no_effect_ignored_flag_is_absent_when_no_effect_genuinely_applies(
    spend: Database,
) -> None:
    """The flag names an IGNORED assertion specifically -- a genuine
    `failure`+`no_effect` report (the one case it does apply to) carries none."""
    conn = spend.connect()
    try:
        intent = _permit(conn, "10.00")
        report_result(
            intent,
            conn=conn,
            outcome=Outcome.FAILURE,
            payload=None,
            error="boom",
            no_effect=True,
            now=NOW,
        )
        row = conn.execute("SELECT detail FROM actions_audit WHERE kind='exec_result'").fetchone()
        assert row["detail"] == ""
    finally:
        conn.close()


def test_sabotage_the_old_refusal_would_have_rejected_this_exact_report() -> None:
    """The four tests above are not vacuous. `report_result` used to raise
    `ReportError` here:

        if no_effect and outcome is not Outcome.FAILURE:
            raise ReportError(...)

    reconstructed verbatim and checked against the exact input
    `test_no_effect_on_a_timeout_is_accepted_and_ignored` uses -- proving the
    removed check really would have refused the report the fix now accepts,
    not that it happened to never apply."""
    outcome = Outcome.TIMEOUT
    no_effect = True
    old_check_would_have_refused = no_effect and outcome is not Outcome.FAILURE
    assert old_check_would_have_refused, (
        "the removed check must actually fire on this input, or the acceptance "
        "test above proves nothing about the fix"
    )


def test_a_failure_with_no_effect_releases_the_value_budget(spend_and_call: Database) -> None:
    conn = spend_and_call.connect()
    try:
        intent = _permit(conn, "10.00")
        assert _spent(conn) == Decimal("10.00")
        report_result(
            intent,
            conn=conn,
            outcome=Outcome.FAILURE,
            payload=None,
            error="boom",
            no_effect=True,
            now=NOW,
        )
        assert _spent(conn) == Decimal(0), "no_effect must release the value dimension"
    finally:
        conn.close()


def test_a_failure_with_no_effect_never_releases_the_rate_budget(
    spend_and_call: Database,
) -> None:
    """-03 §4.1: the attempt happened -- that is why this is a failure, not a
    not_attempted -- so the call it made still counts against the rate budget."""
    conn = spend_and_call.connect()
    try:
        intent = _permit(conn, "10.00")
        assert _calls(conn) == 1
        report_result(
            intent,
            conn=conn,
            outcome=Outcome.FAILURE,
            payload=None,
            error="boom",
            no_effect=True,
            now=NOW,
        )
        assert _calls(conn) == 1, "the rate counter must stay charged after a no_effect release"
    finally:
        conn.close()


def test_no_effect_release_is_audited_and_distinct_from_not_attempted(
    spend_and_call: Database,
) -> None:
    conn = spend_and_call.connect()
    try:
        intent = _permit(conn, "10.00")
        report_result(
            intent,
            conn=conn,
            outcome=Outcome.FAILURE,
            payload=None,
            error="boom",
            no_effect=True,
            now=NOW,
        )
        rows = list(
            conn.execute(
                "SELECT parent_id, detail FROM actions_audit WHERE kind='reservation_released'"
            )
        )
        assert len(rows) == 1
        assert rows[0]["parent_id"] == intent.intent_audit_id
        assert "no_effect" in rows[0]["detail"]
        assert "not_attempted" not in rows[0]["detail"]

        status = conn.execute(
            "SELECT status FROM cap_reservations WHERE intent_audit_id=?",
            (intent.intent_audit_id,),
        ).fetchone()["status"]
        assert status == "released"

        outcome_row = conn.execute(
            "SELECT outcome, connector_ok FROM actions_audit WHERE kind='exec_result'"
        ).fetchone()
        assert outcome_row["outcome"] == "failure"
        assert outcome_row["connector_ok"] is not None and not outcome_row["connector_ok"], (
            "an attempt was made and failed -- unlike not_attempted, connector_ok is "
            "False, never NULL"
        )
    finally:
        conn.close()


def test_no_effect_on_an_already_reclaimed_reservation_does_not_double_release(
    spend_and_call: Database,
) -> None:
    conn = spend_and_call.connect()
    try:
        intent = _permit(conn, "10.00")
        conn.execute(
            "UPDATE cap_reservations SET status='expired' WHERE intent_audit_id=?",
            (intent.intent_audit_id,),
        )
        conn.commit()
        before = _spent(conn)
        report_result(
            intent,
            conn=conn,
            outcome=Outcome.FAILURE,
            payload=None,
            error="boom",
            no_effect=True,
            now=NOW,
        )
        assert _spent(conn) == before, "an expired reservation must not be released again"
    finally:
        conn.close()


# --- not_attempted never releases the rate dimension ------------------------------


@pytest.fixture
def rate_capped(tmp_path: Path) -> Database:
    """A rate cap of exactly 1 -- tight enough that a second decide, right after
    the first is reported `not_attempted`, directly proves whether the call-count
    slot came back."""
    database = Database(str(tmp_path / "rate_capped.db"))
    database.init()
    conn = database.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.spend",
            caps=Caps(daily_rate=1),
            bounds=Bounds(strict_params=False),
        ),
    )
    conn.close()
    return database


def _second_decide(conn: object) -> ActionResult | PermittedIntent:
    return decide_and_reserve(
        ActionRequest(
            request_id=uuid4(),
            action_type="demo.spend",
            params={},
            source=Source.UI,
            rationale="second",
            cost_eur=Decimal("1.00"),
            created_at=NOW,
        ),
        conn=conn,  # type: ignore[arg-type]
        config=CONFIG,
        now=NOW,
    )


def test_not_attempted_repeated_past_the_rate_limit_still_denies(rate_capped: Database) -> None:
    """Decide, then `not_attempted`, repeated past the rate limit, must still
    deny with `rate_exhausted` -- proving the rate counter was never given
    back, unlike the value dimension."""
    conn = rate_capped.connect()
    try:
        first = _permit(conn, "1.00")
        report_result(
            first, conn=conn, outcome=Outcome.NOT_ATTEMPTED, payload=None, error=None, now=NOW
        )
        second = _second_decide(conn)
        assert isinstance(second, ActionResult)
        assert second.decision.decision == Decision.DENIED
        assert second.decision.reason_code == CheckId.RATE_EXHAUSTED
    finally:
        conn.close()


def test_sabotage_releasing_the_rate_counter_again_lets_the_limit_be_exceeded(
    rate_capped: Database,
) -> None:
    """The positive test above is not vacuous: releasing the rate delta again
    after `report_result` -- exactly what the pre-fix code did for
    `not_attempted` (`released_deltas = all_deltas if outcome is
    Outcome.NOT_ATTEMPTED else ...`) -- reproduced here directly against the
    live counters, shows the identical two-decide sequence now wrongly executes
    a second time instead of denying."""
    conn = rate_capped.connect()
    try:
        first = _permit(conn, "1.00")
        report_result(
            first, conn=conn, outcome=Outcome.NOT_ATTEMPTED, payload=None, error=None, now=NOW
        )
        # Sabotage: reproduce the old bug's own effect directly, against the same
        # live counters `check_and_reserve`/`release` already maintain.
        with tx(conn):
            caps.release(conn, [("demo.spend", "rate", caps._day_key(NOW, CONFIG.tz), 1, "0")])
        second = _second_decide(conn)
        assert isinstance(second, PermittedIntent), (
            "sabotaging the release must let a second call through -- proving the "
            "positive test's denial actually depends on the fix, not on something else"
        )
    finally:
        conn.close()
