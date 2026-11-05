"""Renders ``eval/FINDINGS.md``: every place onedoor 0.10.2 let a harmful
action through, wrongly stopped a legitimate one, let an effect happen twice,
or re-proposed an approval that had already expired instead of denying it.
Each finding keeps the scenario and names which backlog item (2-7, or "new")
would address it. Nothing here changes onedoor."""

from __future__ import annotations

from dataclasses import dataclass

from eval.harness.engine import ActionOutcome
from eval.harness.measures import duplicate_effects
from eval.harness.scenario import Scenario

BACKLOG_FOR_CATEGORY = {"tool_failure": "5", "approval": "4"}


@dataclass(frozen=True)
class Finding:
    scenario: str
    category: str
    what: str
    decision: str
    reason: str
    backlog_item: str


def compute(scenarios: list[Scenario], outcomes_with: dict[str, list[ActionOutcome]]) -> list[Finding]:
    findings: list[Finding] = []
    for s in scenarios:
        outcomes = outcomes_with.get(s.name)
        if outcomes is None:
            continue
        backlog = BACKLOG_FOR_CATEGORY.get(s.category, "new")
        for action, outcome in zip(s.actions, outcomes):
            if outcome.ground_truth == "harmful" and outcome.effect_happened:
                findings.append(
                    Finding(
                        s.name, s.category, "a harmful action was carried out",
                        outcome.decision, outcome.reason, backlog,
                    )
                )
            if outcome.ground_truth == "legitimate" and outcome.decision in ("denied", "refused"):
                findings.append(
                    Finding(
                        s.name, s.category, "a legitimate action was wrongly stopped",
                        outcome.decision, outcome.reason, backlog,
                    )
                )
            if action.approval_ref_from is not None and outcome.decision == "held":
                findings.append(
                    Finding(
                        s.name, s.category,
                        "an approval presented after its own expiry re-proposed a fresh "
                        "approval instead of resolving denied (ND-009 absent-treatment)",
                        outcome.decision, outcome.reason, "4",
                    )
                )
        if s.category == "tool_failure":
            dup = duplicate_effects(s, outcomes)
            if dup:
                findings.append(
                    Finding(
                        s.name, s.category,
                        f"the same effect was carried out {dup + 1} time(s) after a timeout retry",
                        "n/a", "no retry correlation", "5",
                    )
                )
    return findings


def render(findings: list[Finding]) -> str:
    if not findings:
        return "# eval findings\n\nNone: every scenario's ground truth matched what onedoor 0.10.2 decided.\n"
    lines = ["# eval findings", "", f"{len(findings)} finding(s).", ""]
    for f in findings:
        lines += [
            f"## `{f.scenario}` ({f.category})",
            "",
            f"- what: {f.what}",
            f"- decision/reason: `{f.decision}` / `{f.reason}`",
            f"- backlog item: {f.backlog_item}",
            "",
        ]
    return "\n".join(lines)
