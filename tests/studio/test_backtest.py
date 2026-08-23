"""The backtest engine (ND-052 / S1, B1–B5).

Four tests carry this ticket, and R043 §5 named three of them:

- **no rows, no caps** — the real ledger gains nothing and no counter moves;
- **determinism** — the same run twice gives the same receipt digest;
- **the stripped label** — a fixture-backed receipt presented as `live` is caught;
- **the fixture-as-live masquerade** — caught by anyone, from the published chain head.

The fourth is the one that makes the design worth having: *a backtest proves it saw real
data by citation, not by writing; the ledger vouches for the backtest, never the reverse.*
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import chain, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.store.db import tx
from onedoor.studio import backtest, fixture
from tests.conftest import FROZEN_NOW, make_request

CANDIDATE = [
    Policy(
        action_type="demo.spend",
        tier=Tier.AUTO_CAPPED,
        dry_run=False,
        compensating_command="demo.restore",
        caps=Caps(eur_day=Decimal("50")),
        cost_param="amount_eur",
        bounds=Bounds(strict_params=False, required=["amount_eur"]),
    ),
    Policy(
        action_type="demo.restore",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="demo.restore",
        bounds=Bounds(strict_params=False),
    ),
]


def _live(conn: Connection, config: EngineConfig, spends: tuple[str, ...] = ("10", "20")) -> None:
    """A small real ledger: a permissive policy, chained, with real decisions in it."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("10000")),
            cost_param="amount_eur",
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.restore",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    with tx(conn):
        chain.enable(conn)
    for amount in spends:
        decide_and_reserve(
            make_request("demo.spend", {"amount_eur": Decimal(amount)}, cost_eur=Decimal(amount)),
            conn=conn,
            config=config,
            now=FROZEN_NOW,
        )


def _snapshot(conn: Connection) -> tuple[int, list[tuple[object, ...]]]:
    rows = conn.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"]
    caps = [tuple(r) for r in conn.execute("SELECT * FROM cap_counters ORDER BY 1,2,3")]
    return int(rows), caps


# --- B1: the assertion the whole isolation exists for -----------------------------


def test_a_backtest_adds_no_rows_and_moves_no_caps(conn: Connection, config: EngineConfig) -> None:
    """R042 §3, as a test rather than a promise.

    The obvious implementation writes an audit row per replayed action *and reserves
    budget*, because `decide_and_reserve` is check-and-reserve — a replay of yesterday's
    traffic would consume today's caps. It would produce right answers while polluting
    the enforcer's record, which is exactly the failure a test has to catch because
    review will not.
    """
    _live(conn, config)
    before = _snapshot(conn)

    receipt = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)

    assert _snapshot(conn) == before, (
        "the backtest touched the decision ledger: rows or cap counters moved"
    )
    assert receipt.replayed > 0, "the fixture must actually replay something"


def test_the_candidate_never_reaches_the_real_store(conn: Connection, config: EngineConfig) -> None:
    """The scratch store is the isolation, so the live policy set is untouched."""
    _live(conn, config)
    before = conn.execute("SELECT version_hash FROM policy_current WHERE id=1").fetchone()[
        "version_hash"
    ]
    backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    after = conn.execute("SELECT version_hash FROM policy_current WHERE id=1").fetchone()[
        "version_hash"
    ]
    assert before == after, "the candidate policy was written into the live store"


# --- B2: the citation, and determinism --------------------------------------------


def test_the_receipt_cites_the_chain_head(conn: Connection, config: EngineConfig) -> None:
    """The citation is what makes the claim expensive to forge.

    Quoting `row_hash_at_last_seq` means a forged "we tested against production" now
    requires forging the chain — the thing the crypto epic just made hard.
    """
    _live(conn, config)
    head = conn.execute(
        "SELECT row_hash FROM actions_audit WHERE seq IS NOT NULL ORDER BY seq DESC LIMIT 1"
    ).fetchone()["row_hash"]
    receipt = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    assert receipt.cited.row_hash_at_last_seq == head
    assert receipt.sealed()["range"]["row_hash_at_last_seq"] == head


def test_the_same_run_twice_gives_the_same_digest(conn: Connection, config: EngineConfig) -> None:
    """R043 §5's determinism requirement. Re-runs are comparable for free."""
    _live(conn, config)
    first = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    second = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    assert first.digest() == second.digest()
    assert first.sealed() == second.sealed()


def test_a_different_candidate_gives_a_different_digest(
    conn: Connection, config: EngineConfig
) -> None:
    """Both directions: determinism must not be constancy."""
    _live(conn, config)
    tighter = [
        CANDIDATE[0].model_copy(update={"caps": Caps(eur_day=Decimal("5"))}),
        CANDIDATE[1],
    ]
    a = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    b = backtest.run(conn, tighter, config=config, provenance=backtest.LIVE)
    assert a.digest() != b.digest()


def test_the_receipt_is_stored_in_the_studios_own_table(
    conn: Connection, config: EngineConfig
) -> None:
    """Migration `0016`, append-only, and emphatically not `actions_audit`."""
    import sqlite3 as sq

    _live(conn, config)
    receipt = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    before = _snapshot(conn)
    with tx(conn):
        digest = backtest.store(conn, receipt, FROZEN_NOW)
    assert _snapshot(conn) == before, "storing a backtest receipt touched the ledger"
    stored = conn.execute(
        "SELECT * FROM backtest_receipts WHERE backtest_digest=?", (digest,)
    ).fetchone()
    assert stored["ledger_provenance"] == "live"
    assert json.loads(stored["body_json"])["backtest_digest"] == digest

    with pytest.raises(sq.IntegrityError), tx(conn):
        conn.execute("UPDATE backtest_receipts SET ledger_provenance='fixture'")


# --- Q2: the refusal, and the counted prefix --------------------------------------


def test_an_unchained_store_is_refused_not_receipted(
    conn: Connection, config: EngineConfig
) -> None:
    """R043 §2's unasked ruling. A citation-free receipt is the store vouching for itself.

    Chaining is opt-in and off by default, so this is the common case rather than an
    exotic one — and the message names the remedy rather than just refusing.
    """
    policy_loader.upsert(conn, CANDIDATE[1])
    decide_and_reserve(make_request("demo.restore", {}), conn=conn, config=config, now=FROZEN_NOW)
    with pytest.raises(backtest.BacktestRefused) as excinfo:
        backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    message = str(excinfo.value)
    assert "cannot cite" in message
    assert "chain.enable" in message, "a refusal must name the remedy"
    assert "fixture" in message, "and the honest demo path in the meantime"


def test_an_unchained_prefix_is_counted_not_labelled(
    conn: Connection, config: EngineConfig
) -> None:
    """Two labels plus a counted skip beats three labels (R043 §2).

    `ledger_provenance` describes the CITED RANGE, not the store: a range that cannot be
    cited is not replayed, and saying so with a number is clearer than a third word.
    """
    policy_loader.upsert(conn, CANDIDATE[1])
    decide_and_reserve(make_request("demo.restore", {}), conn=conn, config=config, now=FROZEN_NOW)
    _live(conn, config)

    receipt = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    assert receipt.ledger_provenance == "live"
    assert receipt.skipped[backtest.SKIP_UNCHAINED_PREFIX] >= 1


def test_an_unknown_provenance_is_refused() -> None:
    assert backtest.LIVE != backtest.FIXTURE
    with pytest.raises(backtest.BacktestRefused, match="ledger_provenance"):
        backtest.run(None, CANDIDATE, config=None, provenance="probably")  # type: ignore[arg-type]


# --- Q1: measured zero and declared zero never share a representation -------------


def test_a_measured_zero_and_a_missing_cost_param_produce_different_receipts(
    conn: Connection, config: EngineConfig
) -> None:
    """R043 §1's law, asserted as the receipts it governs.

    A cost of `0.00` resolved through the candidate's `cost_param` is a MEASUREMENT and
    participates in cap accounting. An action whose candidate declares no `cost_param` is
    a NON-MEASUREMENT — `caps.resolve_cost` returns None rather than zero, the verdict
    comes back `cost_unknown`, and the receipt counts it under its own named reason.

    Defaulting the second to zero would understate cap denials in the direction of
    reassurance: a backtest reporting "3 sent to approval" when the truth is 30.
    """
    _live(conn, config, spends=("0.00",))

    measured = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.LIVE)
    assert backtest.SKIP_COST_UNDERIVABLE not in measured.skipped

    no_cost_param = [
        CANDIDATE[0].model_copy(update={"cost_param": None, "bounds": Bounds(strict_params=False)}),
        CANDIDATE[1],
    ]
    declared = backtest.run(conn, no_cost_param, config=config, provenance=backtest.LIVE)
    assert declared.skipped[backtest.SKIP_COST_UNDERIVABLE] >= 1
    assert measured.digest() != declared.digest(), (
        "measured zero and declared zero produced the same receipt"
    )


def test_the_candidates_cost_param_applies_not_the_sealed_policys(
    conn: Connection, config: EngineConfig
) -> None:
    """R043 §1's boundary: the backtest asks what the CANDIDATE would have done.

    The candidate includes its own cost declaration, even where it differs from the
    policy in force when the row was sealed. Not a bug — the question being answered.
    """
    _live(conn, config, spends=("40",))
    tighter = [
        CANDIDATE[0].model_copy(update={"caps": Caps(eur_day=Decimal("5"))}),
        CANDIDATE[1],
    ]
    receipt = backtest.run(conn, tighter, config=config, provenance=backtest.LIVE)
    assert receipt.divergence.denied >= 1, (
        "a 40-euro spend under a 5-euro cap must show as a denial the candidate causes"
    )
    assert receipt.divergence.flips, "and the flip must be counted"


# --- B3: the fixture ledger ---------------------------------------------------------


def test_the_fixture_ledger_is_mechanically_real(tmp_path: Path) -> None:
    """Chained, verifiable, sealable — because the real engine produced every row."""
    from onedoor.guardrail import anchoring
    from onedoor.guardrail.receipt import Status, verify_decision

    path = tmp_path / "demo.db"
    fixture.build(path)
    from onedoor.store.db import Database

    conn = Database(str(path)).connect()
    try:
        report = chain.verify_chain(conn)
        assert report.sound, [r.detail for r in report.broken]
        assert report.chained_rows > 50, "the demo needs enough traffic to say something"

        row = conn.execute(
            "SELECT * FROM actions_audit WHERE seq IS NOT NULL ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        verification = verify_decision(conn, row)
        assert verification.by_name("chain").status is Status.VERIFIED
        with tx(conn):
            assert anchoring.seal(conn, FROZEN_NOW) is not None, "it must be anchorable"
    finally:
        conn.close()


def test_the_fixture_ledger_regenerates_to_the_committed_head(tmp_path: Path) -> None:
    """The pinning test — and it pins what is actually deterministic.

    Measured rather than assumed: two builds produce an identical `actions_audit` and a
    DIFFERENT file, because the engine samples the clock for `schema_migrations`,
    `policy_versions` and the config stamps. None of those is an input this generator
    can pin, so the committed artifact is the chain head rather than the database.

    That is also the artifact the anti-masquerade check needs, so nothing is lost.
    """
    from onedoor.store.db import Database

    first_head = fixture.build(tmp_path / "a.db")
    second_head = fixture.build(tmp_path / "b.db")
    assert first_head == second_head == fixture.published_head(), (
        "the fixture drifted from its committed HEAD — regenerate with "
        "`python -m onedoor.studio.fixture`"
    )

    rows = []
    for name in ("a.db", "b.db"):
        conn = Database(str(tmp_path / name)).connect()
        try:
            rows.append([tuple(r) for r in conn.execute("SELECT * FROM actions_audit ORDER BY id")])
        finally:
            conn.close()
    assert rows[0] == rows[1], "the LEDGER must be identical even though the file is not"


def test_the_committed_fixture_artifact_is_the_head_not_the_database() -> None:
    """A committed `.db` measured 315 KB, over the 256 KB the ticket declared."""
    assert fixture.HEAD_FILE.is_file()
    assert len(fixture.published_head() or "") == 64
    assert fixture.HEAD_FILE.stat().st_size < 1024


def test_a_backtest_over_the_fixture_is_labelled_fixture(config: EngineConfig) -> None:
    conn = fixture.open_fixture()
    try:
        receipt = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.FIXTURE)
        assert receipt.ledger_provenance == "fixture"
        assert receipt.sealed()["ledger_provenance"] == "fixture"
    finally:
        conn.close()


# --- B5: the two mandatory sabotages ----------------------------------------------


def test_sabotage_the_stripped_label_changes_the_digest(config: EngineConfig) -> None:
    """R043 §5's first sabotage. The label is hashed, so removing it is detectable.

    *A fixture-backed number presented without its label is the overclaim this programme
    exists to make impossible.* Because `ledger_provenance` is inside the digest, a
    receipt relabelled `live` no longer matches its own `backtest_digest` — the forgery
    is caught by arithmetic rather than by a reviewer noticing.
    """
    conn = fixture.open_fixture()
    try:
        receipt = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.FIXTURE)
    finally:
        conn.close()

    sealed = receipt.sealed()
    forged = {**sealed, "ledger_provenance": "live"}
    assert forged["backtest_digest"] == sealed["backtest_digest"], "the forger keeps the old digest"

    from onedoor._vendor.canonical import digest_obj

    body = {k: v for k, v in forged.items() if k != "backtest_digest"}
    assert digest_obj(body) != forged["backtest_digest"], (
        "relabelling a receipt must break its own digest"
    )


def test_sabotage_a_fixture_receipt_claiming_live_is_detected(config: EngineConfig) -> None:
    """R043 §3's masquerade check, and the property the pinning buys.

    The fixture's chain head is a **published constant** — every install ships the same
    generator and the same HEAD — so a receipt citing it while claiming `live` is
    checkable **by anyone**, without access to the deployment. That is a stronger
    guarantee than any rendering test: B5's label tests guard our screens, this guards
    the world outside them.
    """
    conn = fixture.open_fixture()
    try:
        receipt = backtest.run(conn, CANDIDATE, config=config, provenance=backtest.FIXTURE)
    finally:
        conn.close()

    forged = {**receipt.sealed(), "ledger_provenance": "live"}
    assert backtest_claims_fixture_data(forged), (
        "a receipt citing the published fixture head while claiming live went undetected"
    )

    # And the check must not fire on a genuine live receipt.
    assert not backtest_claims_fixture_data(
        {
            **receipt.sealed(),
            "range": {**receipt.sealed()["range"], "row_hash_at_last_seq": "0" * 64},
        }
    )


def backtest_claims_fixture_data(sealed: dict) -> bool:
    """Does this receipt cite the shipped fixture while claiming to be live?

    Deliberately a plain function over the receipt object: anyone holding a published
    receipt and the shipped `HEAD` can run this reasoning, which is the point.
    """
    head = fixture.published_head()
    if head is None:  # pragma: no cover - only in a tree with no generated HEAD
        return False
    return (
        sealed.get("ledger_provenance") == backtest.LIVE
        and sealed.get("range", {}).get("row_hash_at_last_seq") == head
    )


def test_the_masquerade_check_is_available_to_a_third_party() -> None:
    """It needs the receipt and the shipped constant. No store, no deployment."""
    assert fixture.published_head() is not None
    assert backtest_claims_fixture_data(
        {"ledger_provenance": "live", "range": {"row_hash_at_last_seq": fixture.published_head()}}
    )
    assert not backtest_claims_fixture_data(
        {
            "ledger_provenance": "fixture",
            "range": {"row_hash_at_last_seq": fixture.published_head()},
        }
    )


def test_the_pinned_head_file_has_no_carriage_return() -> None:
    """A pinned constant must not be rewritten by a platform default.

    `write_text` translates `\n` to CRLF on Windows, so the committed HEAD and a
    locally regenerated one differed by a byte — the file would show as modified after
    every regeneration on one platform and not another, in the one file whose whole job
    is to be stable. Caught by git's own CRLF warning, which is the third layer
    `.gitattributes` exists to provide and the first one that actually fired here.
    """
    raw = fixture.HEAD_FILE.read_bytes()
    assert b"\r" not in raw, "the pinned head was written with a platform newline"
    assert raw.decode("ascii").strip() == fixture.published_head()
