"""V2 / S1 — the policy library: what it reads, what it says, what it refuses to imply.

The read model and the renderer are tested apart because they fail apart. A wrong
sentence is a rendering defect; a row read from the wrong place is a defect about *what
the system is*, and only one of those is visible by looking at the page.
"""

from __future__ import annotations

import re

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Caps, NumericBound, Policy, Tier
from onedoor.store.db import Database
from onedoor.studio import library, screens, shell


@pytest.fixture
def ledger(tmp_path):
    database = Database(str(tmp_path / "onedoor.db"))
    database.init()
    return database.connect()


def _seed(conn) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="payments.transfer",
            tier=Tier.CONFIRM,
            dry_run=False,
            compensating_command="payments.reverse",
            cost_param="amount_eur",
            caps=Caps(eur_day="2000.00"),
            effects=["money.egress"],
            undo_window_seconds=3600,
            bounds=Bounds(
                numeric={"amount_eur": NumericBound(max="500.00")},
                required=["payee", "amount_eur"],
                strict_params=True,
            ),
        ),
    )
    policy_loader.upsert(
        conn,
        Policy(
            action_type="reports.read",
            tier=Tier.OBSERVE,
            dry_run=False,
            compensating_command="",
            bounds=Bounds(strict_params=False),
        ),
    )
    policy_loader.upsert(
        conn,
        Policy(
            action_type="webhooks.post",
            tier=Tier.AUTO_CAPPED,
            dry_run=True,
            compensating_command="webhooks.retract",
            caps=Caps(daily_rate=100),
            bounds=Bounds(enum={"env": ["prod", "stage"]}, strict_params=False),
        ),
    )
    policy_loader.record_snapshot(conn)


# --- What it reads ---------------------------------------------------------------------


def test_the_library_reads_the_snapshot_behind_the_pinned_version(ledger) -> None:
    """R055 V2: *"read the pinned active version."*

    Not the live tables. A page built from the tables would silently disagree with the
    digest in its own header the moment anyone wrote a policy, which is the one
    inconsistency this screen cannot afford: it is the page an auditor uses to say what
    was deployed.
    """
    _seed(ledger)
    model = library.build(ledger)
    assert model.version == policy_loader.current_version(ledger)
    assert [r.action_type for r in model.rows] == [
        "payments.transfer",
        "reports.read",
        "webhooks.post",
    ]


def test_the_library_shows_the_pinned_version_and_not_the_live_tables(ledger) -> None:
    """The distinction that makes this page trustworthy.

    `policy_loader.upsert` records a snapshot on every write, so through that path the
    tables and the pinned version never disagree. **A row written around it can make
    them disagree**, and then the two answers are different facts: the tables are what
    the next snapshot would contain, the pinned version is what the engine is deciding
    against and what the header's digest names.

    Reading the tables would give a library page that contradicts the digest in its own
    header — on the page an auditor uses to say what was deployed.
    """
    _seed(ledger)
    pinned = library.build(ledger)

    # Straight into the table, deliberately bypassing upsert's snapshot.
    ledger.execute(
        "INSERT INTO policies (action_type, tier, bounds_json, caps_json, effects_json,"
        " param_effects_json, dry_run, compensating_command, updated_at)"
        " VALUES ('invoices.send', 0, '{}', '{}', '[]', '[]', 0, '', '2026-08-28T00:00:00Z')"
    )
    after = library.build(ledger)

    assert after.version == pinned.version, "the pinned pointer moved without a snapshot"
    assert "invoices.send" not in [r.action_type for r in after.rows], (
        "the library showed a policy the version in force does not contain"
    )
    assert "invoices.send" in {
        row["action_type"] for row in ledger.execute("SELECT action_type FROM policies")
    }, "the fixture did not actually create a disagreement, so this test proved nothing"


def test_an_unretrievable_snapshot_is_not_reported_as_an_empty_policy_set(
    ledger, monkeypatch
) -> None:
    """**The one error this page must never make.**

    Three outcomes: no version, a version whose snapshot cannot be read, and a real set.
    Collapsing the middle into the first would tell an operator that nothing is
    permitted while the engine is permitting things right now.
    """
    _seed(ledger)
    monkeypatch.setattr(policy_loader, "snapshot_for", lambda *a, **k: None)
    model = library.build(ledger)
    assert model.version is not None
    assert model.retrievable is False
    assert model.rows == ()

    html = screens.library_body(model)
    assert "not retrievable" in html
    assert "not an empty policy set" in html
    assert library.NO_VERSION not in html, "an unreadable snapshot was rendered as no version"


def test_no_version_in_force_says_nothing_is_permitted(ledger) -> None:
    model = library.build(ledger)
    assert model.version is None and model.retrievable is True
    assert "the default is denial" in screens.library_body(model)


# --- The chip, which is a claim about what the engine will decide -----------------------


def test_a_dry_run_rule_is_not_shown_as_allowed(ledger) -> None:
    """`dry_run` outranks the tier. A rule that would permit but runs dry permits
    nothing, and `allowed` would be the screen making a promise the engine is not
    keeping."""
    _seed(ledger)
    rows = {r.action_type: r for r in library.build(ledger).rows}
    assert rows["webhooks.post"].dry_run is True
    assert rows["webhooks.post"].tier is Tier.AUTO_CAPPED
    assert rows["webhooks.post"].state == "review"


def test_a_confirm_rule_is_shown_as_review_and_an_observe_rule_as_allowed(ledger) -> None:
    _seed(ledger)
    rows = {r.action_type: r for r in library.build(ledger).rows}
    assert rows["payments.transfer"].state == "review"
    assert rows["reports.read"].state == "allow"


def test_the_tier_column_carries_what_the_chip_approximates(ledger) -> None:
    """Three chips over four tiers means one is approximate; the exact answer must be
    on the same row. `OBSERVE` wears `allowed` and performs nothing, so a reader who
    needs the difference has to be able to find it without leaving the table."""
    _seed(ledger)
    html = screens.library_body(library.build(ledger))
    for tier in ("CONFIRM", "OBSERVE", "AUTO_CAPPED"):
        assert f">{tier}<" in html


def test_every_tier_the_engine_declares_has_a_sentence() -> None:
    """A tier added to the engine with no phrase here would render an empty sentence —
    the screen going quiet exactly where it should be most specific (X-14)."""
    assert set(library.TIER_WORDS) == set(Tier)


def test_there_is_no_deny_tier_to_render() -> None:
    """Refusal is not an autonomy level in this engine; it comes from default-deny,
    bounds, caps or the kill switch. A `Tier.DENY` in this table would teach a model of
    the engine that the engine does not have."""
    assert not hasattr(Tier, "DENY")


# --- The sentences ----------------------------------------------------------------------


def test_every_sentence_comes_from_a_field(ledger) -> None:
    """A rendering that adds a clause the policy does not contain is a rendering that
    will be trusted for a guarantee nobody wrote."""
    _seed(ledger)
    bare = library.policy_at(ledger, "reports.read")
    assert library.sentences(bare) == ("`reports.read` is recorded and never carried out.",)


def test_the_dry_run_sentence_says_the_action_is_not_carried_out(ledger) -> None:
    _seed(ledger)
    said = " ".join(library.sentences(library.policy_at(ledger, "webhooks.post")))
    assert "not carried out" in said
    assert "recorded" in said


def test_caps_and_bounds_are_spelled_exactly(ledger) -> None:
    _seed(ledger)
    said = " ".join(library.sentences(library.policy_at(ledger, "payments.transfer")))
    assert "EUR 2000/day" in said
    assert "amount_eur ≤ 500" in said
    assert "requires payee, amount_eur" in said
    assert "no other parameters" in said
    assert "cumulatively" in said, "a cap that does not say it is cumulative invites a misread"


def test_no_number_reaches_the_page_through_a_float(ledger) -> None:
    """E8: canonical decimals, shortest-exact, never binary floating point.

    The engine's own models canonicalise to strings; this asserts the screen does not
    undo that on the way out.
    """
    _seed(ledger)
    policy = library.policy_at(ledger, "payments.transfer")
    rendered = library.yaml_text(policy) + " ".join(library.sentences(policy))
    assert "2000.0000" not in rendered
    assert "499.99999" not in rendered
    assert "e+" not in rendered.lower()


def test_an_undeclared_bound_does_not_appear_as_null(ledger) -> None:
    """R015: null and empty differ, and *undeclared* is neither.

    `NumericBound(max=...)` dumps a `min` of null. Rendering it would show an operator a
    bound they never wrote, on the page that exists to tell them what their rules say.
    """
    _seed(ledger)
    text = library.yaml_text(library.policy_at(ledger, "payments.transfer"))
    assert "null" not in text
    assert '"max": "500"' in text
    assert '"min"' not in text


def test_the_rule_pane_shows_something_the_engine_would_load(ledger) -> None:
    """JSON is a subset of YAML, so what is shown is loadable as written — the property
    that matters more than the file extension."""
    import json

    _seed(ledger)
    text = library.yaml_text(library.policy_at(ledger, "payments.transfer"))
    parsed = json.loads(text)
    assert parsed["action_type"] == "payments.transfer"
    assert parsed["tier"] == int(Tier.CONFIRM)


# --- What the page must say, and must not imply -----------------------------------------


def test_the_absence_is_denial_sentence_is_on_the_library_page(ledger) -> None:
    """R055 V2 requires it, and the reason is the misreading the page invites: a reader
    who sees permissive-looking rows infers a permissive system."""
    _seed(ledger)
    html = screens.library_body(library.build(ledger))
    assert library.ABSENCE_IS_DENIAL in html
    assert "denied" in library.ABSENCE_IS_DENIAL


def test_a_policy_absent_from_the_version_in_force_is_a_fact_not_a_404(ledger) -> None:
    _seed(ledger)
    html = screens.not_found_body("payments.refund")
    assert "denied" in html
    assert "only what is deployed now" in html


def test_the_coverage_badge_carries_a_word_and_never_only_a_colour(ledger) -> None:
    """The same law the chips follow. `declared_inert` sounds fine and behaves
    dangerously; a badge that carried only a hue would lose exactly that."""
    _seed(ledger)
    html = screens.library_body(library.build(ledger))
    for state, (word, _why) in screens.COVERAGE_WORDS.items():
        assert word, f"{state} has no word"
    assert re.search(r'class="badge"[^>]*>[a-z ,]+<', html)


def test_every_coverage_state_the_model_declares_has_a_word() -> None:
    from onedoor.studio import coverage as coverage_model

    assert set(screens.COVERAGE_WORDS) == set(coverage_model.PROMINENCE)


def test_an_action_type_cannot_smuggle_markup_onto_the_page(ledger) -> None:
    """Action types come from a store the Studio opens by filename, so they are
    attacker-shaped by the same argument that applies to params."""
    hostile = "pay<script>alert(1)</script>"
    policy_loader.upsert(
        ledger,
        Policy(
            action_type=hostile,
            tier=Tier.OBSERVE,
            dry_run=False,
            compensating_command="",
            bounds=Bounds(strict_params=False),
        ),
    )
    policy_loader.record_snapshot(ledger)
    html = screens.library_body(library.build(ledger))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html

    detail = screens.policy_body(library.policy_at(ledger, hostile), library.build(ledger))
    assert "<script>alert(1)</script>" not in detail


def test_the_sentence_formatter_escapes_before_it_marks_up() -> None:
    """Order is the security property: marking up first would let a policy's own name
    close a tag."""
    assert "<b>" not in screens._inline("a <b>bold</b> action")
    assert "<code>x</code>" in screens._inline("`x`")
    assert "<strong>y</strong>" in screens._inline("**y**")


def test_the_library_page_renders_inside_the_shell_and_reaches_nowhere(ledger) -> None:
    _seed(ledger)
    html = shell.render(
        body=screens.library_body(library.build(ledger)),
        banner=shell.Banner("a" * 64, "2026-08-28", 3, 1),
        active="policies",
    )
    assert 'aria-current="page"' in html
    assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html)
