"""The proposal surface (S6-T5): one page, two sections, never one table.

R053 §3, held from the rendered document rather than from the stylesheet's comments:
a measured row and an asserted row must never share a table, the asserted section must
state its warrant on its face, and every asserted row must cite what it was checked
against.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html import escape
from sqlite3 import Connection

import pytest

from onedoor.guardrail import policy_loader
from onedoor.studio import coverage as coverage_model
from onedoor.studio import proposer as proposer_model
from onedoor.studio import ratify
from onedoor.viewer import proposal as skin

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
DESCRIPTION = "We issue refunds to customers and post webhooks to our payment partner."

SECTION = re.compile(r"<section class='([^']+)'>(.*?)</section>", re.S)


def rendered_form(sentence: str) -> str:
    """A constant as it appears ON THE PAGE, escaped.

    These sentences contain apostrophes — *a model's reading*, *the candidate's
    authority* — which correctly render as `&#x27;`. An earlier version of these tests
    searched for the raw constant and failed, and the escaping is not the defect: a page
    that did NOT escape operator-adjacent text would be the defect. So the test compares
    against what the renderer is required to emit.
    """
    return escape(sentence, quote=True)


@pytest.fixture
def rendered(fresh: Connection) -> tuple[str, coverage_model.CoverageMap, dict]:
    proposal, record = proposer_model.derive(proposer_model.FixtureProposer(), DESCRIPTION, now=NOW)
    ratify.ratify(
        fresh,
        proposal.policies,
        effects=proposal.effects,
        expected_version=policy_loader.current_version(fresh),
        ratified_by_session="tests",
        now=NOW,
    )
    m = coverage_model.build(fresh)
    sealed = record.sealed()
    return skin.render_page(m, proposal.mentions, sealed), m, sealed


def _sections(html: str) -> dict[str, str]:
    return {classes.split()[0]: body for classes, body in SECTION.findall(html)}


# --- Two sections, never one table -------------------------------------------------


def test_the_page_has_both_sections_and_they_are_separate(rendered) -> None:
    html, _, _ = rendered
    sections = _sections(html)
    assert "measured" in sections
    assert "asserted" in sections
    assert "<table" not in html, "the two kinds must not share a table"


def test_no_measured_row_appears_inside_the_asserted_section(rendered) -> None:
    """The whole point: a claim must never occupy a measurement's row."""
    html, m, _ = rendered
    asserted = _sections(html)["asserted"]
    for row in m.effects:
        assert f"<span class='state'>{row.state.upper()}" not in asserted
    assert "MENTIONED" in asserted


def test_each_section_states_its_own_warrant(rendered) -> None:
    """*A list is honest only if every row carries the same kind of warrant.*"""
    html, _, _ = rendered
    sections = _sections(html)
    assert rendered_form(skin.MEASURED_WARRANT) in sections["measured"]
    assert rendered_form(skin.ASSERTED_WARRANT) in sections["asserted"]
    assert "NOT a measurement" in skin.ASSERTED_WARRANT


def test_every_asserted_row_cites_what_it_was_checked_against(rendered) -> None:
    html, m, _ = rendered
    asserted = _sections(html)["asserted"]
    citation = m.citation()
    assert str(citation["version_hash"]) in asserted, "the coverage citation is not on the row"
    for fragment in ("covered by", "no rule covers it"):
        if fragment in asserted:
            break
    else:  # pragma: no cover - one of the two must appear
        raise AssertionError("no asserted row states its coverage state")


# --- The derivation record's face --------------------------------------------------


def test_both_face_sentences_render(rendered) -> None:
    """R053 §1: the record says what it does not claim, on its face, every time."""
    html, _, _ = rendered
    assert rendered_form(proposer_model.NOT_REDERIVABLE) in html
    assert rendered_form(proposer_model.AUTHORITY_FROM_CHECKS) in html


def test_the_provenance_label_survives_to_the_surface(rendered) -> None:
    """B5's shape: the label reaches every rendering, not just the digest."""
    html, _, sealed = rendered
    assert sealed["proposer_provenance"] == proposer_model.FIXTURE
    assert "proposer_provenance" in html
    assert ">fixture<" in html


def test_the_instrument_block_renders_and_is_not_empty(rendered) -> None:
    html, _, sealed = rendered
    for key in sealed["instrument"]:
        assert key in html


def test_sabotage_stripping_the_label_is_visible_on_the_page(rendered, fresh: Connection) -> None:
    """The other direction: a page rendered from a stripped record must not read as live.

    The digest catches relabelling; this catches *omission*, which a digest cannot — a
    field that is gone breaks no arithmetic, so the rendering has to refuse to be silent.
    """
    _, m, sealed = rendered
    stripped = {k: v for k, v in sealed.items() if k != "proposer_provenance"}
    html = skin.render_page(m, [], stripped)
    assert ">live<" not in html, "a record with no label must never render as live"
    assert "proposer_provenance" in html, "the field must still be named, even when absent"


# --- No verdict colours ------------------------------------------------------------


def test_the_proposal_page_uses_no_verdict_colours(rendered) -> None:
    """This page carries no verdicts; the semantic pair is spent everywhere or nowhere."""
    html, _, _ = rendered
    for var in skin.STATE_COLOUR_VARS:
        assert f"var({var})" not in html


def test_the_asserted_section_is_visibly_a_different_kind(rendered) -> None:
    """Separated by heading is not enough — a reader scrolls past headings."""
    html, _, _ = rendered
    styles = html.split("<style>")[1].split("</style>")[0]
    rule = " ".join(r for r in styles.split("}") if "section.asserted" in r)
    assert rule, "the asserted section has no distinguishing style"
    assert "var(--seal)" in rule


def test_the_page_escapes_the_descriptions_own_words(fresh: Connection) -> None:
    """A description is operator-supplied text and reaches this page verbatim."""
    hostile = "We issue refunds <script>alert(1)</script> and webhooks."
    proposal, record = proposer_model.derive(proposer_model.FixtureProposer(), hostile, now=NOW)
    m = coverage_model.build(fresh)
    html = skin.render_page(m, proposal.mentions, record.sealed())
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
