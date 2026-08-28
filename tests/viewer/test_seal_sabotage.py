"""The sabotage pair for the strengthened seal check (Forward 005, R055 V8(a)).

Forward 005 pins the shape: **two sabotages, not one.** A literal injection proves the
check reads the declaration; a semantic-class route proves it reads the *selector*. A
check that caught only the first would pass any violation written the way real ones are
written — nobody types `--seal` into a rule called `.verdict`; they write a rule for a
state and reach for the colour that looks right.

And the pair must **fail against the check before the fix counts**. These are the tests
that make the four S4 violations and three S6 violations reportable as *caught*, rather
than as *believed to have been caught*.

The third test is the one that keeps the check honest in the other direction: R056 §2
says a conditionally-rendered advisory panel must NOT fire. It is not enough that the
check catches violations — a check that also condemns the innocent teaches people to
route around it, and *a name that outruns its check is false comfort; a check that
outruns its name is a false alarm.*
"""

from __future__ import annotations

import pytest

from onedoor.viewer import canvas as canvas_skin
from onedoor.viewer import coverage as coverage_skin
from onedoor.viewer import proposal as proposal_skin
from tests.viewer.assertions import (
    PropertyViolation,
    assert_seal_never_signals_state,
    seal_state_violations,
)

SKINS = {
    "S4 coverage": coverage_skin._PAGE_CSS,
    "S6 proposal": proposal_skin._PAGE_CSS,
    "studio canvas": canvas_skin._PAGE_CSS,
}


# --- The clean state, which is the claim being made -----------------------------------


@pytest.mark.parametrize("name", sorted(SKINS))
def test_no_skin_routes_the_brand_accent_by_state(name: str) -> None:
    """The migration's result, asserted per skin so a regression names its own screen."""
    assert seal_state_violations(SKINS[name]) == []


# --- Sabotage one: the literal injection ------------------------------------------------


@pytest.mark.parametrize("name", sorted(SKINS))
def test_a_brand_token_dropped_into_a_state_rule_is_caught(name: str) -> None:
    """The obvious violation, which is the one a weak check does catch."""
    sabotaged = SKINS[name] + "\n.row.declared_inert{border-left:3px solid var(--seal);}"
    with pytest.raises(PropertyViolation, match="brand accent"):
        assert_seal_never_signals_state(sabotaged)


@pytest.mark.parametrize("token", ["--seal", "--seal-dim", "--gold", "--gold-dim"])
def test_every_spelling_of_the_brand_accent_is_caught(token: str) -> None:
    """oneview spells it `--seal`; the Studio's ledger-room palette spells it `--gold`.

    A check that knew only one name would pass the Studio by default — the exact shape
    of the grandfather clause R056 §4 removed.
    """
    with pytest.raises(PropertyViolation):
        assert_seal_never_signals_state(f".row.uncovered_observed{{color:var({token});}}")


# --- Sabotage two: the semantic-class route ---------------------------------------------


@pytest.mark.parametrize(
    "selector",
    [
        ".verdict.denied",
        ".row.declared_inert .state",
        ".tally .uncovered_observed b",
        "section.asserted",
        "td.permitted",
        ".chip.review",
    ],
)
def test_a_brand_token_reached_through_a_semantic_class_is_caught(selector: str) -> None:
    """The violation as it is actually written: a rule for a state, in the colour that
    looked right. No `--seal` appears next to the word "verdict" anywhere here."""
    with pytest.raises(PropertyViolation):
        assert_seal_never_signals_state(f"{selector}{{border-left:2px solid var(--gold);}}")


def test_the_state_vocabulary_comes_from_the_code_that_declares_the_states() -> None:
    """A new coverage state is inside the check the moment it exists.

    The alternative — a hand-kept word list — goes stale silently, and a check that has
    silently stopped covering a state is worse than no check, because the screen it no
    longer guards still reports green.
    """
    from onedoor.studio import coverage as coverage_model

    for state in coverage_model.PROMINENCE:
        with pytest.raises(PropertyViolation):
            assert_seal_never_signals_state(f".row.{state}{{color:var(--seal);}}")


# --- The other direction: what must NOT fire ---------------------------------------------


def test_an_advisory_panel_in_gold_does_not_fire() -> None:
    """R056 §2, and the defect this test was written after.

    The first run of this check reported `.store-warning` — F-H's empty-store advice —
    as a violation. It is not one: gold standing near information is brand usage, and
    §4 forbids gold *carrying* state. It fired because the check read the explanatory
    comment above the rule as part of the selector, so a rule inherited every word from
    the prose that documented it. **A check that reads prose as selectors condemns the
    code that documents itself best.**
    """
    innocent = (
        "/* Configuration advice, not a verdict: this panel says the enforcer store has "
        "never held a policy. Seal and rule, never the semantic pair. */\n"
        ".store-warning{border-left:3px solid var(--seal);background:var(--card-hi);}"
    )
    assert seal_state_violations(innocent) == []
    assert_seal_never_signals_state(innocent)


def test_the_wordmark_and_section_rules_keep_their_gold() -> None:
    """Brand usage is the point of having a brand accent at all."""
    for rule in (
        "h1{color:var(--seal);}",
        ".wordmark{color:var(--gold);}",
        ".rulebar{background:linear-gradient(90deg,var(--gold-dim),transparent);}",
        ".provenance b{color:var(--seal);}",
    ):
        assert seal_state_violations(rule) == [], rule


def test_the_check_reports_violations_by_name() -> None:
    """R056 §4 asks for them reported by name, so the message has to carry the name."""
    with pytest.raises(PropertyViolation) as caught:
        assert_seal_never_signals_state(".row.declared_inert .state{color:var(--seal);}")
    assert ".row.declared_inert .state" in str(caught.value)
