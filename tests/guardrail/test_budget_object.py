"""The `budget` object on a cap denial (ND-003 / W5, AADP A4).

W4 made the reason codes unit-neutral, which cost something on purpose: `cap_value`
collapses what used to be `cap_eur_day` and `cap_eur_month`, so the reason code alone
can no longer say which window broke. That was a *visible, temporary* granularity
regression against 0.3.5, and this is the ticket that closes it — the window moves
from prose in `detail` into a machine-readable object a PEP can act on.

Confirmed normative under the evidence section (E7): a `cap_value` denial that cannot
name its window is not re-derivable. So the object is **persisted**, not merely
returned, and these tests check the stored row as well as the reply.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    Decision,
    Policy,
    Source,
    Tier,
)
from onedoor.store.db import Database

NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)
AMS = EngineConfig(
    approval_ttl_seconds=3600,
    connector_timeout_seconds=5.0,
    tz=ZoneInfo("Europe/Amsterdam"),
)


def _db(tmp_path: Path, name: str, caps: Caps) -> Database:
    database = Database(str(tmp_path / f"{name}.db"))
    database.init()
    conn = database.connect()
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.spend",
            caps=caps,
            bounds=Bounds(strict_params=False),
        ),
    )
    conn.close()
    return database


def _spend(conn: object, amount: str) -> object:
    return decide_and_reserve(
        ActionRequest(
            request_id=uuid4(),
            action_type="demo.spend",
            params={},
            source=Source.UI,
            rationale="budget",
            cost_eur=Decimal(amount),
            created_at=NOW,
        ),
        conn=conn,  # type: ignore[arg-type]
        config=AMS,
        now=NOW,
    )


def test_a_value_cap_denial_carries_the_window_the_reason_code_no_longer_says(
    tmp_path: Path,
) -> None:
    conn = _db(tmp_path, "day", Caps(eur_day=Decimal("10.00"))).connect()
    try:
        _spend(conn, "9.00")
        denied = _spend(conn, "2.00")
        d = denied.decision  # type: ignore[union-attr]
        assert d.decision is Decision.DENIED
        assert d.reason_code.value == "cap_value"

        budget = d.budget
        assert budget is not None, "a cap_value denial MUST carry the budget object"
        assert budget.dimension == "value"
        assert budget.unit == "EUR", "currency lives in `unit`, never in a field name"
        assert budget.window == "day", "the window the reason code stopped carrying"
    finally:
        conn.close()


def test_a_month_cap_denial_is_distinguishable_from_a_day_one(tmp_path: Path) -> None:
    """The whole point of ND-003: both deny `cap_value`, and they must not look alike."""
    conn = _db(tmp_path, "month", Caps(eur_month=Decimal("50.00"))).connect()
    try:
        _spend(conn, "49.00")
        denied = _spend(conn, "2.00")
        budget = denied.decision.budget  # type: ignore[union-attr]
        assert budget is not None
        assert budget.window == "month"
        assert denied.decision.reason_code.value == "cap_value"  # type: ignore[union-attr]
    finally:
        conn.close()


def test_a_rate_cap_denial_uses_the_rate_dimension_and_a_token_unit(tmp_path: Path) -> None:
    conn = _db(tmp_path, "rate", Caps(daily_rate=1)).connect()
    try:
        _spend(conn, "0")
        denied = _spend(conn, "0")
        budget = denied.decision.budget  # type: ignore[union-attr]
        assert denied.decision.reason_code.value == "cap_rate"  # type: ignore[union-attr]
        assert budget is not None
        assert budget.dimension == "rate"
        assert budget.unit == "calls", "a rate is counted in a token, not a currency"
        assert budget.limit == "1" and budget.consumed == "1" and budget.remaining == "0"
    finally:
        conn.close()


def test_every_numeric_field_is_a_canonical_decimal_string(tmp_path: Path) -> None:
    """E8: decimal strings, shortest-exact, never floats and never JSON numbers.

    `10.00` records as `"10"`, so two policies expressing the same limit differently
    produce the same bytes -- one form for wire, storage and preimage.
    """
    conn = _db(tmp_path, "canon", Caps(eur_day=Decimal("10.00"))).connect()
    try:
        _spend(conn, "9.500")
        budget = _spend(conn, "2.00").decision.budget  # type: ignore[union-attr]
        assert budget is not None
        assert budget.limit == "10", f"authored scale must not survive: {budget.limit}"
        assert budget.consumed == "9.5"
        assert budget.remaining == "0.5"
        for field in (budget.limit, budget.consumed, budget.remaining):
            assert isinstance(field, str)
            assert "E" not in field.upper(), "never exponent form"
    finally:
        conn.close()


def test_the_reset_instant_matches_the_timezone_the_counters_use(tmp_path: Path) -> None:
    """The budget must not name a reset that disagrees with its own counter.

    Windows are keyed in the policy timezone, so the reset instant is derived from the
    same clock and rendered canonically in UTC. Amsterdam is UTC+2 in July, so the day
    window rolls at 22:00Z the previous evening -- a UTC-derived answer would be two
    hours wrong and would look right.
    """
    conn = _db(tmp_path, "tz", Caps(eur_day=Decimal("10.00"))).connect()
    try:
        _spend(conn, "9.00")
        budget = _spend(conn, "2.00").decision.budget  # type: ignore[union-attr]
        assert budget is not None
        assert budget.window_resets_at == "2026-07-05T22:00:00Z"
    finally:
        conn.close()


def test_the_budget_is_persisted_not_merely_returned(tmp_path: Path) -> None:
    """E7. Evidence that cannot name its window is not re-derivable."""
    conn = _db(tmp_path, "persist", Caps(eur_day=Decimal("10.00"))).connect()
    try:
        _spend(conn, "9.00")
        _spend(conn, "2.00")
        row = conn.execute(
            "SELECT budget_json FROM actions_audit WHERE budget_json IS NOT NULL"
        ).fetchone()
        assert row is not None, "the denial must persist its budget"
        stored = json.loads(row["budget_json"])
        assert stored["window"] == "day"
        assert stored["limit"] == "10"
        assert set(stored) == {
            "dimension",
            "unit",
            "window",
            "limit",
            "consumed",
            "remaining",
            "window_resets_at",
        }, "all seven fields are REQUIRED"
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("caps", "amount", "why"),
    [
        (Caps(eur_day=Decimal("10.00")), "1.00", "permitted: nothing was denied"),
        (Caps(daily_rate=5), "0", "permitted under a rate cap"),
    ],
)
def test_no_budget_when_nothing_was_capped(
    tmp_path: Path, caps: Caps, amount: str, why: str
) -> None:
    """Present **iff** deny + cap_value/cap_rate. A permit carries no budget."""
    conn = _db(tmp_path, "none", caps).connect()
    try:
        outcome = _spend(conn, amount)
        assert isinstance(outcome, PermittedIntent), why
        rows = list(
            conn.execute("SELECT budget_json FROM actions_audit WHERE budget_json IS NOT NULL")
        )
        assert rows == [], "a permitted action must not persist a budget"
    finally:
        conn.close()


def test_a_non_cap_denial_carries_no_budget(tmp_path: Path) -> None:
    """`cost_unknown` reaches the same branch and must NOT invent budget state.

    There is no budget to report when the amount could not be resolved -- reporting
    one would be a number with nothing behind it. The probe supplies the declared
    cost parameter as a boolean: present, so the required-param check passes, but
    unusable as money, so cost resolution refuses it. (`resolve_cost` returning None
    is a denial, never an assumed zero -- reading "unset" as "free" was the F7 defect.)
    """
    database = Database(str(tmp_path / "unknown.db"))
    database.init()
    conn = database.connect()
    try:
        policy_loader.upsert(
            conn,
            Policy(
                action_type="demo.spend",
                tier=Tier.AUTO_CAPPED,
                dry_run=False,
                compensating_command="demo.spend",
                cost_param="amount_eur",
                caps=Caps(eur_day=Decimal("10.00")),
                # required, so the amount must be present; NOT in `numeric`, so bounds
                # does not reject it before cost resolution gets a look.
                bounds=Bounds(required=["amount_eur"], strict_params=False),
            ),
        )
        denied = decide_and_reserve(
            ActionRequest(
                request_id=uuid4(),
                action_type="demo.spend",
                params={"amount_eur": True},
                source=Source.UI,
                rationale="budget",
                created_at=NOW,
            ),
            conn=conn,
            config=AMS,
            now=NOW,
        )
        assert denied.decision.reason_code.value == "cost_unknown"  # type: ignore[union-attr]
        assert denied.decision.budget is None  # type: ignore[union-attr]
    finally:
        conn.close()
