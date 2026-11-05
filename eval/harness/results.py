"""Renders ``eval/RESULTS.md``. Written only by the runner -- never by hand --
so two runs produce byte-identical output apart from the date line."""

from __future__ import annotations

from dataclasses import dataclass

from eval.harness.engine import ActionOutcome
from eval.harness.measures import Totals
from eval.harness.scenario import Scenario

FIELDS = (
    ("harmful_carried_out_without", "harmful, without onedoor"),
    ("harmful_carried_out_with", "harmful, with onedoor"),
    ("legitimate_wrongly_stopped_with", "legitimate, wrongly stopped"),
    ("held_for_person_with", "held for a person"),
)


@dataclass
class RunMeta:
    onedoor_version: str
    onedoor_commit: str
    run_date: str  # YYYY-MM-DD


def _scenario_line(
    s: Scenario, outcomes_without: list[ActionOutcome], outcomes_with: list[ActionOutcome]
) -> str:
    n = len(s.actions)
    eff_wo = sum(1 for o in outcomes_without if o.effect_happened)
    eff_wi = sum(1 for o in outcomes_with if o.effect_happened)
    decisions = ", ".join(f"{o.decision}" for o in outcomes_with)
    return f"- `{s.name}` ({n} action(s)): effects without onedoor {eff_wo}/{n}, with onedoor {eff_wi}/{n} -- {decisions}"


def render(
    *,
    meta: RunMeta,
    scenarios: list[Scenario],
    outcomes_without: dict[str, list[ActionOutcome]],
    outcomes_with: dict[str, list[ActionOutcome]],
    totals: Totals,
    record_verify_line: str | None,
) -> str:
    lines = [
        "# eval results",
        "",
        f"onedoor {meta.onedoor_version} ({meta.onedoor_commit}), run on {meta.run_date}.",
        "",
        "Wording: \"stopped\" (denied or refused outright), \"held\" (proposed, "
        "awaiting a person), \"carried out\" (the simulated tool recorded an "
        "effect). Numbers only; no claim beyond what a scenario measured.",
        "",
        "## Totals",
        "",
        "| category | " + " | ".join(label for _, label in FIELDS) + " | duplicate effects (without / with) |",
        "|---" * (len(FIELDS) + 2) + "|",
    ]
    categories = sorted(totals.categories)
    for category in categories:
        m = totals.categories[category]
        if m.not_run:
            lines.append(f"| {category} | not run -- {m.not_run_reason} | | | | |")
            continue
        cells = " | ".join(str(getattr(m, field_name)) for field_name, _ in FIELDS)
        lines.append(
            f"| {category} | {cells} | {m.duplicate_effects_without} / {m.duplicate_effects_with} |"
        )
    total_cells = " | ".join(str(totals.total(field_name)) for field_name, _ in FIELDS)
    lines.append(
        f"| **total** | {total_cells} | {totals.total('duplicate_effects_without')} / "
        f"{totals.total('duplicate_effects_with')} |"
    )
    if record_verify_line:
        lines += ["", record_verify_line]
    lines += ["", "## Scenarios", ""]
    for s in scenarios:
        if s.name not in outcomes_with:
            lines.append(f"- `{s.name}` ({s.category}): not run")
            continue
        lines.append(_scenario_line(s, outcomes_without[s.name], outcomes_with[s.name]))
    lines.append("")
    return "\n".join(lines)
