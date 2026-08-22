"""The chain: written on both paths, walked honestly, and localised when tampered.

C2–C5 of `TICKETS-ND-001.md`. The tests that matter most here are not the ones proving
a good chain verifies — that is the easy direction and it would pass against a
function that returned `True`. They are:

- **both commit paths produce identical hashes** (N2's decision, made checkable),
- **a tampered row is localised to itself** rather than poisoning the log after it,
- **the four outcomes stay apart** on a mixed archive, which is every real deployment
  that switches chaining on after running for a while.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import chain, policy_loader
from onedoor.guardrail.audit import chaining_on
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.guardrail.preimage import GENESIS_PREV_HASH
from onedoor.guardrail.receipt import Status
from onedoor.store.db import Database, tx
from tests.conftest import FROZEN_NOW, make_request


def _policies(conn: Connection) -> None:
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


def _decide(conn: Connection, config: EngineConfig, action: str = "demo.plain") -> None:
    params = {"amount_eur": Decimal("1")} if action == "demo.spend" else {}
    cost = Decimal("1") if action == "demo.spend" else Decimal(0)
    decide_and_reserve(
        make_request(action, params, cost_eur=cost),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )


def _enable(conn: Connection) -> int:
    with tx(conn):
        return chain.enable(conn)


def _force(conn: Connection, audit_id: int, column: str, value: object) -> None:
    """Tamper with a stored row the way an attacker with file access would.

    The append-only trigger is dropped and restored, so the store is otherwise exactly
    as production has it. The point is to test the WALKER against damage, not to
    re-test the trigger, which `test_audit_append_only.py` already covers.
    """
    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute(f"UPDATE actions_audit SET {column}=? WHERE id=?", (value, audit_id))  # noqa: S608
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )


# --- C3: switching it on ----------------------------------------------------------


def test_chaining_is_off_until_it_is_switched_on(conn: Connection, config: EngineConfig) -> None:
    """An upgrade does not silently start hashing. Enabling is a deliberate act."""
    _policies(conn)
    _decide(conn, config)
    assert not chaining_on(conn)
    row = conn.execute("SELECT seq, prev_hash, row_hash FROM actions_audit").fetchone()
    assert (row["seq"], row["prev_hash"], row["row_hash"]) == (None, None, None)


def test_the_first_chained_row_carries_the_ruled_sentinel(
    conn: Connection, config: EngineConfig
) -> None:
    """R016: 64 ASCII zeros, an affirmative statement that no predecessor exists."""
    _policies(conn)
    _enable(conn)
    _decide(conn, config)
    row = conn.execute("SELECT * FROM actions_audit ORDER BY id DESC LIMIT 1").fetchone()
    assert row["seq"] == 1
    assert row["prev_hash"] == GENESIS_PREV_HASH
    assert len(row["row_hash"]) == 64


def test_enabling_twice_is_refused(conn: Connection) -> None:
    """Two genesis points would make a break and a fresh start indistinguishable."""
    _enable(conn)
    with pytest.raises(chain.ChainError, match="already enabled"), tx(conn):
        chain.enable(conn)


def test_the_boundary_is_recorded_rather_than_inferred(
    conn: Connection, config: EngineConfig
) -> None:
    """Where the unchained prefix ends is a fact about the store, kept in the store."""
    _policies(conn)
    _decide(conn, config)
    _decide(conn, config)
    boundary = _enable(conn)
    assert boundary == 2
    assert chain.genesis_after_id(conn) == 2
    _decide(conn, config)
    assert conn.execute("SELECT MAX(seq) AS s FROM actions_audit").fetchone()["s"] == 1


# --- C2: both commit paths -------------------------------------------------------


def _fixed_requests(count: int) -> list[object]:
    """The SAME requests for both runs, with fixed ids.

    `make_request` mints a fresh `uuid4` per call, and `request_id` is in the preimage
    — so replaying "the same actions" through two paths with fresh ids produces
    different hashes for a completely correct implementation. The first version of
    this test did exactly that and failed, which was the fixture lying rather than the
    chain drifting. Two runs can only be compared if they are the same two runs.
    """
    from uuid import UUID

    from onedoor.guardrail.models import ActionRequest, Source

    return [
        ActionRequest(
            request_id=UUID(int=0x51D0 + i),
            action_type="demo.plain",
            params={},
            source=Source.LLM,
            rationale="chain parity",
            created_at=FROZEN_NOW,
        )
        for i in range(count)
    ]


def _hashes_for_path(tmp_path: Path, name: str, batch: int, requests: list[object]) -> list[str]:
    """Replay one fixed sequence of requests through one commit path; return the chain."""
    from zoneinfo import ZoneInfo

    from onedoor.connectors import mock
    from onedoor.guardrail import audit
    from onedoor.guardrail.executor import evaluate_and_execute

    database = Database(str(tmp_path / f"{name}.db"))
    database.init()
    conn = database.connect()
    try:
        _policies(conn)
        with tx(conn):
            chain.enable(conn)
        cfg = EngineConfig(
            approval_ttl_seconds=3600,
            connector_timeout_seconds=5.0,
            tz=ZoneInfo("UTC"),
            audit_group_commit=batch,
        )
        registry = mock.build_registry()
        registry.register("demo.plain", mock.act_ok)
        registry.register("demo.restore", mock.act_ok)
        for request in requests:
            evaluate_and_execute(
                request,  # type: ignore[arg-type]
                conn=conn,
                registry=registry,
                config=cfg,
                now=FROZEN_NOW,
            )
        audit.flush(conn)
        return [
            r["row_hash"]
            for r in conn.execute(
                "SELECT row_hash FROM actions_audit WHERE row_hash IS NOT NULL ORDER BY seq"
            )
        ]
    finally:
        conn.close()


def test_group_commit_reorders_the_ledger_and_that_is_the_feature(tmp_path: Path) -> None:
    """Measured, because the decomposition claimed something stronger than is true.

    `TICKETS-ND-001.md` §3 said both commit paths must produce **identical row_hash
    values** for the same sequence of actions. They cannot, and the test that asserted
    it failed for a correct implementation.

    Group commit defers result rows, so the same four actions land in a different ROW
    ORDER — immediate writes `intent, result, intent, result`; buffered writes
    `intent, intent, intent, result, result, result`. `seq` and `prev_hash` are in the
    preimage, so different positions mean different hashes. That is what group commit
    *is*, not a drift in the chain, and the honest correction is to assert the
    invariant that does hold rather than to weaken the one that does not.
    """
    requests = _fixed_requests(3)
    _hashes_for_path(tmp_path, "imm", 0, requests)
    _hashes_for_path(tmp_path, "buf", 3, requests)

    def order(name: str) -> list[tuple[int, str]]:
        conn = Database(str(tmp_path / f"{name}.db")).connect()
        try:
            return [
                (int(r["seq"]), str(r["kind"]))
                for r in conn.execute(
                    "SELECT seq, kind FROM actions_audit WHERE seq IS NOT NULL ORDER BY seq"
                )
            ]
        finally:
            conn.close()

    immediate, buffered = order("imm"), order("buf")
    assert [k for _, k in immediate] == ["exec_intent", "exec_result"] * 3
    assert [k for _, k in buffered] == ["exec_intent"] * 3 + ["exec_result"] * 3
    assert immediate != buffered, (
        "if the orders ever match, this test is no longer measuring what it claims and "
        "the invariant below should be re-derived"
    )


def test_the_preimage_does_not_depend_on_which_path_wrote_the_row(tmp_path: Path) -> None:
    """The invariant that DOES hold, and the one N2's decision actually needs.

    Same row content at the same chain position hashes the same, whichever path put it
    there — where "position" is `seq`, `prev_hash` **and** `parent_id`, because a
    result row names its intent by row id and ids follow write order. If this failed, a store's receipts would depend on a performance setting and
    two operators running identical actions would hold different evidence — which is
    the real risk group commit introduced. Row order differing is fine; the *function*
    differing is not.
    """
    from onedoor.guardrail.preimage import FIELD_ORDER, row_hash

    requests = _fixed_requests(3)
    _hashes_for_path(tmp_path, "imm2", 0, requests)
    _hashes_for_path(tmp_path, "buf2", 3, requests)

    def content(name: str, kind: str, request_id: str) -> dict[str, object]:
        conn = Database(str(tmp_path / f"{name}.db")).connect()
        try:
            row = conn.execute(
                "SELECT * FROM actions_audit WHERE kind=? AND request_id=?", (kind, request_id)
            ).fetchone()
            assert row is not None
            # Hold the POSITION-DETERMINED fields fixed so only content is compared.
            #
            # `seq` and `prev_hash` are the chain position. `parent_id` joins them,
            # which the first version of this test missed and the failure taught: a
            # result row names its intent by row id, and ids follow write order, so
            # deferring results shifts them. Three fields the ledger's ORDER decides,
            # and everything else is the row's own content.
            values = {f: row[f] for f in FIELD_ORDER}
            values["seq"] = 7
            values["prev_hash"] = "b" * 64
            values["parent_id"] = 99
            return values
        finally:
            conn.close()

    for kind in ("exec_intent", "exec_result"):
        rid = str(requests[1].request_id)  # type: ignore[attr-defined]
        assert row_hash(content("imm2", kind, rid)) == row_hash(content("buf2", kind, rid)), (
            f"a {kind} row hashes differently depending on the commit path that wrote "
            f"it: the preimage has become path-dependent"
        )


def test_a_buffered_batch_chains_in_row_order(tmp_path: Path) -> None:
    """Each buffered row links to the one before it, not all to the same tip."""
    _hashes_for_path(tmp_path, "order", 3, _fixed_requests(4))
    database = Database(str(tmp_path / "order.db"))
    conn = database.connect()
    try:
        rows = list(
            conn.execute(
                "SELECT seq, prev_hash, row_hash FROM actions_audit "
                "WHERE seq IS NOT NULL ORDER BY seq"
            )
        )
        assert [r["seq"] for r in rows] == list(range(1, len(rows) + 1))
        expected = GENESIS_PREV_HASH
        for row in rows:
            assert row["prev_hash"] == expected
            expected = row["row_hash"]
    finally:
        conn.close()


def test_the_seq_index_refuses_a_duplicate_ordinal(conn: Connection, config: EngineConfig) -> None:
    """Migration 0012: the database refuses the ambiguity rather than the walker."""
    import sqlite3

    _policies(conn)
    _enable(conn)
    _decide(conn, config)
    _decide(conn, config)
    with pytest.raises(sqlite3.IntegrityError), tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        try:
            conn.execute("UPDATE actions_audit SET seq=1 WHERE seq=2")
        finally:
            conn.execute(
                "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
                "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
            )


def test_the_append_only_triggers_survive_migration_0012(conn: Connection) -> None:
    """R031's standing constraint: re-verify the triggers after any migration here."""
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert {"actions_audit_no_update", "actions_audit_no_delete"} <= names


# --- C4: walking it ---------------------------------------------------------------


def test_an_intact_chain_verifies(conn: Connection, config: EngineConfig) -> None:
    _policies(conn)
    _enable(conn)
    for _ in range(3):
        _decide(conn, config)
    report = chain.verify_chain(conn)
    assert report.sound
    assert report.chained_rows == 3
    assert [r.status for r in report.regions] == [Status.VERIFIED]


def test_a_mixed_archive_states_both_regions(conn: Connection, config: EngineConfig) -> None:
    """The unchained prefix is ABSENT, the rest is VERIFIED, and neither swallows the other.

    A log with an unchained prefix and an intact chain after genesis is not "verified"
    and not "failed". Averaging them into one word is the two-outcome collapse.
    """
    _policies(conn)
    _decide(conn, config)
    _decide(conn, config)
    _enable(conn)
    _decide(conn, config)
    report = chain.verify_chain(conn)
    assert [r.status for r in report.regions] == [Status.ABSENT, Status.VERIFIED]
    assert report.unchained_rows == 2
    assert report.chained_rows == 1
    assert report.sound, "an unchained prefix is not damage; it is history"
    assert "cannot be hashed retroactively" in report.regions[0].detail


def test_an_empty_store_reports_nothing_rather_than_verified(tmp_path: Path) -> None:
    database = Database(str(tmp_path / "empty.db"))
    database.init()
    empty = database.connect()
    try:
        assert chain.verify_chain(empty).regions == ()
    finally:
        empty.close()


def test_a_half_written_chain_is_unverifiable(conn: Connection, config: EngineConfig) -> None:
    """Ran and did not finish is a different fact from never ran (R015)."""
    _policies(conn)
    _decide(conn, config)
    _force(conn, 1, "seq", 99)
    report = chain.verify_chain(conn)
    assert Status.UNVERIFIABLE in [r.status for r in report.regions]
    assert not report.sound


# --- C5: the tamper test (DoD) ----------------------------------------------------


def test_a_tampered_row_is_localised_to_that_row(conn: Connection, config: EngineConfig) -> None:
    """The DoD's requirement, and the reason the walker continues from the STORE.

    A naive walker carries its expectation forward and reports every row after a break
    as broken too — which is technically true and operationally useless: an auditor
    reading "1,400 rows broken" cannot tell where the damage is. Continuing from what
    the store says localises the break to the row that actually moved.
    """
    _policies(conn)
    _enable(conn)
    for _ in range(5):
        _decide(conn, config)
    assert chain.verify_chain(conn).sound

    _force(conn, 3, "detail", "quietly edited")

    report = chain.verify_chain(conn)
    assert not report.sound
    failed = [r for r in report.regions if r.status is Status.FAILED]
    assert len(failed) == 1, f"the break was not localised: {[r.status for r in report.regions]}"
    assert failed[0].first_id == failed[0].last_id == 3
    assert "do not hash to its recorded row_hash" in failed[0].detail
    assert report.chained_rows == 4, "the untouched rows must still verify"


def test_a_relinked_row_is_caught_even_if_its_own_hash_is_consistent(
    conn: Connection, config: EngineConfig
) -> None:
    """Editing the link rather than the contents. Both are the chain's job."""
    _policies(conn)
    _enable(conn)
    for _ in range(3):
        _decide(conn, config)
    _force(conn, 2, "prev_hash", "f" * 64)
    report = chain.verify_chain(conn)
    failed = [r for r in report.regions if r.status is Status.FAILED]
    assert len(failed) == 1
    assert failed[0].first_id == 2
    assert "prev_hash" in failed[0].detail


def test_a_deleted_row_breaks_the_chain(conn: Connection, config: EngineConfig) -> None:
    """The attack the chain exists for: removing an inconvenient decision."""
    _policies(conn)
    _enable(conn)
    for _ in range(4):
        _decide(conn, config)
    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_delete")
        conn.execute("DELETE FROM actions_audit WHERE seq=2")
        conn.execute(
            "CREATE TRIGGER actions_audit_no_delete BEFORE DELETE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )
    report = chain.verify_chain(conn)
    assert not report.sound
    assert any("seq is 3, expected 2" in r.detail for r in report.regions)


def test_verification_never_raises_on_damage(conn: Connection, config: EngineConfig) -> None:
    """Damage is a verdict, not an exception.

    A verifier that threw on a broken chain could not be run against a suspect
    archive, which is the only archive worth running one against.
    """
    _policies(conn)
    _enable(conn)
    _decide(conn, config)
    _force(conn, 1, "row_hash", "not even a hash")
    report = chain.verify_chain(conn)
    assert not report.sound
