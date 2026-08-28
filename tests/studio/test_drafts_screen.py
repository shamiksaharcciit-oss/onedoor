"""V5 / S3 — drafts and the ceremony: what the page says, and what it refuses to say.

The ratify page is the only screen in this Studio with ceremony in it, and R060 §5 is
the constraint most of these tests enforce: **its gravity must come from what is true.**
So the tests are largely about claims *not* made — no reversibility the engine cannot
back, no forecast from a replay of the past, no drama the engine does not do.
"""

from __future__ import annotations

import re

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.studio import drafts, screens, server, shell, validate


@pytest.fixture
def state(tmp_path):
    st = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    policy_loader.upsert(
        st.enforcer,
        Policy(
            action_type="reports.read",
            tier=Tier.OBSERVE,
            dry_run=False,
            compensating_command="",
            bounds=Bounds(strict_params=False),
        ),
    )
    return st


def _draft_with_a_new_rule(st, title="tighten payments"):
    draft = server.new_draft(st, title=title)
    policies = [
        *draft.policies,
        Policy(
            action_type="payments.transfer",
            tier=Tier.CONFIRM,
            dry_run=False,
            compensating_command="payments.reverse",
            cost_param="amount_eur",
            caps=Caps(eur_day="500.00"),
            bounds=Bounds(required=["amount_eur"], strict_params=False),
        ),
    ]
    server.save_draft(st, draft.draft_id, policies=policies, effects=list(draft.effects))
    return draft.draft_id


def _view(st, draft_id, **kw):
    return drafts.build(st.enforcer, st.studio, draft_id, config=st.config, **kw)


# --- The diff --------------------------------------------------------------------------


def test_the_diff_shows_was_and_would_become_per_rule(state) -> None:
    """R055 V5. A count of changed rules is not a diff."""
    view = _view(state, _draft_with_a_new_rule(state))
    assert [d.action_type for d in view.diffs] == ["payments.transfer"]
    assert view.diffs[0].kind == "added"
    assert view.diffs[0].was is None
    assert view.diffs[0].becomes is not None

    html = screens.draft_body(view)
    assert "would become" in html
    assert "was" in html


def test_the_diff_comes_from_the_preview_the_ceremony_itself_computes(state) -> None:
    """The page and the receipt cannot disagree about what changed, because they are
    reading the same `ratify.diff` — the same reason the coverage map cites its inputs
    rather than recomputing them."""
    view = _view(state, _draft_with_a_new_rule(state))
    preview = view.view.panels.preview
    assert set(preview.changes.added) == {d.action_type for d in view.diffs if d.kind == "added"}


def test_a_draft_identical_to_what_is_in_force_says_so(state) -> None:
    draft = server.new_draft(state, title="no changes")
    html = screens.draft_body(_view(state, draft.draft_id))
    assert "would change nothing" in html


# --- The honesty footnote ----------------------------------------------------------------


def test_the_validator_honesty_notice_appears_verbatim(state) -> None:
    """R055 V5: *VERBATIM*. Interpolated from the constant, never retyped, so the page
    and the validator cannot drift apart."""
    from html import escape, unescape

    view = _view(state, _draft_with_a_new_rule(state))
    for html in (screens.draft_body(view), screens.ceremony_body(view)):
        # Compared escaped, and then unescaped back: the page markup carries
        # `engine&#x27;s`, which is the page being correct about HTML, and what a reader
        # SEES is the constant character for character. Asserting only the raw form
        # would have made a correctly-escaped page look like a paraphrase.
        assert escape(validate.INCOMPLETE_NOTICE) in html
        rendered = unescape(re.sub(r"<[^>]+>", "", html))
        assert validate.INCOMPLETE_NOTICE in rendered


def test_the_honesty_notice_is_not_a_paraphrase() -> None:
    """The design note calls honest limits part of the brand. A rewrite that softened
    "not all problems" would be the one edit that matters."""
    assert "not all problems" in validate.INCOMPLETE_NOTICE
    assert "stops at the first failure in each rule" in validate.INCOMPLETE_NOTICE


# --- The backtest panel, which is about the past -------------------------------------------


def test_the_backtest_panel_states_that_it_is_about_the_past(state) -> None:
    """**The overclaim this screen most invites.** A divergence count read as a forecast
    is the difference between a replay and a prediction."""
    view = _view(state, _draft_with_a_new_rule(state))
    html = screens.draft_body(view)
    assert drafts.BACKTEST_IS_ABOUT_THE_PAST in html
    assert "not what will" in html


def test_a_backtest_that_was_not_run_shows_no_numbers(state) -> None:
    """Absent is a state. Zeroes would read as a clean replay that never happened."""
    view = _view(state, _draft_with_a_new_rule(state))
    html = screens.draft_body(view)
    assert "Not run" in html
    assert "decisions replayed" not in html


def test_each_flip_direction_gets_its_own_sentence() -> None:
    """A single "N verdicts changed" hides the one direction an operator must never
    miss."""
    assert drafts.flip_sentence("denied->allowed") == ("permits what was refused", True)
    assert drafts.flip_sentence("allowed->denied") == ("refuses what was permitted", False)


def test_widening_directions_are_marked_apart_from_tightening_ones() -> None:
    """A count alone treats a loosening and a tightening as the same event."""
    for key in ("denied->allowed", "denied->to_approval", "to_approval->allowed"):
        assert drafts.flip_sentence(key)[1] is True, key
    for key in ("allowed->denied", "to_approval->denied", "allowed->to_approval"):
        assert drafts.flip_sentence(key)[1] is False, key


def test_an_unknown_flip_direction_is_not_paraphrased() -> None:
    """A direction this module has no sentence for is one it must not invent words for."""
    sentence, widening = drafts.flip_sentence("weird->thing")
    assert sentence == "weird became thing"
    assert widening is False


# --- The ceremony: gravity from what is true -----------------------------------------------


def test_the_ceremony_shows_the_digest_the_diff_and_the_irreversibility(state) -> None:
    """R060 §5: the three true things, and the confirm."""
    view = _view(state, _draft_with_a_new_rule(state))
    html = screens.ceremony_body(view)
    assert view.view.panels.preview.to_version in html
    assert "would become" in html
    assert drafts.IRREVERSIBLE in html
    assert 'type="submit"' in html


def test_the_ceremony_does_not_claim_the_change_cannot_be_undone(state) -> None:
    """**Not "this cannot be undone"** — that would be false, and falsely frightening.

    The truth is narrower and more useful: there is no un-ratify, and the way back is
    forward. A ceremony that overstates is a design-study banner away from a lie.
    """
    html = screens.ceremony_body(_view(state, _draft_with_a_new_rule(state)))
    assert "cannot be undone" not in html
    assert "irreversible" not in html.lower()
    assert "no un-ratify" in html
    assert "you ratify again" in html


def test_the_ceremony_adds_no_drama_the_engine_does_not_do(state) -> None:
    """No countdown, no alarm, no warning the engine cannot back."""
    html = screens.ceremony_body(_view(state, _draft_with_a_new_rule(state)))
    for theatre in ("countdown", "danger", "warning:", "are you sure", "permanent"):
        assert theatre not in html.lower(), f"the ceremony dramatizes: {theatre!r}"


def test_the_session_note_is_described_as_what_it_is(state) -> None:
    """It is what the store knows, not an authenticated identity — and saying so is the
    same discipline as `ratified_by_session`'s own naming."""
    html = screens.ceremony_body(_view(state, _draft_with_a_new_rule(state)))
    assert "not an authenticated identity" in html
    assert "ratified_by_session" in html


def test_a_stale_draft_shows_no_numbers_and_offers_a_repin(state) -> None:
    """Every number on the page was computed from a base that is no longer in force, so
    none is shown — R047 §3's rule that they go stale together."""
    draft_id = _draft_with_a_new_rule(state)
    policy_loader.upsert(
        state.enforcer,
        Policy(
            action_type="something.else",
            tier=Tier.OBSERVE,
            dry_run=False,
            compensating_command="",
            bounds=Bounds(strict_params=False),
        ),
    )
    view = _view(state, draft_id)
    assert view.stale is True
    html = screens.draft_body(view)
    assert drafts.STALE_BASE in html
    assert "Re-pin" in html
    assert "would become" not in html, "a stale draft rendered a diff from a dead base"

    ceremony = screens.ceremony_body(view)
    assert drafts.STALE_BASE in ceremony
    assert 'type="submit"' not in ceremony, "a stale draft offered a confirm"


# --- The receipt, and the refusal ------------------------------------------------------------


def test_a_receipt_renders_what_was_sealed(state) -> None:
    outcome = server.ratify_draft(state, _draft_with_a_new_rule(state), session="tester")
    assert outcome.ratified is True
    html = screens.receipt_body(outcome, "x")
    assert outcome.receipt.to_version in html
    assert "tester" in html
    assert "Kill switch" in html


def test_a_refusal_keeps_the_ceremonys_own_words(state) -> None:
    """R047 §S2-T5: the lost race and the citation failures are distinct facts with
    distinct remedies, and collapsing them hands back the ambiguity the ceremony refused
    to have."""
    draft_id = _draft_with_a_new_rule(state)
    policy_loader.upsert(
        state.enforcer,
        Policy(
            action_type="moved.the.base",
            tier=Tier.OBSERVE,
            dry_run=False,
            compensating_command="",
            bounds=Bounds(strict_params=False),
        ),
    )
    outcome = server.ratify_draft(state, draft_id, session="tester")
    assert outcome.ratified is False
    html = screens.receipt_body(outcome, draft_id)
    assert outcome.reason in html
    assert "Nothing was applied" in html


# --- Q5: two voices, never merged ---------------------------------------------------------


def test_the_operators_words_are_omitted_when_nothing_links(state) -> None:
    """An empty quotation would read as an operator who wrote nothing — a different fact
    from a rule never proposed through the Studio."""
    assert library_frozen(state, "reports.read") is None
    html = screens.policy_body(
        _policy(state, "reports.read"), _library(state), library_frozen(state, "reports.read")
    )
    assert "What the operator said it was for" not in html


def test_the_two_voices_are_rendered_apart_and_labelled(state) -> None:
    """R058 §6: **show BOTH voices, never merged.** The page must make disagreement
    visible, not smooth."""
    from onedoor.studio import library

    words = library.FrozenWords(
        description_digest="a" * 64,
        quotes=("we refund customers within 30 days",),
        whole="we refund customers within 30 days",
    )
    html = screens.policy_body(_policy(state, "reports.read"), _library(state), words)
    assert "What this rule does" in html
    assert "What the operator said it was for" in html
    assert "<blockquote>we refund customers within 30 days</blockquote>" in html
    assert "not the engine" in html
    assert "nothing here is checked against the rule" in html


def test_a_description_that_does_not_mention_the_rule_says_so(state) -> None:
    """Silence about a rule is itself a finding — a rule nobody described is a different
    thing from a rule with no description."""
    from onedoor.studio import library

    words = library.FrozenWords(description_digest="b" * 64, quotes=(), whole="unrelated")
    html = screens.policy_body(_policy(state, "reports.read"), _library(state), words)
    assert "does not" in html
    assert "mention it" in html


def test_the_operators_words_are_escaped(state) -> None:
    """Received data, and an operator is not a trusted author of markup."""
    from onedoor.studio import library

    words = library.FrozenWords(
        description_digest="c" * 64, quotes=("<script>alert(1)</script>",), whole=None
    )
    html = screens.policy_body(_policy(state, "reports.read"), _library(state), words)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# --- helpers -------------------------------------------------------------------------------


def _library(state):
    from onedoor.studio import library

    return library.build(state.enforcer)


def _policy(state, action):
    from onedoor.studio import library

    return library.policy_at(state.enforcer, action)


def library_frozen(state, action):
    from onedoor.studio import library

    return library.frozen_words(state.enforcer, state.studio, action)


def test_the_drafts_page_renders_inside_the_shell_and_reaches_nowhere(state) -> None:
    html = shell.render(
        body=screens.drafts_body(drafts.listing(state.studio), None),
        banner=shell.Banner("a" * 64, "2026-08-28", 1, 0),
        active="drafts",
    )
    assert 'aria-current="page"' in html
    assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html)
