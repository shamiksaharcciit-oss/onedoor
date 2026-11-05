from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from eval.harness.scenario import CATEGORIES, ScenarioError, load_all

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "scenarios"


def test_every_category_has_at_least_four_scenarios() -> None:
    scenarios = load_all(SCENARIOS_DIR)
    counts = Counter(s.category for s in scenarios)
    for category in CATEGORIES:
        assert counts[category] >= 4, f"{category} has only {counts[category]} scenario(s)"


def test_every_category_mixes_harmful_and_legitimate_except_ordinary_work() -> None:
    """``ordinary_work`` is, by this evaluation's own description, "legitimate
    actions within policy, so wrongly stopped actions can be measured" -- all
    legitimate, by design, not a mixed category."""
    scenarios = load_all(SCENARIOS_DIR)
    by_category: dict[str, set[str]] = {c: set() for c in CATEGORIES}
    for s in scenarios:
        for action in s.actions:
            by_category[s.category].add(action.ground_truth)
    for category in CATEGORIES:
        if category == "ordinary_work":
            assert by_category[category] == {"legitimate"}
            continue
        assert by_category[category] == {"harmful", "legitimate"}, (
            f"{category} does not mix ground truths: {by_category[category]}"
        )


def test_scenario_names_are_unique() -> None:
    scenarios = load_all(SCENARIOS_DIR)
    names = [s.name for s in scenarios]
    assert len(names) == len(set(names))


def test_only_filters_to_one_category() -> None:
    scenarios = load_all(SCENARIOS_DIR, only="permits")
    assert scenarios
    assert all(s.category == "permits" for s in scenarios)


def test_an_unknown_category_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: x\ncategory: not_a_real_category\ndescription: d\n"
        "actions: [{action_type: a, params: {}, ground_truth: harmful, why: w}]\n",
        encoding="utf-8",
    )
    with pytest.raises(ScenarioError):
        load_all(tmp_path)


def test_every_action_carries_a_why() -> None:
    scenarios = load_all(SCENARIOS_DIR)
    for s in scenarios:
        for action in s.actions:
            assert action.why.strip(), f"{s.name} has an action with no 'why'"
