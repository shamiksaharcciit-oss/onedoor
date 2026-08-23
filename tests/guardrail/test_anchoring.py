"""Merkle anchoring, and the third-party check run on two files (ND-017 / M2–M5).

The test this ticket is really about is
`test_a_third_party_verifies_membership_from_two_files_and_nothing_else`. R039 named it
as the acceptance shape and R040 §4 called it *the nothing-else-of-ours test made
unfakeable*: the verifier runs in a directory containing exactly the published root and
one receipt export. If it ever needs the database, the design has failed R038 §4's
independence metric — and the test would say so by failing, not by looking wrong.
"""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import anchoring, chain, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _policy(conn: Connection) -> None:
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


def _decide(conn: Connection, config: EngineConfig) -> None:
    decide_and_reserve(make_request("demo.plain", {}), conn=conn, config=config, now=FROZEN_NOW)


def _chained(conn: Connection, config: EngineConfig, rows: int = 4) -> None:
    _policy(conn)
    with tx(conn):
        chain.enable(conn)
    for _ in range(rows):
        _decide(conn, config)


def _row(conn: Connection, seq: int):  # type: ignore[no-untyped-def]
    return conn.execute("SELECT * FROM actions_audit WHERE seq=?", (seq,)).fetchone()


def _force(conn: Connection, audit_id: int, column: str, value: object) -> None:
    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute(f"UPDATE actions_audit SET {column}=? WHERE id=?", (value, audit_id))  # noqa: S608
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )


# --- The acceptance shape ----------------------------------------------------------


def test_a_third_party_verifies_membership_from_two_files_and_nothing_else(
    conn: Connection, config: EngineConfig, tmp_path: Path
) -> None:
    """R039's acceptance, R040 §4's *unfakeable*. Two files, a fresh process, no store.

    Run in a subprocess whose working directory holds exactly the anchor and the
    receipt: no database, no repository, nothing of ours but the two artifacts. A
    verifier that needed the store would fail here rather than pass and look fine.
    """
    _chained(conn, config)
    with tx(conn):
        anchor = anchoring.seal(conn, FROZEN_NOW)
    assert anchor is not None

    export = anchoring.receipt_export(conn, _row(conn, 2))
    outdir = tmp_path / "handover"
    outdir.mkdir()
    (outdir / "anchor.json").write_text(json.dumps(anchor.to_object()), encoding="utf-8")
    (outdir / "receipt.json").write_text(json.dumps(export), encoding="utf-8")
    assert sorted(p.name for p in outdir.iterdir()) == ["anchor.json", "receipt.json"], (
        "the acceptance is the ENVIRONMENT: exactly two files, nothing else of ours"
    )

    script = (
        "import json,sys;"
        "from onedoor.guardrail.anchoring import verify_files;"
        "print(verify_files('receipt.json','anchor.json')[0])"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=outdir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "verified", result.stdout + result.stderr


def test_without_the_published_root_it_is_self_consistent_not_verified(
    conn: Connection, config: EngineConfig
) -> None:
    """R040 §3, and the sentence it settles.

    *onedoor never vouches for itself: at the key layer and the anchor layer alike,
    `verified` requires something the store does not hold.* The proof checks against the
    root carried inside the receipt — real information, and not independence.
    """
    _chained(conn, config)
    with tx(conn):
        anchoring.seal(conn, FROZEN_NOW)
    export = anchoring.receipt_export(conn, _row(conn, 1))

    outcome, detail = anchoring.check_membership(export, published_root=None)
    assert outcome == anchoring.MEMBERSHIP_SELF_CONSISTENT
    assert "supply the published root" in detail

    anchored = anchoring.check_membership(export, published_root=export["anchor"]["root"])
    assert anchored[0] == anchoring.MEMBERSHIP_VERIFIED


def test_a_different_published_root_is_unverifiable_not_failed(
    conn: Connection, config: EngineConfig
) -> None:
    """The proof is fine; it is about a different tree. Not the same as a bad proof."""
    _chained(conn, config)
    with tx(conn):
        anchoring.seal(conn, FROZEN_NOW)
    export = anchoring.receipt_export(conn, _row(conn, 1))
    outcome, _ = anchoring.check_membership(export, published_root="f" * 64)
    assert outcome == anchoring.MEMBERSHIP_UNVERIFIABLE


def test_a_tampered_proof_fails(conn: Connection, config: EngineConfig) -> None:
    _chained(conn, config)
    with tx(conn):
        anchoring.seal(conn, FROZEN_NOW)
    export = anchoring.receipt_export(conn, _row(conn, 2))
    export["row_hash"] = "a" * 64
    outcome, _ = anchoring.check_membership(export, published_root=export["anchor"]["root"])
    assert outcome == anchoring.MEMBERSHIP_FAILED


def test_an_unanchored_row_is_absent_and_that_is_normal(
    conn: Connection, config: EngineConfig
) -> None:
    """Anchoring is PERIODIC, so the newest rows are always un-anchored.

    A viewer that showed them red would train an operator to ignore red — which is why
    this is `absent` and the detail says so in the words a reader meets.
    """
    _chained(conn, config)
    export = anchoring.receipt_export(conn, _row(conn, 1))
    outcome, detail = anchoring.check_membership(export, published_root=None)
    assert outcome == anchoring.MEMBERSHIP_ABSENT
    assert "not a fault" in detail


def test_half_a_membership_claim_is_unverifiable(conn: Connection, config: EngineConfig) -> None:
    _chained(conn, config)
    with tx(conn):
        anchoring.seal(conn, FROZEN_NOW)
    export = anchoring.receipt_export(conn, _row(conn, 1))
    export["inclusion"] = None
    assert anchoring.check_membership(export, None)[0] == anchoring.MEMBERSHIP_UNVERIFIABLE


# --- X-8 ---------------------------------------------------------------------------


def test_anchoring_refuses_over_a_broken_chain(conn: Connection, config: EngineConfig) -> None:
    """X-8, and the reason stated where it is enforced.

    An anchor over a broken chain would publish a root that certifies damage,
    permanently and in public. So the verification runs first and a fault anywhere
    refuses the seal.
    """
    _chained(conn, config)
    _force(conn, 2, "detail", "edited")
    with pytest.raises(anchoring.AnchorError, match="refusing to anchor"), tx(conn):
        anchoring.seal(conn, FROZEN_NOW)
    assert conn.execute("SELECT COUNT(*) AS n FROM anchors").fetchone()["n"] == 0


def test_sealing_twice_covers_only_the_new_rows(conn: Connection, config: EngineConfig) -> None:
    """Anchors partition the chain; they do not overlap."""
    _chained(conn, config, rows=3)
    with tx(conn):
        first = anchoring.seal(conn, FROZEN_NOW)
    assert first is not None and (first.first_seq, first.last_seq) == (1, 3)

    with tx(conn):
        assert anchoring.seal(conn, FROZEN_NOW) is None, "nothing new to anchor"

    _decide(conn, config)
    with tx(conn):
        second = anchoring.seal(conn, FROZEN_NOW)
    assert second is not None and (second.first_seq, second.last_seq) == (4, 4)


def test_an_anchor_cannot_be_withdrawn(conn: Connection, config: EngineConfig) -> None:
    """A published root someone can quietly remove is not an anchor."""
    import sqlite3 as sq

    _chained(conn, config)
    with tx(conn):
        anchoring.seal(conn, FROZEN_NOW)
    with pytest.raises(sq.IntegrityError), tx(conn):
        conn.execute("DELETE FROM anchors")
    with pytest.raises(sq.IntegrityError), tx(conn):
        conn.execute("UPDATE anchors SET root='0'")


def test_anchor_ref_is_never_written_and_membership_is_by_range(
    conn: Connection, config: EngineConfig
) -> None:
    """The finding the append-only table forced, kept as a test.

    `anchor_ref` is a column on `actions_audit`; anchoring happens after a row is
    sealed; the no-update trigger forbids `UPDATE`. So the anchor points at the rows,
    not the rows at the anchor — which is also the better shape, since a back-reference
    would be a second answer to a question the range already answers (X-14).
    """
    _chained(conn, config)
    with tx(conn):
        anchoring.seal(conn, FROZEN_NOW)
    assert (
        conn.execute(
            "SELECT COUNT(*) AS n FROM actions_audit WHERE anchor_ref IS NOT NULL"
        ).fetchone()["n"]
        == 0
    )
    assert anchoring.anchor_for(conn, 2) is not None
    assert anchoring.anchor_for(conn, 99) is None


# --- Cadence lives on the anchor ----------------------------------------------------


def test_cadence_is_recorded_on_the_anchor_and_not_in_the_instrument(
    conn: Connection, config: EngineConfig
) -> None:
    """R040 §2. Cadence schedules anchoring, not deciding.

    Recorded here, where a change is visible in exactly the artifact stream it governs.
    Inside `I` it would have re-identified the DECIDING instrument for every row after
    an ops-schedule tweak.
    """
    from onedoor.guardrail import digests

    _policy(conn)
    with tx(conn):
        chain.enable(conn)
        conn.execute(
            "INSERT INTO config (key, value, updated_at) VALUES (?,?,?)",
            (anchoring.CADENCE_KEY, "daily", "2026-07-05T12:00:00Z"),
        )
    _decide(conn, config)
    with tx(conn):
        anchor = anchoring.seal(conn, FROZEN_NOW)
    assert anchor is not None
    assert anchor.to_object()["cadence"] == "daily"
    assert "cadence" not in digests.instrument(_row(conn, 1))


def test_declaring_a_cadence_makes_the_trust_set_anchor_closed(
    conn: Connection, config: EngineConfig
) -> None:
    """`closure` is a declaration about the deployment, known when the row is sealed."""
    from onedoor._vendor.canonical import digest_obj
    from onedoor.guardrail import digests

    _policy(conn)
    with tx(conn):
        chain.enable(conn)
        conn.execute(
            "INSERT INTO config (key, value, updated_at) VALUES (?,?,?)",
            (anchoring.CADENCE_KEY, "hourly", "2026-07-05T12:00:00Z"),
        )
    _decide(conn, config)
    row = _row(conn, 1)
    assert row["t_digest"] == digest_obj(digests.trust(row, closure=digests.ANCHOR_CLOSED))


# --- The digests reach the row -----------------------------------------------------


def test_every_chained_row_carries_its_four_digests(conn: Connection, config: EngineConfig) -> None:
    """They live on an append-only table, so they are written at birth or never."""
    _chained(conn, config, rows=2)
    for row in conn.execute("SELECT * FROM actions_audit WHERE seq IS NOT NULL").fetchall():
        for column in ("e_digest", "i_digest", "t_digest", "v_digest"):
            assert row[column] is not None, f"{column} was not sealed with the row"
            assert len(row[column]) == 64


def test_an_unchained_row_has_no_digests(conn: Connection, config: EngineConfig) -> None:
    """Absent, not empty: before chaining is enabled nothing is sealed."""
    _policy(conn)
    _decide(conn, config)
    row = conn.execute("SELECT * FROM actions_audit ORDER BY id DESC LIMIT 1").fetchone()
    assert row["e_digest"] is None


def test_exporting_an_unchained_row_is_refused(conn: Connection, config: EngineConfig) -> None:
    _policy(conn)
    _decide(conn, config)
    row = conn.execute("SELECT * FROM actions_audit ORDER BY id DESC LIMIT 1").fetchone()
    with pytest.raises(anchoring.AnchorError, match="no membership to prove"):
        anchoring.receipt_export(conn, row)


def test_the_receipt_export_carries_no_request_body(conn: Connection, config: EngineConfig) -> None:
    """The privacy property `E` buys, checked at the artifact that actually travels."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    with tx(conn):
        chain.enable(conn)
    decide_and_reserve(
        make_request("demo.spend", {"iban": "NL91ABNA0417164300"}, cost_eur=Decimal(0)),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    export = anchoring.receipt_export(conn, _row(conn, 1))
    assert "NL91ABNA0417164300" not in json.dumps(export), (
        "a receipt must be handable to a third party without handing over the request body"
    )


# --- F1 (R041): the degenerate empty-path forgery, refused at the front door -------


def _size_one_receipt(conn: Connection, config: EngineConfig) -> dict:
    """A genuine single-row tree — the one shape where an empty path is honest."""
    _chained(conn, config, rows=1)
    with tx(conn):
        anchor = anchoring.seal(conn, FROZEN_NOW)
    assert anchor is not None and anchor.tree_size == 1
    export = anchoring.receipt_export(conn, _row(conn, 1))
    assert export["inclusion"]["path"] == [], "a size-1 tree has no siblings to prove"
    return export


def test_the_honest_single_row_tree_verifies(conn: Connection, config: EngineConfig) -> None:
    """R041's positive vector. The degenerate shape is legitimate in exactly one tree."""
    export = _size_one_receipt(conn, config)
    outcome, _ = anchoring.check_membership(export, published_root=export["anchor"]["root"])
    assert outcome == anchoring.MEMBERSHIP_VERIFIED


def test_sabotage_ep1_empty_path_with_a_larger_claimed_tree(
    conn: Connection, config: EngineConfig
) -> None:
    """S-EP1. Empty path, tree_size rewritten large, root rewritten to the leaf hash.

    With no siblings the proof asserts *the leaf is the root* — true only at size 1. At
    any larger claimed size it is a forgery that checks without a single hash
    computation, which is why the refusal runs before the computation.
    """
    export = _size_one_receipt(conn, config)
    export["inclusion"]["tree_size"] = 8
    export["anchor"]["root"] = export["row_hash"]
    outcome, detail = anchoring.check_membership(export, published_root=export["row_hash"])
    assert outcome == anchoring.MEMBERSHIP_FAILED, (
        "an internally inconsistent artifact is `failed` by definition, not unverifiable"
    )
    assert "size 8" in detail


def test_sabotage_ep2_empty_path_at_a_nonzero_index(conn: Connection, config: EngineConfig) -> None:
    """S-EP2. Empty path, tree_size 1, index rewritten non-zero."""
    export = _size_one_receipt(conn, config)
    export["inclusion"]["index"] = 3
    outcome, detail = anchoring.check_membership(export, published_root=export["anchor"]["root"])
    assert outcome == anchoring.MEMBERSHIP_FAILED
    assert "index 3" in detail


@pytest.mark.parametrize("size", [0, -1, None, "1", 1.0, True])
def test_an_empty_path_with_an_unusable_tree_size_fails(
    conn: Connection, config: EngineConfig, size: object
) -> None:
    """Missing, non-integer and non-positive all land in the same place (R041 §1).

    `True` is in the set on purpose: `bool` subclasses `int`, so a naive
    `isinstance(size, int)` would accept it as the number 1 and let the degenerate claim
    through — the third time that subclass has had to be handled explicitly in this
    repository.
    """
    export = _size_one_receipt(conn, config)
    export["inclusion"]["tree_size"] = size
    outcome, _ = anchoring.check_membership(export, published_root=export["anchor"]["root"])
    assert outcome == anchoring.MEMBERSHIP_FAILED


def test_the_refusal_runs_before_any_merkle_computation(
    conn: Connection, config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R041's law, asserted structurally rather than by reading the source.

    *A verifier must refuse the degenerate case before it computes, because the
    degenerate case is the one that computes to true.* If `verify_inclusion` is ever
    reached with an empty path, this test fails — which is a stronger statement than
    "the outcome was failed", since a guard placed after the computation would produce
    the same outcome and none of the protection.
    """
    export = _size_one_receipt(conn, config)
    export["inclusion"]["tree_size"] = 8

    def must_not_run(*args: object, **kwargs: object) -> bool:  # pragma: no cover
        raise AssertionError("the degenerate path reached the Merkle computation")

    monkeypatch.setattr(anchoring, "verify_inclusion", must_not_run)
    assert anchoring.check_membership(export, None)[0] == anchoring.MEMBERSHIP_FAILED


def test_a_non_empty_path_still_reaches_the_normal_recomputation(
    conn: Connection, config: EngineConfig
) -> None:
    """Both directions: the guard must not swallow ordinary proofs."""
    _chained(conn, config, rows=4)
    with tx(conn):
        anchoring.seal(conn, FROZEN_NOW)
    export = anchoring.receipt_export(conn, _row(conn, 2))
    assert export["inclusion"]["path"], "the fixture must produce a real audit path"
    assert (
        anchoring.check_membership(export, export["anchor"]["root"])[0]
        == anchoring.MEMBERSHIP_VERIFIED
    )


def test_the_vendored_construction_already_refused_both_vectors(
    conn: Connection, config: EngineConfig
) -> None:
    """What delivery measured before adopting the guard — recorded, not assumed.

    Reported to core rather than left implicit: R041 reads as though the path-length
    zero case were open here. Against the vendored RFC 6962 construction it was not,
    for two independent reasons — `verify_inclusion` rejects an `index` outside
    `[0, tree_size)`, and its terminal `sn == 0` check fails an empty path whenever
    `tree_size > 1`. `_leaf_hash`'s `0x00` prefix adds a third: a size-1 root is
    `sha256(0x00 ‖ leaf)` and never the bare leaf digest, so the literal
    "root rewritten to the leaf hash" forgery could not verify at all.

    The guard is adopted regardless, and belongs at our front door — but the record
    should not say a hole was patched when what happened was a line added in depth.
    """
    from onedoor._vendor.canonical import merkle_root, verify_inclusion

    leaf = _size_one_receipt(conn, config)["row_hash"]
    size_one_root = merkle_root([leaf])
    assert size_one_root != leaf, "RFC 6962's leaf prefix means a size-1 root is not the leaf"
    assert not verify_inclusion(leaf, 0, 8, [], leaf), "S-EP1 already failed"
    assert not verify_inclusion(leaf, 0, 8, [], size_one_root), "and so did its stronger form"
    assert not verify_inclusion(leaf, 3, 1, [], size_one_root), "S-EP2 already failed"
    assert verify_inclusion(leaf, 0, 1, [], size_one_root), "the honest size-1 tree verifies"
