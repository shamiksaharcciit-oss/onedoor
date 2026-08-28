"""V6 — the flagship: *"was this correct under last week's rules?"*

The screen nobody else has, so most of these tests are about the ways it could quietly
lie: a comparison that could not be made rendering as one that found no difference, a
version that cannot be rebuilt replaying as an empty policy set, or a counterfactual
that forgets to say it is one.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.models import ActionRequest, Bounds, Caps, Policy, Source, Tier
from onedoor.store.clock import now_utc
from onedoor.studio import history, reevaluate, screens, server, shell
from tests.viewer.assertions import assert_reader_sees


def _capped(conn, eur_day: str) -> str:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="payments.transfer",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="payments.reverse",
            cost_param="amount_eur",
            caps=Caps(eur_day=eur_day),
            bounds=Bounds(required=["amount_eur"], strict_params=False),
        ),
    )
    return policy_loader.current_version(conn)


@pytest.fixture
def scene(tmp_path):
    """A decision refused under a tight cap, and a later version that loosens it.

    The scene the flagship exists for: *the rules changed, was that refusal right?*
    """
    st = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    tight = _capped(st.enforcer, "100.00")
    request = ActionRequest(
        request_id=uuid4(),
        action_type="payments.transfer",
        params={"amount_eur": "400.00"},
        source=Source.LLM,
        rationale="test",
        created_at=now_utc(),
    )
    decide_and_reserve(request, conn=st.enforcer, config=st.config, now=request.created_at)
    loose = _capped(st.enforcer, "5000.00")
    row_id = history.page(st.enforcer).entries[0].row_id
    return st, history.entry(st.enforcer, row_id), tight, loose


# --- The premise -------------------------------------------------------------------------


def test_policy_sets_are_retrievable_by_version(scene) -> None:
    """R055 V6 asks this be verified first. It is — and this test is the verification,
    kept as a test rather than as a sentence in a report."""
    st, _row, tight, loose = scene
    versions = reevaluate.retrievable_versions(st.enforcer)
    assert tight in versions
    assert loose in versions
    assert reevaluate._policies_at(st.enforcer, tight) is not None


def test_the_dropdown_offers_only_what_the_store_can_serve(scene) -> None:
    """R056: *the version dropdown lists what `snapshot_for` can honestly serve.*

    Read from `policy_versions`, not from the audit log's distinct version values — a
    version some row once named is not necessarily one this store can rebuild.
    """
    st, row, _tight, _loose = scene
    st.enforcer.execute(
        "INSERT INTO actions_audit (request_id, kind, action_type, source, params_json,"
        " decision, reason_code, nominal_tier, effective_tier, created_at, policy_version)"
        " VALUES ('x','decision','a.b','llm','{}','denied','bounds',1,1,'2026-01-01','ghost')"
    )
    st.enforcer.commit()
    assert "ghost" not in reevaluate.retrievable_versions(st.enforcer)
    html = screens.reevaluate_block(row, reevaluate.retrievable_versions(st.enforcer))
    assert "ghost" not in html


# --- The comparison ------------------------------------------------------------------------


def test_replaying_under_the_version_that_decided_agrees_with_the_record(scene) -> None:
    """The control case, and the strongest evidence the instrument is the right one: the
    engine, given the same inputs and the same rules, reaches the same verdict it
    reached live."""
    st, row, tight, _loose = scene
    comparison = reevaluate.compare(st.enforcer, row, tight, config=st.config)
    assert comparison.now is not None
    assert comparison.then.shape == comparison.now.shape == "denied"
    assert comparison.changed is False


def test_replaying_under_a_looser_version_shows_the_answer_changing(scene) -> None:
    """The flagship's whole point: *this refusal would be a permit under today's rules.*"""
    st, row, _tight, loose = scene
    comparison = reevaluate.compare(st.enforcer, row, loose, config=st.config)
    assert comparison.then.shape == "denied"
    assert comparison.now is not None
    assert comparison.now.shape == "allowed"
    assert comparison.changed is True


def test_the_replay_uses_the_engine_and_not_a_second_implementation(scene) -> None:
    """`decide_and_reserve` is the entry point the live service calls.

    A hand-written comparison of rules would be a second implementation of the verdict,
    and the two would disagree the first time anything subtle changed. Asserted against
    the source, the same structural fence the read-only screens carry.
    """
    import inspect

    source = inspect.getsource(reevaluate)
    assert "decide_and_reserve" in source
    for reimplementation in ("if policy.tier", "cap_counters", "def _verdict"):
        assert reimplementation not in source, f"a second verdict path: {reimplementation}"


def test_the_replay_changes_nothing_in_the_real_store(scene) -> None:
    """It runs a decision function. An operator who thinks a payment was attempted twice
    has been badly misled by a button."""
    st, row, _tight, loose = scene
    before = (
        st.enforcer.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"],
        st.enforcer.execute("SELECT COUNT(*) AS n FROM cap_counters").fetchone()["n"],
        policy_loader.current_version(st.enforcer),
    )
    for _ in range(3):
        reevaluate.compare(st.enforcer, row, loose, config=st.config)
    after = (
        st.enforcer.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"],
        st.enforcer.execute("SELECT COUNT(*) AS n FROM cap_counters").fetchone()["n"],
        policy_loader.current_version(st.enforcer),
    )
    assert before == after


# --- The three outcomes ---------------------------------------------------------------------


def test_an_unretrievable_version_is_not_replayed_as_an_empty_policy_set(scene) -> None:
    """**The most dangerous available answer**, and the one this refuses to give.

    An empty policy set replays as default-deny and returns a confident `denied` — the
    shape of a real verdict, carrying none of its meaning.
    """
    st, row, _tight, _loose = scene
    comparison = reevaluate.compare(st.enforcer, row, "de" * 32, config=st.config)
    assert comparison.now is None
    assert comparison.reason == reevaluate.NOT_RETRIEVABLE
    assert comparison.changed is None, "a comparison that could not be made claimed a result"

    html = screens.reevaluate_block(row, (), comparison)
    assert reevaluate.NOT_RETRIEVABLE in html
    assert "confident refusal that means nothing" in html
    assert "would have been the same" not in html
    assert "would have changed" not in html


def test_a_row_that_cannot_be_rebuilt_is_a_different_failure(scene) -> None:
    """*Not retrievable* is about the rules; *cannot be replayed* is about the question.
    Different facts, different remedies, so they never share a word."""
    st, _row, _tight, loose = scene
    st.enforcer.execute(
        "INSERT INTO actions_audit (request_id, kind, action_type, source, params_json,"
        " decision, reason_code, nominal_tier, effective_tier, created_at, policy_version)"
        " VALUES ('y','decision','a.b','llm','{not json','denied','bounds',1,1,"
        "'2026-01-01',?)",
        (loose,),
    )
    st.enforcer.commit()
    row = history.entry(st.enforcer, history.page(st.enforcer).entries[0].row_id)
    comparison = reevaluate.compare(st.enforcer, row, loose, config=st.config)
    assert comparison.now is None
    assert comparison.reason == reevaluate.UNREPLAYABLE
    assert comparison.reason != reevaluate.NOT_RETRIEVABLE

    html = screens.reevaluate_block(row, (loose,), comparison)
    assert "nothing to replay" in html


def test_changed_is_none_and_never_false_when_nothing_ran(scene) -> None:
    """The type keeps it apart so the caller does not have to remember to."""
    st, row, _tight, _loose = scene
    comparison = reevaluate.compare(st.enforcer, row, "ff" * 32, config=st.config)
    assert comparison.changed is not False
    assert comparison.changed is None


# --- What the screen must say (R061 §5) -------------------------------------------------------


def test_the_screen_names_both_versions_in_the_same_breath(scene) -> None:
    """R061 §5. The version that decided then, and the version replaying now."""
    st, row, tight, loose = scene
    comparison = reevaluate.compare(st.enforcer, row, loose, config=st.config)
    html = screens.reevaluate_block(row, (tight, loose), comparison)
    assert shell.short_digest(tight) in html, "the deciding version is not named"
    assert shell.short_digest(loose) in html, "the replaying version is not named"
    assert "Decided under" in html and "replayed under" in html


def test_the_screen_wears_the_would_have_limit_sentence(scene) -> None:
    """A counterfactual that does not name its counterfactual-ness on the screen where
    it renders is the backtest panel's lie one click deeper."""
    st, row, tight, loose = scene
    for comparison in (
        None,
        reevaluate.compare(st.enforcer, row, loose, config=st.config),
        reevaluate.compare(st.enforcer, row, "de" * 32, config=st.config),
    ):
        html = screens.reevaluate_block(row, (tight, loose), comparison)
        assert_reader_sees(html, reevaluate.WOULD_HAVE)
        assert "not what will be" in html
        assert "Nothing was re-executed" in html


def test_the_version_that_decided_is_marked_in_the_dropdown(scene) -> None:
    """So a reader can find the control case without comparing digests by eye."""
    st, row, tight, loose = scene
    html = screens.reevaluate_block(row, (tight, loose))
    assert "the version that decided" in html


def test_both_verdicts_carry_their_own_word(scene) -> None:
    """The same law the chips follow: the colour never stands in for the verdict."""
    st, row, tight, loose = scene
    comparison = reevaluate.compare(st.enforcer, row, loose, config=st.config)
    html = screens.reevaluate_block(row, (tight, loose), comparison)
    assert "Decided then" in html and "Would be now" in html
    assert ">denied<" in html
    assert ">executed<" in html


def test_the_block_renders_inside_the_shell_and_reaches_nowhere(scene) -> None:
    st, row, tight, loose = scene
    html = shell.render(
        body=screens.reevaluate_block(row, (tight, loose)),
        banner=shell.Banner("a" * 64, "2026-08-28", 1, 0),
        active="history",
    )
    assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html)


def test_a_hostile_version_string_cannot_smuggle_markup(scene) -> None:
    st, row, _tight, _loose = scene
    hostile = "<script>alert(1)</script>"
    comparison = reevaluate.compare(st.enforcer, row, hostile, config=st.config)
    html = screens.reevaluate_block(row, (hostile,), comparison)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
