"""Renders ``eval/FINDINGS.md``: every place onedoor 0.10.2 let a harmful
action through, wrongly stopped a legitimate one, let an effect happen twice,
or re-proposed an approval that had already expired instead of denying it.
Each finding keeps the scenario and names which backlog item (2-7, or "new")
would address it. Nothing here changes onedoor."""

from __future__ import annotations

from dataclasses import dataclass

from eval.harness.engine import ActionOutcome
from eval.harness.measures import duplicate_effects
from eval.harness.scenario import Action, Scenario

BACKLOG_FOR_CATEGORY = {"tool_failure": "5", "approval": "4"}


def _describe(action: Action) -> str:
    """A plain sentence fragment for one action, built only from its own
    action_type and params -- so a finding's wording stays generated from
    the scenario's own data, not hand-written per scenario."""
    p = action.params
    bits = [action.action_type]
    if "amount_eur" in p:
        bits.append(f"of EUR {p['amount_eur']:.2f}")
    destination = p.get("destination_account")
    recipient = p.get("recipient")
    if destination:
        bits.append(f"to {destination}")
    elif recipient:
        bits.append(f"to {recipient}")
    if "table" in p and "record_id" in p:
        bits.append(f"on {p['table']}/{p['record_id']}")
    return " ".join(bits)


@dataclass(frozen=True)
class Finding:
    scenario: str
    category: str
    what: str
    decision: str
    reason: str
    backlog_item: str


def compute(
    scenarios: list[Scenario], outcomes_with: dict[str, list[ActionOutcome]]
) -> list[Finding]:
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
                        s.name,
                        s.category,
                        f"{_describe(action)} was carried out, decided `{outcome.decision}`.",
                        outcome.decision,
                        outcome.reason,
                        backlog,
                    )
                )
            if outcome.ground_truth == "legitimate" and outcome.decision in ("denied", "refused"):
                findings.append(
                    Finding(
                        s.name,
                        s.category,
                        f"{_describe(action)} was stopped (`{outcome.decision}`), though it "
                        "was legitimate.",
                        outcome.decision,
                        outcome.reason,
                        backlog,
                    )
                )
            if action.approval_ref_from is not None and outcome.decision == "held":
                findings.append(
                    Finding(
                        s.name,
                        s.category,
                        f"{_describe(action)}, presented again past its own approval's "
                        "expiry, re-proposed a fresh approval instead of resolving denied "
                        "(an approval presented after its expiry is treated as absent).",
                        outcome.decision,
                        outcome.reason,
                        "4",
                    )
                )
        if s.category == "tool_failure":
            dup = duplicate_effects(s, outcomes)
            if dup:
                retry_action = next((a for a in s.actions if a.retry_of is not None), None)
                desc = _describe(retry_action) if retry_action is not None else s.name
                findings.append(
                    Finding(
                        s.name,
                        s.category,
                        f"{desc}: the retry was not correlated to the original, so the "
                        f"effect was carried out {dup + 1} time(s).",
                        "n/a",
                        "no retry correlation",
                        "5",
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
