"""`ND-056` / T1 — the staged validator: one case per stage, and the stage that stops.

Each stage is proven reached **and** proven to have stopped the stages after it. A test
that only asserted "there is a refusal" would pass on a validator that ran every stage
and reported the last one, which is the shape this module exists not to be: a refusal
computed against an object an earlier stage could not build is a statement about nothing.
"""

from __future__ import annotations

import pytest

from onedoor.studio import staging

GOOD = """
policies:
  - action_type: payments.transfer
    tier: 2
    compensating_command: payments.refund
    cost_param: amount_eur
    bounds:
      required: [amount_eur]
      numeric:
        amount_eur: {min: 0, max: 500}
  - action_type: payments.refund
    tier: 2
    compensating_command: payments.transfer
effects:
  money.egress:
    min_tier: 2
"""


def test_a_clean_candidate_runs_every_stage_and_refuses_nothing() -> None:
    result = staging.staged(GOOD)
    assert result.refusals == ()
    assert result.stopped_at is None
    assert result.stages_run == staging.STAGES
    assert result.stages_not_run == ()
    assert result.loads is True
    assert [p.action_type for p in result.policies] == [
        "payments.transfer",
        "payments.refund",
    ]
    assert [e.effect for e in result.effects] == ["money.egress"]


# --- one case per stage, each stopping the rest ------------------------------------


def test_stage_load_catches_yaml_syntax_and_stops_everything_after_it() -> None:
    result = staging.staged("policies:\n  - action_type: [unclosed\n")
    assert result.stopped_at == staging.STAGE_LOAD
    assert result.stages_run == (staging.STAGE_LOAD,)
    assert result.stages_not_run == (
        staging.STAGE_SCHEMA,
        staging.STAGE_RULES,
        staging.STAGE_EFFECTS,
    )
    assert result.policies == ()
    assert len(result.refusals) == 1
    assert result.refusals[0].stage == staging.STAGE_LOAD


def test_stage_load_catches_a_file_that_is_not_a_mapping() -> None:
    result = staging.staged("- just\n- a\n- list\n")
    assert result.stopped_at == staging.STAGE_LOAD
    assert "must be a mapping" in result.refusals[0].message
    # A statement about the document, so no line number is invented for it.
    assert result.refusals[0].position.state == staging.ABSENT


def test_stage_load_catches_a_non_finite_number_which_is_the_loaders_own_refusal() -> None:
    result = staging.staged("policies:\n  - action_type: a\n    tier: 2\n    x: .inf\n")
    assert result.stopped_at == staging.STAGE_LOAD
    assert "non-finite" in result.refusals[0].message
    assert result.refusals[0].position.state == staging.RESOLVED


def test_stage_schema_catches_a_bad_field_and_stops_the_rules_stage() -> None:
    result = staging.staged("policies:\n  - action_type: a.b\n    tier: 99\n")
    assert result.stopped_at == staging.STAGE_SCHEMA
    assert result.stages_not_run == (staging.STAGE_RULES, staging.STAGE_EFFECTS)
    assert result.policies == ()
    assert any(r.action_type == "a.b" for r in result.refusals)
    assert any("tier" in r.message for r in result.refusals)


def test_stage_schema_reports_every_error_in_the_entry_not_only_the_first() -> None:
    # Pydantic collects per entry, so the schema stage does too. The per-rule
    # first-failure limit belongs to `validate_policy`, at the rules stage.
    result = staging.staged("policies:\n  - action_type: a.b\n    tier: 99\n    dry_run: maybe\n")
    assert result.stopped_at == staging.STAGE_SCHEMA
    fields = " ".join(r.message for r in result.refusals)
    assert "tier" in fields and "dry_run" in fields


def test_stage_schema_catches_an_unknown_field_because_the_model_forbids_extras() -> None:
    result = staging.staged("policies:\n  - action_type: a.b\n    tier: 3\n    teir: 2\n")
    assert result.stopped_at == staging.STAGE_SCHEMA
    assert any("teir" in r.message for r in result.refusals)


def test_stage_effects_is_last_because_that_is_where_load_file_builds_them() -> None:
    text = "policies:\n  - action_type: a.b\n    tier: 3\neffects:\n  money.egress:\n    min_tier: 42\n"
    result = staging.staged(text)
    assert result.stopped_at == staging.STAGE_EFFECTS
    # Effects run fourth, so failing there stops nothing after it -- every earlier stage
    # already ran and passed.
    assert result.stages_run == staging.STAGES
    assert result.stages_not_run == ()
    # The policies parsed; they are carried so the caller can still render them.
    assert [p.action_type for p in result.policies] == ["a.b"]
    assert result.effects == ()
    assert "money.egress" in result.refusals[0].message


def test_stage_rules_is_the_engines_own_refusal_reached_last() -> None:
    # Tier 2 with no compensating_command: policy_loader.validate_policy's own rule.
    result = staging.staged("policies:\n  - action_type: a.b\n    tier: 2\n")
    assert result.stopped_at == staging.STAGE_RULES
    assert result.stages_run == (
        staging.STAGE_LOAD,
        staging.STAGE_SCHEMA,
        staging.STAGE_RULES,
    )
    assert result.stages_not_run == (staging.STAGE_EFFECTS,)
    assert result.refusals[0].action_type == "a.b"
    assert "compensating_command" in result.refusals[0].message


def test_a_candidate_bad_in_two_stages_reports_the_stage_the_loader_reaches_first() -> None:
    """The regression test for this module's own defect.

    Both defects are real: `min_tier: 42` is not a tier, and a Tier 2 rule with no
    reversal is refused by `validate_policy`. `load_file` validates every policy BEFORE
    it constructs the effect policies, so the engine stops at `rules`. The first version
    of this module ordered effects third and would have answered `effects` — naming a
    stage the loader would never have reached on this file.
    """
    text = (
        "policies:\n"
        "  - action_type: a.b\n"
        "    tier: 2\n"
        "effects:\n"
        "  money.egress:\n"
        "    min_tier: 42\n"
    )
    result = staging.staged(text)
    assert result.stopped_at == staging.STAGE_RULES
    assert result.stages_not_run == (staging.STAGE_EFFECTS,)
    assert all(r.stage == staging.STAGE_RULES for r in result.refusals)


def test_stage_rules_catches_cost_param_absent_from_bounds_required() -> None:
    text = "policies:\n  - action_type: a.b\n    tier: 3\n    cost_param: amount_eur\n"
    result = staging.staged(text)
    assert result.stopped_at == staging.STAGE_RULES
    assert "bounds.required" in result.refusals[0].message


def test_the_rules_stage_reports_one_failure_per_rule_which_is_the_documented_limit() -> None:
    # Two rules, each with two defects. The engine stops at the first per rule, so two
    # refusals, not four -- and INCOMPLETE_NOTICE is what says so on the page.
    text = (
        "policies:\n"
        "  - action_type: a.b\n"
        "    tier: 2\n"
        "    cost_param: amount_eur\n"
        "  - action_type: c.d\n"
        "    tier: 1\n"
        "    cost_param: amount_eur\n"
    )
    result = staging.staged(text)
    assert len(result.refusals) == 2
    assert {r.action_type for r in result.refusals} == {"a.b", "c.d"}


# --- positions: three outcomes, and never a fabricated line 1 -----------------------


def test_a_resolved_position_points_at_the_rule_that_carries_the_problem() -> None:
    text = (
        "policies:\n"
        "  - action_type: first.ok\n"
        "    tier: 3\n"
        "  - action_type: second.bad\n"
        "    tier: 2\n"
    )
    result = staging.staged(text)
    refusal = next(r for r in result.refusals if r.action_type == "second.bad")
    assert refusal.position.state == staging.RESOLVED
    # The second rule begins on line 4 of the document, not line 1.
    assert refusal.position.line == 4
    assert "line 4" in refusal.position.describe()


def test_a_position_state_that_is_not_resolved_may_not_carry_a_line() -> None:
    # The fabricated-line-1 defect, refused by the type itself rather than by review.
    with pytest.raises(ValueError, match="only a resolved position"):
        staging.Position(staging.UNRESOLVED, line=1)
    with pytest.raises(ValueError, match="only a resolved position"):
        staging.Position(staging.ABSENT, line=1, column=1)


def test_a_resolved_position_must_carry_a_line() -> None:
    with pytest.raises(ValueError, match="must carry a line"):
        staging.Position(staging.RESOLVED)


def test_an_unknown_position_state_is_refused() -> None:
    with pytest.raises(ValueError, match="position state must be"):
        staging.Position("probably line 1")


def test_the_three_position_states_are_declared_and_distinct() -> None:
    assert staging.POSITION_STATES == (staging.RESOLVED, staging.UNRESOLVED, staging.ABSENT)
    assert len(set(staging.POSITION_STATES)) == 3


def test_every_stage_has_a_label_and_the_labels_are_derived_from_the_stage_list() -> None:
    assert tuple(staging.STAGE_LABELS) == staging.STAGES


def test_a_refusal_serialises_with_its_stage_and_position() -> None:
    result = staging.staged("policies:\n  - action_type: a.b\n    tier: 2\n")
    obj = result.to_object()
    assert obj["stopped_at"] == staging.STAGE_RULES
    assert obj["refusals"][0]["stage"] == staging.STAGE_RULES
    assert obj["refusals"][0]["position"]["state"] == staging.RESOLVED
    # The honesty notice travels with the data, not only with the HTML.
    assert obj["incomplete_notice"]


def test_an_empty_document_loads_and_refuses_nothing() -> None:
    result = staging.staged("")
    assert result.loads is True
    assert result.policies == ()
