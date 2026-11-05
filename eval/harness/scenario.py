"""Scenarios as data: one YAML file per scenario under ``eval/scenarios/``.

A scenario is a name, a category, a plain-words description, and a script of
proposed actions. Each action carries its ground truth (``harmful`` or
``legitimate``) and the one-line reason the label is right, plus whatever a
category needs to script a tool outcome, an approval answer, a kill-switch
state, or a permit's shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CATEGORIES = (
    "ambiguity",
    "conflicting_constraints",
    "tool_failure",
    "permits",
    "injected_instruction",
    "approval",
    "kill_switch",
    "ordinary_work",
)

GROUND_TRUTHS = ("harmful", "legitimate")


class ScenarioError(ValueError):
    """A scenario file is missing a required field or names an unknown value."""


@dataclass(frozen=True)
class Action:
    action_type: str
    params: dict[str, Any]
    ground_truth: str
    why: str
    tool_outcome: str = "success"  # success | timeout | failure
    source: str = "llm"
    approve: str | None = None  # "grant" | "deny" | None (left pending)
    kill_switch: bool | None = None  # set before this action, if not None
    permit: str | None = None  # "fresh" | "reuse_prior" | "wrong_recipient" | "expired"
    retry_of: int | None = None  # index into the scenario's own actions, 0-based
    approval_ref_from: int | None = None  # present that action's approval_id as approval_ref
    wait_seconds: float = 0.0  # a real sleep before this action, so its approval can expire

    def __post_init__(self) -> None:
        if self.ground_truth not in GROUND_TRUTHS:
            raise ScenarioError(f"unknown ground_truth {self.ground_truth!r}")
        if self.tool_outcome not in ("success", "timeout", "failure"):
            raise ScenarioError(f"unknown tool_outcome {self.tool_outcome!r}")
        if self.approve not in (None, "grant", "deny"):
            raise ScenarioError(f"unknown approve {self.approve!r}")
        if self.permit not in (None, "fresh", "reuse_prior", "wrong_recipient", "expired"):
            raise ScenarioError(f"unknown permit {self.permit!r}")


@dataclass(frozen=True)
class Scenario:
    name: str
    category: str
    description: str
    actions: tuple[Action, ...] = field(default_factory=tuple)
    path: Path | None = None

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ScenarioError(f"{self.name}: unknown category {self.category!r}")
        if not self.actions:
            raise ScenarioError(f"{self.name}: no actions")


def _load_one(path: Path) -> Scenario:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        actions = tuple(Action(**a) for a in raw["actions"])
        return Scenario(
            name=raw["name"],
            category=raw["category"],
            description=raw["description"],
            actions=actions,
            path=path,
        )
    except (KeyError, TypeError) as exc:
        raise ScenarioError(f"{path}: {exc}") from exc


def load_all(scenarios_dir: Path, *, only: str | None = None) -> list[Scenario]:
    """Every ``*.yaml`` file under ``scenarios_dir``, sorted by filename so a run's
    order never depends on filesystem iteration order."""
    scenarios = [_load_one(p) for p in sorted(scenarios_dir.glob("*.yaml"))]
    if only is not None:
        scenarios = [s for s in scenarios if s.category == only]
    names = [s.name for s in scenarios]
    if len(names) != len(set(names)):
        dupes = {n for n in names if names.count(n) > 1}
        raise ScenarioError(f"duplicate scenario name(s): {sorted(dupes)}")
    return scenarios
