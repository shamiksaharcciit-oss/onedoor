"""V7 / S2 — the editor: two panes over one object, inside a draft, never near the live rules.

The tests fall into three groups. **Sync** — the panes cannot disagree, because there is
nothing to disagree between. **The fence** — nothing here writes to the enforcer store.
**The note** — ND-054's divergence is described as the engine behaves *today*, with no
hedge toward a fix that has not happened.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Caps, NumericBound, Policy, Tier
from onedoor.studio import editor, screens, server, store


def _rule(**kw) -> Policy:
    base = dict(
        action_type="payments.transfer",
        tier=Tier.CONFIRM,
        dry_run=False,
        compensating_command="payments.reverse",
        cost_param="amount_eur",
        caps=Caps(eur_day="500.00"),
        bounds=Bounds(
            numeric={"amount_eur": NumericBound(max="500.00")},
            required=["amount_eur"],
            strict_params=True,
        ),
    )
    base.update(kw)
    return Policy(**base)  # type: ignore[arg-type]


@pytest.fixture
def state(tmp_path):
    st = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    policy_loader.upsert(st.enforcer, _rule())
    return st


@pytest.fixture
def draft(state):
    d = server.new_draft(state, title="edit me")
    return state, store.load(state.studio, d.draft_id)


# --- Sync ------------------------------------------------------------------------------


def test_both_panes_are_rendered_from_one_object() -> None:
    """**"Always in sync" is true by construction, not maintained.**

    Syncing client-side would need a second implementation of the policy parser, in
    another language, and the two would disagree on exactly the inputs this engine cares
    about — decimal strings, unicode, key order, null against absent. R062 §1's law.
    """
    policy = _rule()
    fields = {f.name: f.value for f in editor.fields_for(policy)}
    raw = json.loads(editor.raw_for(policy))
    assert fields["action_type"] == raw["action_type"]
    assert fields["tier"] == str(raw["tier"])
    assert fields["caps.eur_day"] == raw["caps"]["eur_day"]


def test_the_editor_holds_no_second_parser() -> None:
    """Asserted structurally, the same fence the replay carries: the module must not
    grow a JavaScript mirror or a YAML writer of its own."""
    import inspect

    source = inspect.getsource(editor)
    for smell in ("<script", "yaml.dump", "def _parse_yaml"):
        assert smell not in source, f"a second implementation is growing: {smell}"


def test_a_form_round_trip_is_stable() -> None:
    policy = _rule()
    fields = {f.name: [f.value] for f in editor.fields_for(policy)}
    assert editor.raw_for(editor.policy_from_form(fields, base=policy)) == editor.raw_for(policy)


def test_a_raw_round_trip_is_stable() -> None:
    policy = _rule()
    assert editor.raw_for(
        editor.policy_from_raw(editor.raw_for(policy), base=policy)
    ) == editor.raw_for(policy)


def test_the_raw_pane_shows_something_the_engine_would_load() -> None:
    """JSON is a subset of YAML, so what is shown is loadable as written."""
    parsed = json.loads(editor.raw_for(_rule()))
    assert Policy.model_validate({**_rule().model_dump(), **parsed})


def test_saving_from_the_form_keeps_fields_the_form_never_showed() -> None:
    """**A partial editor that writes a whole object deletes what it never displayed.**

    The form is a declared subset; rebuilding from it alone would silently drop the rest.
    """
    policy = _rule(is_default_deny=True, dry_run_until=None)
    assert "is_default_deny" in editor.NOT_IN_THE_FORM
    fields = {f.name: [f.value] for f in editor.fields_for(policy)}
    updated = editor.policy_from_form(fields, base=policy)
    assert updated.is_default_deny is True, "a field the form does not show was dropped"


def test_the_page_names_the_fields_the_form_does_not_offer(draft) -> None:
    """A reader must be able to find out which subset without diffing two renderings."""
    state, d = draft
    html = screens.editor_body(d, _rule(), [])
    for field in editor.NOT_IN_THE_FORM:
        assert field in html


# --- Decimals, and the ND-054 note ---------------------------------------------------------


def test_no_decimal_is_routed_through_a_float() -> None:
    """E8, and the shape of the defect ND-054 was raised about, met from the other side."""
    updated = editor.policy_from_form({"caps.eur_day": ["0.1"]}, base=_rule())
    assert updated.caps.eur_day == Decimal("0.1")
    assert updated.caps.eur_day != Decimal(str(0.1 + 0.2 - 0.2))


def test_a_value_that_is_not_a_decimal_is_refused_by_name() -> None:
    with pytest.raises(editor.EditError, match="not a decimal number"):
        editor.policy_from_form({"caps.eur_day": ["12.3.4"]}, base=_rule())


def test_the_nd054_note_appears_at_every_decimal_field() -> None:
    """R055 V7: the divergence is NOTED at the decimal fields."""
    noted = {f.name for f in editor.fields_for(_rule()) if f.note}
    assert noted == set(editor.DECIMAL_FIELDS)


def test_the_note_describes_what_the_engine_does_today(draft) -> None:
    """R062 §5, and the sharpest constraint on this stage.

    **A note that describes tomorrow's behaviour is aspiration dressed as capability,
    one field at a time.** So the note says what happens now, and says nothing about a
    fix — no "will be", no "until", no ticket number promising relief.
    """
    note = editor.DECIMAL_DIVERGENCE
    assert "today" in note
    assert "changes which wire types that action accepts" in note
    for hedge in ("will be", "soon", "until", "ND-054", "planned", "fixed", "upcoming"):
        assert hedge.lower() not in note.lower(), f"the note hedges toward a fix: {hedge!r}"


def test_the_note_matches_the_behaviour_the_frozen_ticket_measured() -> None:
    """The wording is drawn from `TICKETS-ND-054.md` §3, which measured it on shipped
    code. A note that drifted from the measurement would be a note about nothing."""
    from pathlib import Path

    ticket = Path(__file__).resolve().parents[2] / "TICKETS-ND-054.md"
    # Whitespace-normalised and de-emphasised: the ticket wraps the sentence across a
    # line and bolds it, and neither is a change to what it says.
    text = " ".join(ticket.read_text(encoding="utf-8").replace("**", "").split())
    assert "Adding a bound changes which wire types the action accepts" in text
    assert "changes which wire types that action accepts" in editor.DECIMAL_DIVERGENCE


def test_the_note_is_shown_to_the_reader(draft) -> None:
    from tests.viewer.assertions import assert_reader_sees

    state, d = draft
    assert_reader_sees(screens.editor_body(d, _rule(), []), editor.DECIMAL_DIVERGENCE)


# --- Refusals ------------------------------------------------------------------------------


def test_unparseable_json_is_refused_with_where(draft) -> None:
    with pytest.raises(editor.EditError, match="not valid JSON"):
        editor.policy_from_raw("{nope", base=_rule())


def test_a_list_is_not_a_rule() -> None:
    with pytest.raises(editor.EditError, match="must be an object"):
        editor.policy_from_raw("[1, 2]", base=_rule())


def test_a_numeric_bound_that_is_not_understood_says_how_to_write_one() -> None:
    """A permissive parser would guess, and a guess about a bound is a guess about what
    the engine will refuse."""
    with pytest.raises(editor.EditError, match="amount_eur max 500"):
        editor.policy_from_form({"bounds.numeric": ["amount_eur 500"]}, base=_rule())


def test_a_refusal_says_the_draft_is_unchanged(draft) -> None:
    state, d = draft
    html = screens.editor_body(d, _rule(), [], error="the rule is not valid JSON")
    assert "not saved" in html
    assert "The draft is unchanged" in html
    assert "Nothing was written" in html


# --- The fence -------------------------------------------------------------------------------


def test_the_editor_module_never_touches_the_enforcer_store() -> None:
    """Fence post one, asserted structurally: the module imports nothing that can write
    live rules, and calls nothing named like it.

    Checked over the **parsed module**, not its text. The first version scanned the
    source and failed on the docstring sentence *"`policy_loader.upsert` is never
    called"* — condemning the module for documenting the very fence it keeps. That is
    R058 §4's law arriving a second time: **a checker must parse the language it checks,
    not the prose around it.**
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(editor))
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    for module in imported:
        assert "policy_loader" not in module, f"the editor imports {module}"
        assert "ratify" not in module, f"the editor imports {module}"

    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    for forbidden in ("upsert", "upsert_effect", "record_snapshot", "ratify"):
        assert forbidden not in called, f"the editor calls {forbidden}"


def test_editing_changes_the_draft_and_not_the_rules_in_force(state) -> None:
    """The property the whole two-store split exists for, checked end to end."""
    d = server.new_draft(state, title="edit me")
    before = policy_loader.current_version(state.enforcer)
    live_caps = state.enforcer.execute("SELECT caps_json FROM policies").fetchone()[0]

    base = next(p for p in store.load(state.studio, d.draft_id).policies)
    updated = editor.policy_from_form({"caps.eur_day": ["9999.00"]}, base=base)
    server.save_draft(state, d.draft_id, policies=[updated], effects=[])

    assert policy_loader.current_version(state.enforcer) == before
    assert state.enforcer.execute("SELECT caps_json FROM policies").fetchone()[0] == live_caps
    saved = store.load(state.studio, d.draft_id)
    assert saved.policies[0].caps.eur_day == Decimal("9999.00")


def test_the_page_says_the_rules_in_force_are_untouched(draft) -> None:
    state, d = draft
    html = screens.editor_body(d, _rule(), [])
    assert "rules in force are not touched" in html


def test_the_honesty_footnote_rides_the_editors_validation(draft) -> None:
    """R055 V5's requirement follows the validator wherever it renders."""
    from onedoor.studio import validate
    from tests.viewer.assertions import assert_reader_sees

    state, d = draft
    assert_reader_sees(screens.editor_body(d, _rule(), []), validate.INCOMPLETE_NOTICE)


def test_operator_text_cannot_smuggle_markup_into_either_pane(draft) -> None:
    state, d = draft
    hostile = _rule(action_type="pay<script>alert(1)</script>")
    html = screens.editor_body(d, hostile, [])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_the_editor_page_reaches_nowhere(draft) -> None:
    state, d = draft
    html = screens.editor_body(d, _rule(), [])
    assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html)
