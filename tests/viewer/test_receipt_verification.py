"""The four outcomes, held apart (ND-051 / V1).

`absent`, `unverifiable` and `failed` are distinct and must never collapse (R010).
In a viewer that is not a technicality, it is the product: a page that shows a value
it could not confirm is the dashboard failure this whole design is built against.

The distinction these tests protect hardest is **absent versus unverifiable**:

- `row_hash` is NULL because `ND-001` has not run. Absent. A fact about the roadmap.
- A policy snapshot row that is gone was produced and then lost. Unverifiable. A fact
  about this store, and someone has to look at it.

Both are "there is no value here". Only one of them is fine.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.guardrail.receipt import (
    CHAIN_COLUMNS,
    Status,
    fetch_decision,
    hero_decision,
    latest_verdicts,
    verify_decision,
)
from onedoor.store.db import Database, tx
from tests.conftest import FROZEN_NOW, make_request


def _spend_policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("10")),
            cost_param="amount_eur",
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )


def _deny_with_budget(conn: Connection, config: EngineConfig) -> int:
    """Produce the demo hero: a cap denial carrying a seven-field budget."""
    _spend_policy(conn)
    result = decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("99")}, cost_eur=Decimal("99")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert result.decision.reason_code.value == "cap_value"  # type: ignore[union-attr]
    return int(result.audit_id)  # type: ignore[union-attr,arg-type]


def test_a_sound_receipt_reports_every_check(conn: Connection, config: EngineConfig) -> None:
    audit_id = _deny_with_budget(conn, config)
    verification = verify_decision(conn, fetch_decision(conn, audit_id))  # type: ignore[arg-type]
    assert verification.sound
    assert not verification.faults
    names = [c.name for c in verification.checks]
    assert names == [
        "params_byte_form",
        "params_provenance",
        "reason_vocabulary",
        "budget_object",
        "policy_snapshot",
        "chain",
        "append_only",
    ], "byte-form checks run before anything hashes (R028), and the order is the contract"


def test_the_chain_is_absent_not_verified_and_not_failed(
    conn: Connection, config: EngineConfig
) -> None:
    """ND-001 has not run. The honest word for that is `absent`.

    Not `verified` -- there is nothing to verify. Not `failed` -- nothing is wrong.
    A viewer that rendered a green tick here would be showing confidence in a NULL.
    """
    audit_id = _deny_with_budget(conn, config)
    chain = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("chain")  # type: ignore[arg-type]
    assert chain.status is Status.ABSENT
    assert "ND-001" in chain.detail, "an absent state names the ticket that will fill it"


def test_a_half_written_chain_is_unverifiable_not_absent(
    conn: Connection, config: EngineConfig
) -> None:
    """Produced and then lost is a different fact from not yet produced (R015).

    A chain with `seq` set and `row_hash` NULL is not a feature that has not run; it
    is a feature that ran and did not finish, and calling that "absent" would file a
    fault under "nothing to see here".
    """
    audit_id = _deny_with_budget(conn, config)
    # The audit table is append-only by trigger, so this writes through a fresh
    # connection with the trigger dropped -- simulating a store damaged elsewhere,
    # which is exactly the case the check exists for.
    _force_column(conn, audit_id, "seq", 42)
    chain = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("chain")  # type: ignore[arg-type]
    assert chain.status is Status.UNVERIFIABLE
    assert "partly written" in chain.detail
    assert not verify_decision(conn, fetch_decision(conn, audit_id)).sound  # type: ignore[arg-type]


def _force_column(conn: Connection, audit_id: int, column: str, value: object) -> None:
    """Write a column the append-only trigger forbids, to simulate outside damage.

    The trigger is dropped and restored so the store is otherwise as production has
    it -- the point is to test the CHECKER against a damaged row, not to test whether
    the trigger works, which `tests/guardrail/test_audit_append_only.py` already does.
    """
    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute(f"UPDATE actions_audit SET {column}=? WHERE id=?", (value, audit_id))  # noqa: S608
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )


def test_a_missing_policy_snapshot_is_unverifiable(conn: Connection, config: EngineConfig) -> None:
    """The rules that produced the verdict cannot be re-read. Surface it, never skip it."""
    audit_id = _deny_with_budget(conn, config)
    with tx(conn):
        conn.execute("DROP TRIGGER policy_versions_no_delete")
        conn.execute("DELETE FROM policy_versions")
    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("policy_snapshot")  # type: ignore[arg-type]
    assert check.status is Status.UNVERIFIABLE
    assert not verify_decision(conn, fetch_decision(conn, audit_id)).sound  # type: ignore[arg-type]


def test_a_tampered_snapshot_fails_rather_than_being_unverifiable(
    conn: Connection, config: EngineConfig
) -> None:
    """The snapshot is there and does not hash to what the row records. That is a fault."""
    audit_id = _deny_with_budget(conn, config)
    with tx(conn):
        conn.execute("DROP TRIGGER policy_versions_no_update")
        conn.execute("UPDATE policy_versions SET snapshot_json = snapshot_json || ' '")
    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("policy_snapshot")  # type: ignore[arg-type]
    assert check.status is Status.FAILED
    assert "hashes to" in check.detail


def test_the_snapshot_check_is_not_a_tautology(conn: Connection, config: EngineConfig) -> None:
    """R028: a digest checked against a file's own bytes is a tautology dressed as a check.

    This one compares two SEPARATELY STORED fields -- the snapshot text in
    `policy_versions` and the `policy_version` stamped on the audit row -- so changing
    either one alone breaks it. Asserted by changing each one alone.
    """
    audit_id = _deny_with_budget(conn, config)
    original = fetch_decision(conn, audit_id)["policy_version"]  # type: ignore[index]

    _force_column(conn, audit_id, "policy_version", "0" * 64)
    assert (
        verify_decision(conn, fetch_decision(conn, audit_id)).by_name("policy_snapshot").status  # type: ignore[arg-type]
        is Status.UNVERIFIABLE
    ), "changing only the row's stamp must break it"

    _force_column(conn, audit_id, "policy_version", original)
    with tx(conn):
        conn.execute("DROP TRIGGER policy_versions_no_update")
        conn.execute("UPDATE policy_versions SET snapshot_json='{}'")
    assert (
        verify_decision(conn, fetch_decision(conn, audit_id)).by_name("policy_snapshot").status  # type: ignore[arg-type]
        is Status.FAILED
    ), "changing only the stored snapshot must break it"


def test_a_cap_denial_without_a_budget_fails(conn: Connection, config: EngineConfig) -> None:
    """E7: a cap denial that cannot name its window is not re-derivable."""
    audit_id = _deny_with_budget(conn, config)
    _force_column(conn, audit_id, "budget_json", None)
    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("budget_object")  # type: ignore[arg-type]
    assert check.status is Status.FAILED
    assert "window cannot be named" in check.detail


def test_a_budget_on_a_non_cap_verdict_fails(conn: Connection, config: EngineConfig) -> None:
    """Present iff deny-and-cap. The `iff` is a claim in both directions."""
    audit_id = _deny_with_budget(conn, config)
    _force_column(conn, audit_id, "reason_code", "bounds")
    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("budget_object")  # type: ignore[arg-type]
    assert check.status is Status.FAILED


def test_params_byte_form_fails_before_anything_hashes(
    conn: Connection, config: EngineConfig
) -> None:
    """Bytes that are not JSON are reported as bytes that are not JSON."""
    audit_id = _deny_with_budget(conn, config)
    _force_column(conn, audit_id, "params_json", "{not json")
    verification = verify_decision(conn, fetch_decision(conn, audit_id))  # type: ignore[arg-type]
    check = verification.by_name("params_byte_form")
    assert check.status is Status.FAILED
    assert "not valid JSON" in check.detail
    assert not verification.sound


def test_an_undeclared_provenance_fails_but_an_absent_one_does_not(
    conn: Connection, config: EngineConfig
) -> None:
    """A pre-0.4.0 row has no provenance and that is a fact about its age (R015)."""
    audit_id = _deny_with_budget(conn, config)

    _force_column(conn, audit_id, "params_provenance", None)
    v = verify_decision(conn, fetch_decision(conn, audit_id))  # type: ignore[arg-type]
    assert v.by_name("params_provenance").status is Status.ABSENT
    assert v.sound, "an absent provenance on an old row does not make the receipt unsound"

    _force_column(conn, audit_id, "params_provenance", "invented")
    v = verify_decision(conn, fetch_decision(conn, audit_id))  # type: ignore[arg-type]
    assert v.by_name("params_provenance").status is Status.FAILED
    assert not v.sound


def test_a_reason_code_outside_the_vocabulary_fails(conn: Connection, config: EngineConfig) -> None:
    audit_id = _deny_with_budget(conn, config)
    _force_column(conn, audit_id, "reason_code", "cap_eur_day")  # retired in 0.4.0
    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("reason_vocabulary")  # type: ignore[arg-type]
    assert check.status is Status.FAILED


def test_a_store_without_the_append_only_triggers_fails(
    conn: Connection, config: EngineConfig
) -> None:
    """The ledger's central claim, checked rather than assumed."""
    audit_id = _deny_with_budget(conn, config)
    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_delete")
    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("append_only")  # type: ignore[arg-type]
    assert check.status is Status.FAILED
    assert "actions_audit_no_delete" in check.detail


def test_the_hero_is_the_deny_with_budget(conn: Connection, config: EngineConfig) -> None:
    """The spec names it, and it is picked by verdict shape rather than by position."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.plain",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    hero_id = _deny_with_budget(conn, config)
    # A later, ordinary decision must not displace it.
    decide_and_reserve(make_request("demo.plain", {}), conn=conn, config=config, now=FROZEN_NOW)
    chosen = hero_decision(conn)
    assert chosen is not None
    assert chosen["id"] == hero_id
    assert json.loads(chosen["budget_json"])["window"] == "day"


def test_the_hero_falls_back_rather_than_requiring_a_denial(
    conn: Connection, config: EngineConfig
) -> None:
    """A viewer that needs a particular verdict to exist cannot be pointed at a real
    system on its first day."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.plain",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    decide_and_reserve(make_request("demo.plain", {}), conn=conn, config=config, now=FROZEN_NOW)
    assert hero_decision(conn) is not None


def test_an_empty_store_has_no_hero_and_no_tail(tmp_path: Path) -> None:
    """None, not an exception and not an invented row."""
    database = Database(str(tmp_path / "empty.db"))
    database.init()
    empty = database.connect()
    try:
        assert hero_decision(empty) is None
        assert latest_verdicts(empty) == []
    finally:
        empty.close()


def test_the_tail_shows_permits_as_well_as_denials(conn: Connection, config: EngineConfig) -> None:
    """Found by a failing test, and it matters more than it looks.

    `kind='decision'` is every terminal verdict EXCEPT a permit -- a permitted action
    writes `exec_intent`. A tail filtered to `decision` alone would show denials and
    nothing else, and would read as a machine that only ever refuses. A feed that
    systematically omits every approval is not a faithful record, and faithful is the
    entire claim.
    """
    _deny_with_budget(conn, config)
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.plain",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    decide_and_reserve(make_request("demo.plain", {}), conn=conn, config=config, now=FROZEN_NOW)
    kinds = {r["kind"] for r in latest_verdicts(conn)}
    assert kinds == {"decision", "exec_intent"}, (
        "the tail must carry the permit as well as the denial, or the page shows a "
        "machine that only ever says no"
    )
    # A follow-up to a verdict is not itself a verdict.
    assert "exec_result" not in kinds


@pytest.mark.parametrize("column", CHAIN_COLUMNS)
def test_every_chain_column_alone_makes_the_chain_unverifiable(
    conn: Connection, config: EngineConfig, column: str
) -> None:
    """Generated over the columns rather than spot-checking one of them."""
    audit_id = _deny_with_budget(conn, config)
    _force_column(conn, audit_id, column, "x" if column != "seq" else 1)
    assert (
        verify_decision(conn, fetch_decision(conn, audit_id)).by_name("chain").status  # type: ignore[arg-type]
        is Status.UNVERIFIABLE
    )
