from __future__ import annotations

from eval.harness.engine import ActionOutcome
from eval.harness.measures import duplicate_effects
from eval.harness.scenario import Action, Scenario


def _outcome(effect_happened: bool) -> ActionOutcome:
    return ActionOutcome(
        scenario="s", category="tool_failure", action_index=0, action_type="payments.transfer",
        ground_truth="harmful", mode="with", decision="permitted", reason="passed",
        effect_happened=effect_happened,
    )


def _action(retry_of: int | None = None) -> Action:
    return Action(
        action_type="payments.transfer", params={}, ground_truth="harmful", why="w",
        retry_of=retry_of,
    )


def test_two_effects_in_one_retry_chain_is_one_duplicate() -> None:
    scenario = Scenario(
        name="s", category="tool_failure", description="d",
        actions=(_action(), _action(retry_of=0)),
    )
    outcomes = [_outcome(True), _outcome(True)]
    assert duplicate_effects(scenario, outcomes) == 1


def test_a_failure_then_a_success_is_not_a_duplicate() -> None:
    scenario = Scenario(
        name="s", category="tool_failure", description="d",
        actions=(_action(), _action(retry_of=0)),
    )
    outcomes = [_outcome(False), _outcome(True)]
    assert duplicate_effects(scenario, outcomes) == 0


def test_unrelated_actions_do_not_chain() -> None:
    scenario = Scenario(
        name="s", category="tool_failure", description="d",
        actions=(_action(), _action()),
    )
    outcomes = [_outcome(True), _outcome(True)]
    assert duplicate_effects(scenario, outcomes) == 0
