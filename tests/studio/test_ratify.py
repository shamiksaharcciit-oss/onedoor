"""The ratification ceremony (ND-052 / S2, T1–T5).

R045 §6 named the standing this suite has to produce:

- **the equality test green, with its merged-set sabotage** — the previewed hash equals
  the hash ratification then produces, and seeding the scratch store with only the
  changed rules makes that equality fail;
- **the lost-race test green** — a ratification whose diff was read from a version that
  has since moved refuses, loudly, and writes nothing;
- **the citation-mismatch refusal green** — a cited backtest that does not resolve, and
  one that tested a different candidate, are refused under **different** named reasons.

The rendering disciplines are held next door, in `tests/viewer/test_ratification.py`,
because they are properties of the views rather than of the ceremony.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import chain, killswitch, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, EffectPolicy, Policy, Tier
from onedoor.store.db import tx
from onedoor.studio import backtest, ratify
from tests.conftest import FROZEN_NOW, make_request

SESSION = "operator-1"


def _policy(action: str, cap: str = "500", tier: Tier = Tier.AUTO_CAPPED) -> Policy:
    return Policy(
        action_type=action,
        tier=tier,
        dry_run=False,
        compensating_command="demo.restore",
        caps=Caps(eur_day=Decimal(cap)),
        cost_param="amount_eur",
        bounds=Bounds(strict_params=False, required=["amount_eur"]),
    )


def _restore() -> Policy:
    return Policy(
        action_type="demo.restore",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="demo.restore",
        bounds=Bounds(strict_params=False),
    )


def _in_force(conn: Connection, *policies: Policy) -> str:
    for item in policies:
        policy_loader.upsert(conn, item)
    version = policy_loader.current_version(conn)
    assert version is not None
    return version


# --- T1: the diff is of meaning, not of spelling ----------------------------------


def test_a_rewritten_bound_with_the_same_value_is_not_a_change() -> None:
    """`500` and `500.00` are one rule. E8's canonical renderer, arriving in the diff."""
    before = [_policy("demo.spend", cap="500")]
    after = [_policy("demo.spend", cap="500.00")]
    assert ratify.diff(before, after) == ratify.Changes(added=[], modified=[])


def test_a_changed_cap_is_a_modification_and_a_new_action_is_an_addition() -> None:
    before = [_policy("demo.spend", cap="500")]
    after = [_policy("demo.spend", cap="250"), _policy("demo.refund")]
    changes = ratify.diff(before, after)
    assert changes.modified == ["demo.spend"]
    assert changes.added == ["demo.refund"]
    assert not changes.is_empty


def test_an_omitted_action_is_not_reported_as_removed() -> None:
    """The ceremony cannot retire a rule, so it never claims to have.

    `upsert` has no delete and the candidate merges over the active set, so an omitted
    action type stays exactly as it was. `Changes` therefore has no `removed` field at
    all — *a field that can never be non-empty is a promise nothing keeps* — and this
    test pins the absence so a future reader does not add one back by reflex.
    """
    assert not hasattr(ratify.Changes(added=[], modified=[]), "removed")
    assert "removed" not in ratify.Changes(added=["a"], modified=[]).to_object()


# --- T2: the equality that is the ticket's central claim --------------------------


def test_the_previewed_hash_is_the_hash_ratification_produces(conn: Connection) -> None:
    """R045 §6's first requirement. The number shown IS the number that lands."""
    expected = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    candidate = [_policy("demo.spend", cap="250")]

    shown = ratify.preview(conn, candidate)
    assert shown.from_version == expected
    assert shown.changes.modified == ["demo.spend"]

    receipt = ratify.ratify(
        conn,
        candidate,
        expected_version=expected,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    assert receipt.to_version == shown.to_version, (
        "the previewed hash and the produced hash disagree — the preview is a promise "
        "the store did not keep"
    )
    assert policy_loader.current_version(conn) == shown.to_version


def test_sabotage_a_scratch_store_seeded_with_only_the_changed_rules(conn: Connection) -> None:
    """R045 §2's sabotage. The trap, pinned permanently.

    `_normalized_snapshot` renders the WHOLE policy table, so a scratch store holding
    only the changed rules yields the hash of a two-rule deployment — *a different
    number wearing the right label*. It looks right, it is stable, and it is wrong.
    """
    expected = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    candidate = [_policy("demo.spend", cap="250")]

    honest = ratify.preview(conn, candidate)
    sabotaged = ratify.preview(conn, candidate, seed_active=False)
    assert sabotaged.to_version != honest.to_version, (
        "seeding the scratch store with only the changed rules produced the same hash — "
        "the merge is not actually being done"
    )

    receipt = ratify.ratify(
        conn,
        candidate,
        expected_version=expected,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    assert receipt.to_version == honest.to_version
    assert receipt.to_version != sabotaged.to_version


# --- R088 §1/§2 (F-U1): a candidate the loader would refuse does not crash the preview -


def test_a_candidate_the_loader_would_refuse_returns_a_refusal_not_a_raise(
    conn: Connection,
) -> None:
    """The traceback in R088 §1, reproduced directly against `ratify.preview`.

    Tier 2 with no `compensating_command` is exactly what
    `policy_loader.validate_policy` raises `ValueError` over — previously that raise
    climbed straight out of `preview`, uncaught, into whatever called it. Now it is
    caught at the boundary `preview` owns, and the answer is a value, not an exception.
    `_apply` is not mocked, stubbed, or bypassed here: the same function still runs and
    still refuses; only who catches the refusal changed.
    """
    expected = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    candidate = [Policy(action_type="payments.transfer", tier=Tier.AUTO_CAPPED, dry_run=False)]

    shown = ratify.preview(conn, candidate)
    assert shown.to_version is None
    assert shown.refusal is not None
    assert "compensating_command" in shown.refusal
    assert "payments.transfer" in shown.refusal
    # The active store is untouched — a caught refusal is not a silent write.
    assert policy_loader.current_version(conn) == expected


def test_a_refused_previews_changes_and_digest_still_compute(conn: Connection) -> None:
    """Only `to_version` needs `_apply` to succeed — `changes`, `effect_changes` and
    `candidate_digest` are pure comparisons against the candidate as given, so a refused
    draft still shows what it would have changed, even though it cannot say what it
    would have become (R088 §2's own reasoning, held as a test rather than a comment)."""
    _in_force(conn, _restore())
    candidate = [Policy(action_type="payments.transfer", tier=Tier.AUTO_CAPPED, dry_run=False)]

    shown = ratify.preview(conn, candidate)
    assert shown.refusal is not None
    assert shown.changes.added == ["payments.transfer"]
    assert shown.candidate_digest == backtest.policy_digest(candidate)


def test_a_clean_candidate_carries_no_refusal(conn: Connection) -> None:
    """The success path is unchanged in shape — `refusal` is `None`, `to_version` is a
    real hash — so this is the boundary the two tests above test the OTHER side of."""
    _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    shown = ratify.preview(conn, [_policy("demo.spend", cap="250")])
    assert shown.refusal is None
    assert shown.to_version is not None


def test_the_real_ratification_still_refuses_the_identical_candidate(
    conn: Connection,
) -> None:
    """R088 §2's constraint, held as a test: preview and ratification must not diverge.
    `_apply` is untouched and shared — `ratify.ratify` still raises on this candidate
    exactly as it always did; only `preview` learned to catch it. Confirms the fix did
    not make the ceremony permissive by accident."""
    expected = _in_force(conn, _restore())
    candidate = [Policy(action_type="payments.transfer", tier=Tier.AUTO_CAPPED, dry_run=False)]
    assert ratify.preview(conn, candidate).refusal is not None

    with pytest.raises(ValueError, match="compensating_command"):
        ratify.ratify(
            conn,
            candidate,
            expected_version=expected,
            ratified_by_session=SESSION,
            now=FROZEN_NOW,
        )


def test_the_preview_writes_nothing_to_the_real_store(conn: Connection) -> None:
    """A preview is a question, not a change. Asked before it is answered."""
    expected = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    versions = conn.execute("SELECT COUNT(*) AS n FROM policy_versions").fetchone()["n"]

    ratify.preview(conn, [_policy("demo.spend", cap="250")])

    assert policy_loader.current_version(conn) == expected
    assert conn.execute("SELECT COUNT(*) AS n FROM policy_versions").fetchone()["n"] == versions
    assert conn.execute("SELECT COUNT(*) AS n FROM ratifications").fetchone()["n"] == 0


def test_the_first_ratification_on_a_fresh_store_has_an_absent_from_version(
    fresh: Connection,
) -> None:
    """Absent, not empty (R015). And `expected_version=None` is a real answer."""
    shown = ratify.preview(fresh, [_policy("demo.spend"), _restore()])
    assert shown.from_version is None

    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    assert receipt.from_version is None
    assert receipt.sealed()["from_version"] is None
    assert receipt.to_version == shown.to_version


# --- T3: the compare-and-swap -----------------------------------------------------


def test_a_lost_race_refuses_loudly_and_writes_nothing(conn: Connection) -> None:
    """R045 §6's second requirement. A UI has a gap between reading and clicking."""
    stale = _in_force(conn, _policy("demo.spend", cap="500"), _restore())

    # Another operator ratifies in the gap.
    moved = _in_force(conn, _policy("demo.spend", cap="400"))
    assert moved != stale

    with pytest.raises(ratify.RatificationRefused) as caught:
        ratify.ratify(
            conn,
            [_policy("demo.spend", cap="250")],
            expected_version=stale,
            ratified_by_session=SESSION,
            now=FROZEN_NOW,
        )
    assert caught.value.reason == ratify.REFUSED_LOST_RACE
    assert policy_loader.current_version(conn) == moved, "a lost race must not silently write"
    assert conn.execute("SELECT COUNT(*) AS n FROM ratifications").fetchone()["n"] == 0


def test_the_refusal_never_retries_on_the_operators_behalf(conn: Connection) -> None:
    """It refuses; it does not helpfully re-diff and proceed.

    The failure mode a retry would create is precisely the one CAS exists to stop: the
    operator signs a diff they read, and a retry substitutes a diff they did not.
    """
    stale = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    moved = _in_force(conn, _policy("demo.spend", cap="400"))

    with pytest.raises(ratify.RatificationRefused):
        ratify.ratify(
            conn,
            [_policy("demo.spend", cap="250")],
            expected_version=stale,
            ratified_by_session=SESSION,
            now=FROZEN_NOW,
        )
    row = conn.execute("SELECT caps_json FROM policies WHERE action_type='demo.spend'").fetchone()
    assert json.loads(row["caps_json"])["eur_day"] == "400", (
        "the refused candidate reached the store anyway"
    )
    assert policy_loader.current_version(conn) == moved


def test_a_fresh_store_with_a_claimed_previous_version_is_a_lost_race(fresh: Connection) -> None:
    """`None` and "some hash" are different claims, and only one of them is true here."""
    with pytest.raises(ratify.RatificationRefused) as caught:
        ratify.ratify(
            fresh,
            [_policy("demo.spend"), _restore()],
            expected_version="0" * 64,
            ratified_by_session=SESSION,
            now=FROZEN_NOW,
        )
    assert caught.value.reason == ratify.REFUSED_LOST_RACE
    assert "no recorded version" in str(caught.value)


# --- T4: the citation is checked, and the receipt is sealed -----------------------


def _stored_backtest(conn: Connection, config: EngineConfig, candidate: list[Policy]) -> str:
    """Run a real backtest over a chained store with real decisions in it.

    `chain.enable` alone is not enough: a backtest cites the sealed chain, and a store
    with an enabled chain but no decisions has nothing to cite — which `backtest.run`
    refuses rather than receipting (R043 §2).
    """
    with tx(conn):
        chain.enable(conn)
    for amount in ("10", "20"):
        decide_and_reserve(
            make_request("demo.spend", {"amount_eur": Decimal(amount)}, cost_eur=Decimal(amount)),
            conn=conn,
            config=config,
            now=FROZEN_NOW,
        )
    receipt = backtest.run(conn, candidate, config=config, provenance=backtest.LIVE)
    return backtest.store(conn, receipt, FROZEN_NOW)


def test_an_unresolvable_citation_is_refused_under_its_own_reason(conn: Connection) -> None:
    """R010 in the ceremony: a citation this store cannot check is not evidence."""
    expected = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    with pytest.raises(ratify.RatificationRefused) as caught:
        ratify.ratify(
            conn,
            [_policy("demo.spend", cap="250")],
            expected_version=expected,
            ratified_by_session=SESSION,
            backtest_digest="f" * 64,
            now=FROZEN_NOW,
        )
    assert caught.value.reason == ratify.REFUSED_BACKTEST_UNRESOLVABLE
    assert policy_loader.current_version(conn) == expected


def test_a_citation_of_a_different_candidate_is_refused_under_a_different_reason(
    conn: Connection, config: EngineConfig
) -> None:
    """R045 §4.1. Citing someone else's homework, made structurally impossible.

    The two backtest refusals are deliberately **not** one reason: a digest that
    resolves to nothing and a digest that resolves to a receipt about another candidate
    are different facts with different remedies.
    """
    expected = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    other = [_policy("demo.spend", cap="999"), _restore()]
    digest = _stored_backtest(conn, config, other)
    expected = policy_loader.current_version(conn) or expected

    with pytest.raises(ratify.RatificationRefused) as caught:
        ratify.ratify(
            conn,
            [_policy("demo.spend", cap="250")],
            expected_version=expected,
            ratified_by_session=SESSION,
            backtest_digest=digest,
            now=FROZEN_NOW,
        )
    assert caught.value.reason == ratify.REFUSED_BACKTEST_MISMATCH
    assert caught.value.reason != ratify.REFUSED_BACKTEST_UNRESOLVABLE
    assert conn.execute("SELECT COUNT(*) AS n FROM ratifications").fetchone()["n"] == 0


def test_a_matching_citation_is_accepted_and_recorded(
    conn: Connection, config: EngineConfig
) -> None:
    _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    candidate = [_policy("demo.spend", cap="250"), _restore()]
    digest = _stored_backtest(conn, config, candidate)
    expected = policy_loader.current_version(conn)

    receipt = ratify.ratify(
        conn,
        candidate,
        expected_version=expected,
        ratified_by_session=SESSION,
        backtest_digest=digest,
        now=FROZEN_NOW,
    )
    assert receipt.backtest_digest == digest
    assert receipt.candidate_digest == backtest.policy_digest(candidate)
    stored = ratify.load(conn, receipt.digest())
    assert stored is not None
    assert stored["backtest_digest"] == digest


def test_ratifying_without_a_backtest_is_allowed_and_the_absence_is_in_the_receipt(
    fresh: Connection,
) -> None:
    """R045 §4: refusing would block the first policy on a fresh store."""
    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    sealed = receipt.sealed()
    assert "backtest_digest" in sealed and sealed["backtest_digest"] is None, (
        "the field must be present-and-null, not omitted — an omitted field reads as "
        "'not applicable' where null reads as 'none, and that is worth knowing'"
    )


def test_the_receipt_names_the_session_and_says_it_is_declared(fresh: Connection) -> None:
    """R045 §3: `ratified_by_session`, never `ratified_by`."""
    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    sealed = receipt.sealed()
    assert sealed["ratified_by_session"] == SESSION
    assert "ratified_by" not in sealed, "the short name reads as an identity claim"
    assert sealed["schema"] == "onedoor/ratification/1"


def test_the_receipt_is_its_own_content_address(fresh: Connection) -> None:
    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    from onedoor._vendor.canonical import digest_obj

    sealed = receipt.sealed()
    body = {k: v for k, v in sealed.items() if k != "ratification_digest"}
    assert digest_obj(body) == sealed["ratification_digest"]

    forged = {**sealed, "ratified_by_session": "someone-else"}
    body = {k: v for k, v in forged.items() if k != "ratification_digest"}
    assert digest_obj(body) != forged["ratification_digest"]


def test_the_ratifications_table_is_append_only(fresh: Connection) -> None:
    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        fresh.execute("UPDATE ratifications SET ratified_by_session='x'")
    with pytest.raises(sqlite3.IntegrityError):
        fresh.execute("DELETE FROM ratifications")
    assert ratify.load(fresh, receipt.digest()) is not None


# --- T4: the two-file export ------------------------------------------------------


def test_the_export_verifies_from_two_files_and_no_store(fresh: Connection, tmp_path: Path) -> None:
    """The independence metric `anchoring.verify_files` set, applied here."""
    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    body, snapshot = ratify.export(fresh, receipt.digest())

    receipt_path = tmp_path / "ratification.json"
    snapshot_path = tmp_path / "snapshot.json"
    receipt_path.write_text(json.dumps(body), encoding="utf-8")
    snapshot_path.write_text(snapshot, encoding="utf-8", newline="")

    status, detail = ratify.verify_files(str(receipt_path), str(snapshot_path))
    assert status == "verified", detail


def test_a_tampered_snapshot_fails_the_two_file_check(fresh: Connection, tmp_path: Path) -> None:
    """Both directions: the check must fail when it should, not only pass when it should."""
    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    body, snapshot = ratify.export(fresh, receipt.digest())
    receipt_path = tmp_path / "ratification.json"
    snapshot_path = tmp_path / "snapshot.json"
    receipt_path.write_text(json.dumps(body), encoding="utf-8")
    tampered = snapshot.replace("demo.spend", "demo.spendx")
    assert tampered != snapshot, "the tamper did not land — the test would pass vacuously"
    snapshot_path.write_text(tampered, encoding="utf-8", newline="")

    status, detail = ratify.verify_files(str(receipt_path), str(snapshot_path))
    assert status == "failed"
    assert "hashes to" in detail


def test_a_tampered_receipt_fails_the_two_file_check(fresh: Connection, tmp_path: Path) -> None:
    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    body, snapshot = ratify.export(fresh, receipt.digest())
    receipt_path = tmp_path / "ratification.json"
    snapshot_path = tmp_path / "snapshot.json"
    receipt_path.write_text(
        json.dumps({**body, "ratified_by_session": "someone-else"}), encoding="utf-8"
    )
    snapshot_path.write_text(snapshot, encoding="utf-8", newline="")

    status, detail = ratify.verify_files(str(receipt_path), str(snapshot_path))
    assert status == "failed"
    assert "own digest" in detail


# --- Q3: the kill switch does not block, and the lift is loud ---------------------


def test_ratification_proceeds_under_an_engaged_switch(fresh: Connection) -> None:
    """R045 §5. The switch stops actions; the pen keeps working, and says so."""
    with tx(fresh):
        killswitch.set_engaged(fresh, True, origin="test")

    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    assert receipt.kill_switch_engaged is True
    assert receipt.sealed()["kill_switch_engaged"] is True


def test_the_switch_state_is_inside_the_receipts_digest(fresh: Connection) -> None:
    """Visible forever, deniable never — because relabelling breaks the address."""
    with tx(fresh):
        killswitch.set_engaged(fresh, True, origin="test")
    receipt = ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    from onedoor._vendor.canonical import digest_obj

    sealed = receipt.sealed()
    forged = {**sealed, "kill_switch_engaged": False}
    body = {k: v for k, v in forged.items() if k != "ratification_digest"}
    assert digest_obj(body) != forged["ratification_digest"]


def test_the_lift_reports_a_policy_change_made_behind_a_shut_door(conn: Connection) -> None:
    """*"The rules changed while the door was shut, from X to Y."*"""
    at_engagement = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    with tx(conn):
        killswitch.set_engaged(conn, True, origin="test")

    ratify.ratify(
        conn,
        [_policy("demo.spend", cap="250")],
        expected_version=at_engagement,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    with tx(conn):
        report = killswitch.set_engaged(conn, False, origin="test")

    assert report is not None
    assert report.state == killswitch.CHANGED
    assert report.version_at_engagement == at_engagement
    assert report.version_at_release == policy_loader.current_version(conn)
    assert "the rules changed while the door was shut" in report.sentence().lower()


def test_the_lift_reports_no_change_when_nothing_moved(conn: Connection) -> None:
    at_engagement = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    with tx(conn):
        killswitch.set_engaged(conn, True, origin="test")
    with tx(conn):
        report = killswitch.set_engaged(conn, False, origin="test")
    assert report is not None
    assert report.state == killswitch.UNCHANGED
    assert report.version_at_engagement == at_engagement


def test_an_engagement_with_no_recorded_version_is_undeterminable_not_unchanged(
    fresh: Connection,
) -> None:
    """R010. "We cannot tell" is never rendered as "nothing happened"."""
    with tx(fresh):
        killswitch.set_engaged(fresh, True, origin="test")
    assert policy_loader.current_version(fresh) is None

    ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    with tx(fresh):
        report = killswitch.set_engaged(fresh, False, origin="test")

    assert report is not None
    assert report.state == killswitch.UNDETERMINABLE
    assert report.state != killswitch.UNCHANGED
    assert "cannot be determined" in report.sentence()


def test_re_engaging_keeps_the_first_engagements_baseline(conn: Connection) -> None:
    """The door has been shut since the FIRST engagement; that is where the report runs from.

    An idempotent call that quietly reset the baseline would erase exactly the change
    the report exists to surface.
    """
    first = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    with tx(conn):
        killswitch.set_engaged(conn, True, origin="test")
    ratify.ratify(
        conn,
        [_policy("demo.spend", cap="250")],
        expected_version=first,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    with tx(conn):
        killswitch.set_engaged(conn, True, origin="test")  # re-engage: no new baseline
    with tx(conn):
        report = killswitch.set_engaged(conn, False, origin="test")

    assert report is not None
    assert report.state == killswitch.CHANGED
    assert report.version_at_engagement == first
    assert conn.execute("SELECT COUNT(*) AS n FROM kill_switch_episodes").fetchone()["n"] == 1


def test_releasing_an_already_released_switch_reports_nothing(conn: Connection) -> None:
    """No door opened, so no reassuring sentence is manufactured for it."""
    with tx(conn):
        assert killswitch.set_engaged(conn, False, origin="test") is None


def test_a_switch_engaged_with_no_episode_reports_its_own_state(conn: Connection) -> None:
    """A store upgraded while the switch was already held. Not `unchanged`."""
    _in_force(conn, _policy("demo.spend"), _restore())
    with tx(conn):
        # The pre-0018 world: the flag set without an episode row.
        conn.execute(
            "INSERT INTO config (key, value, updated_at) VALUES ('kill_switch_engaged','1',?)",
            (FROZEN_NOW.isoformat(),),
        )
    assert killswitch.is_engaged(conn)

    with tx(conn):
        report = killswitch.set_engaged(conn, False, origin="test")

    assert report is not None
    assert report.state == killswitch.NO_EPISODE
    assert report.state not in (killswitch.UNCHANGED, killswitch.CHANGED)
    assert "not a report that they did not" in report.sentence()


def test_the_episode_is_closed_with_both_hashes(conn: Connection) -> None:
    at_engagement = _in_force(conn, _policy("demo.spend", cap="500"), _restore())
    with tx(conn):
        killswitch.set_engaged(conn, True, origin="test")
    ratify.ratify(
        conn,
        [_policy("demo.spend", cap="250")],
        expected_version=at_engagement,
        ratified_by_session=SESSION,
        now=FROZEN_NOW + timedelta(minutes=5),
    )
    with tx(conn):
        killswitch.set_engaged(conn, False, origin="test")

    row = conn.execute("SELECT * FROM kill_switch_episodes ORDER BY id DESC LIMIT 1").fetchone()
    assert row["released_at"] is not None
    assert row["version_hash_at_engagement"] == at_engagement
    assert row["version_hash_at_release"] == policy_loader.current_version(conn)
    assert killswitch.open_episode(conn) is None


# --- The ceremony writes nothing to the enforcer's record -------------------------


def test_a_ratification_adds_no_rows_to_the_decision_ledger(fresh: Connection) -> None:
    """Constitution principle 1: the proposer is never the enforcer."""
    before = fresh.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"]
    ratify.ratify(
        fresh,
        [_policy("demo.spend"), _restore()],
        expected_version=None,
        ratified_by_session=SESSION,
        now=FROZEN_NOW,
    )
    after = fresh.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"]
    assert after == before


def test_an_effect_policy_change_is_diffed_and_ratified(conn: Connection) -> None:
    _in_force(conn, _policy("demo.spend"), _restore())
    effects = [EffectPolicy(effect="money.egress", min_tier=Tier.CONFIRM, caps=Caps())]
    expected = policy_loader.current_version(conn)

    shown = ratify.preview(conn, [], effects=effects)
    assert shown.effect_changes.added == ["money.egress"]

    receipt = ratify.ratify(
        conn,
        [],
        expected_version=expected,
        ratified_by_session=SESSION,
        effects=effects,
        now=FROZEN_NOW,
    )
    assert receipt.to_version == shown.to_version
    assert receipt.sealed()["effect_changes"]["added"] == ["money.egress"]
