"""A permit outlives the process that issued it (ND-010).

The DoD test is `test_a_restart_between_decide_and_report_loses_nothing`: decide, throw
the app object away, rebuild, report, and assert the report is accepted, the reservation
settles, **no new audit identity is created**, and the reservation total is unchanged.

The two tests that matter as much are the ones guarding findings the decomposition made
before any code was written:

- **a rebuilt permit cannot carry a synthesised `cost_eur`**, because it has no such
  field to carry — checked structurally, not by inspecting a value;
- **a post-restart result row keeps the intent's `received` provenance**, because
  `frozen_params` would otherwise re-serialise and stamp `serialized` on bytes that
  arrived verbatim. A wrong label on a receipt, written when nobody is watching.
"""

from __future__ import annotations

from dataclasses import fields
from decimal import Decimal
from sqlite3 import Connection

import pytest

from onedoor.guardrail import policy_loader, rebuild
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
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _spend_policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("100")),
            cost_param="amount_eur",
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )


def _permit(conn: Connection, config: EngineConfig, amount: str = "5") -> PermittedIntent:
    _spend_policy(conn)
    outcome = decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal(amount)}, cost_eur=Decimal(amount)),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(outcome, PermittedIntent)
    return outcome


def _counters(conn: Connection) -> list[tuple[object, ...]]:
    return [tuple(r) for r in conn.execute("SELECT * FROM cap_counters ORDER BY 1,2,3")]


# --- The DoD test -----------------------------------------------------------------


def test_a_restart_between_decide_and_report_loses_nothing(
    conn: Connection, config: EngineConfig
) -> None:
    """Decide, lose the process, report anyway. The core's binding constraint.

    Reconstructed intents are **the same durable rows**, never new ones: no new evidence
    identity and no budget re-reservation (§invariants #9, §idem). Both asserted by
    counting rather than by trusting.
    """
    permit = _permit(conn, config)
    rows_before = conn.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"]
    counters_before = _counters(conn)

    # The process dies here. Everything in memory is gone; only the ledger remains.
    del permit

    rebuilt = rebuild.rebuild(conn, rows_before)
    assert rebuilt.status is rebuild.RebuildStatus.REBUILT, rebuilt.detail
    assert rebuilt.intent is not None

    result = report_result(
        rebuilt.intent,
        conn=conn,
        outcome=Outcome.SUCCESS,
        payload={"ok": True},
        error=None,
        now=FROZEN_NOW,
    )
    assert result.decision.decision.value == "executed"

    reservation = conn.execute("SELECT status FROM cap_reservations").fetchone()
    assert reservation["status"] == "settled", "the held budget must settle, not linger"
    assert _counters(conn) == counters_before, "a rebuild must not re-reserve"

    rows_after = conn.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"]
    assert rows_after == rows_before + 1, "exactly one result row, no new intent identity"
    assert (
        conn.execute("SELECT COUNT(*) AS n FROM actions_audit WHERE kind='exec_intent'").fetchone()[
            "n"
        ]
        == 1
    )


# --- Finding one: no synthesised values, checked structurally ----------------------


def test_a_rebuilt_permit_has_no_field_it_would_have_to_invent() -> None:
    """`rationale`, `cost_eur` and `session_id` are stored nowhere in `actions_audit`.

    A rebuild that reconstructed an `ActionRequest` would pass `cost_eur=Decimal(0)` —
    a default that looks like a fact, which any later reader would take at face value.
    The type simply has no such field, so the mistake is unavailable rather than
    avoided: R032 §3's *surface the gap, do not synthesise*, made structural.
    """
    names = {f.name for f in fields(rebuild.RebuiltIntent)}
    for unstored in ("cost_eur", "rationale", "session_id", "request", "params"):
        assert unstored not in names, (
            f"RebuiltIntent carries {unstored!r}, which the ledger does not store — so "
            f"its value can only have been invented"
        )
    assert {"intent_audit_id", "params_provenance", "reservation_deltas"} <= names, (
        "a rebuilt permit must carry provenance to the rows it derives from (R032 §3)"
    )


def test_a_rebuilt_permit_names_the_request_time_apart_from_a_row_time() -> None:
    """R033 §3, at the field level. Two timestamps under one name is X-14's shape."""
    names = {f.name for f in fields(rebuild.RebuiltIntent)}
    assert "requested_at" in names
    assert "created_at" not in names, (
        "a rebuilt permit must not carry a `created_at`: the result row's stamp comes "
        "from `now`, because the ledger records when it LEARNED the outcome"
    )


def test_a_rebuilt_report_is_stamped_now_not_backdated(
    conn: Connection, config: EngineConfig
) -> None:
    """The ledger never testifies to a moment it did not witness (R033 §3)."""
    from datetime import timedelta

    _permit(conn, config)
    later = FROZEN_NOW + timedelta(days=3)
    rebuilt = rebuild.rebuild(conn, 1)
    assert rebuilt.intent is not None
    assert rebuilt.intent.requested_at == FROZEN_NOW

    report_result(
        rebuilt.intent,
        conn=conn,
        outcome=Outcome.SUCCESS,
        payload=None,
        error=None,
        now=later,
    )
    row = conn.execute("SELECT created_at FROM actions_audit WHERE kind='exec_result'").fetchone()
    assert row["created_at"].startswith("2026-07-08"), (
        "the result row was backdated to the request time; it must record when the "
        "ledger learned the outcome"
    )


# --- Finding two: provenance survives the restart ---------------------------------


def test_a_post_restart_result_keeps_the_received_provenance(
    conn: Connection, config: EngineConfig
) -> None:
    """The regression this ticket was closest to shipping.

    `report_result` hands the request to `audit.append`, which calls `frozen_params`:
    it returns `params_raw` verbatim, or **re-serialises when `params_raw` is None** —
    and only a live ingress sets `params_raw`. A rebuilt request would therefore have
    stamped `serialized` on bytes that arrived `received`. Not a crash and not a test
    failure: a wrong label on a receipt, written at the moment the system is least
    observed.
    """
    _spend_policy(conn)
    raw = '{"amount_eur": "5", "note": "as the caller sent it"}'
    request = ActionRequest(
        request_id=make_request("demo.spend", {}).request_id,
        action_type="demo.spend",
        params={"amount_eur": Decimal("5"), "note": "as the caller sent it"},
        source=Source.LLM,
        rationale="received bytes",
        cost_eur=Decimal("5"),
        created_at=FROZEN_NOW,
        params_raw=raw,
    )
    outcome = decide_and_reserve(request, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(outcome, PermittedIntent)

    intent_row = conn.execute(
        "SELECT params_json, params_provenance FROM actions_audit WHERE kind='exec_intent'"
    ).fetchone()
    assert intent_row["params_provenance"] == "received"
    assert intent_row["params_json"] == raw, "E10: the caller's bytes, frozen"

    rebuilt = rebuild.rebuild(conn, outcome.intent_audit_id)
    assert rebuilt.intent is not None
    report_result(
        rebuilt.intent,
        conn=conn,
        outcome=Outcome.SUCCESS,
        payload=None,
        error=None,
        now=FROZEN_NOW,
    )
    result_row = conn.execute(
        "SELECT params_json, params_provenance FROM actions_audit WHERE kind='exec_result'"
    ).fetchone()
    assert result_row["params_provenance"] == "received", (
        "the rebuilt report re-labelled received bytes as serialized"
    )
    assert result_row["params_json"] == raw, "and it re-serialised them, so they differ"


# --- The four outcomes at recovery time -------------------------------------------


def test_an_unknown_intent_is_absent_not_an_error(conn: Connection) -> None:
    assert rebuild.rebuild(conn, 999).status is rebuild.RebuildStatus.ABSENT


def test_an_already_reported_intent_is_absent(conn: Connection, config: EngineConfig) -> None:
    """Reported once is the normal end state, not a fault."""
    permit = _permit(conn, config)
    report_result(
        permit, conn=conn, outcome=Outcome.SUCCESS, payload=None, error=None, now=FROZEN_NOW
    )
    outcome = rebuild.rebuild(conn, permit.intent_audit_id)
    assert outcome.status is rebuild.RebuildStatus.ABSENT
    assert "already reported" in outcome.detail


def test_a_reservation_without_its_intent_is_unverifiable(
    conn: Connection, config: EngineConfig
) -> None:
    """`cap_reservations` has no foreign key to `actions_audit`, so this is reachable.

    Reading it as "nothing to do" would leave the budget held until the reclaimer voids
    it — quietly, and in a direction someone pays for.
    """
    _permit(conn, config)
    with tx(conn):
        conn.execute(
            "INSERT INTO cap_reservations "
            "(intent_audit_id, request_id, deadline_utc, deltas_json, status, created_utc) "
            "VALUES (?,?,?,?,?,?)",
            (4242, "r", "2026-07-05T13:00:00Z", "[]", "held", "2026-07-05T12:00:00Z"),
        )
    outcome = rebuild.rebuild(conn, 4242)
    assert outcome.status is rebuild.RebuildStatus.UNVERIFIABLE
    assert "disagrees with itself" in outcome.detail


def test_an_unreadable_reservation_is_failed_not_absent(
    conn: Connection, config: EngineConfig
) -> None:
    """Stored and unreadable is a third thing again."""
    permit = _permit(conn, config)
    with tx(conn):
        conn.execute(
            "UPDATE cap_reservations SET deltas_json='{not json' WHERE intent_audit_id=?",
            (permit.intent_audit_id,),
        )
    outcome = rebuild.rebuild(conn, permit.intent_audit_id)
    assert outcome.status is rebuild.RebuildStatus.FAILED
    assert outcome.intent is None


def test_pending_is_read_from_the_ledger(conn: Connection, config: EngineConfig) -> None:
    """The whole ticket in one assertion: pending state is a query, not a dict."""
    first = _permit(conn, config)
    second = _permit(conn, config)
    assert rebuild.pending(conn) == [first.intent_audit_id, second.intent_audit_id]
    report_result(
        first, conn=conn, outcome=Outcome.SUCCESS, payload=None, error=None, now=FROZEN_NOW
    )
    assert rebuild.pending(conn) == [second.intent_audit_id]


def test_a_rebuilt_not_attempted_releases_the_budget(
    conn: Connection, config: EngineConfig
) -> None:
    """R005 through the rebuilt path: release on a positive assertion of non-occurrence."""
    permit = _permit(conn, config, amount="7")
    rebuilt = rebuild.rebuild(conn, permit.intent_audit_id)
    assert rebuilt.intent is not None
    report_result(
        rebuilt.intent,
        conn=conn,
        outcome=Outcome.NOT_ATTEMPTED,
        payload=None,
        error=None,
        now=FROZEN_NOW,
    )
    assert conn.execute("SELECT status FROM cap_reservations").fetchone()["status"] == "released"
    assert (
        conn.execute(
            "SELECT COUNT(*) AS n FROM actions_audit WHERE kind='reservation_released'"
        ).fetchone()["n"]
        == 1
    ), "the release is an audited event, never a silent adjustment"


@pytest.mark.parametrize("outcome", list(Outcome))
def test_every_outcome_reports_through_a_rebuilt_permit(
    conn: Connection, config: EngineConfig, outcome: Outcome
) -> None:
    """Generated over the vocabulary rather than spot-checking success."""
    permit = _permit(conn, config)
    rebuilt = rebuild.rebuild(conn, permit.intent_audit_id)
    assert rebuilt.intent is not None
    result = report_result(
        rebuilt.intent, conn=conn, outcome=outcome, payload=None, error=None, now=FROZEN_NOW
    )
    assert result.request_id == permit.request.request_id
