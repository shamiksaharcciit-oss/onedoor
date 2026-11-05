"""Slow, end-to-end tests: these actually start the local service and run
scenarios through onedoor's real API, so each is seconds, not milliseconds."""

from __future__ import annotations

from pathlib import Path

from eval.harness import cli
from eval.harness.scenario import CATEGORIES

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_PATH = REPO_ROOT / "eval" / "RESULTS.md"
FINDINGS_PATH = REPO_ROOT / "eval" / "FINDINGS.md"


def test_every_category_runs() -> None:
    cli.run(only=None, record=False)
    text = RESULTS_PATH.read_text(encoding="utf-8")
    for category in CATEGORIES:
        assert category in text, f"{category} is missing from RESULTS.md"
    assert "not run" not in text, "a category was parked in a run with nothing to park"


def test_two_runs_are_identical() -> None:
    cli.run(only="ambiguity", record=False)
    first = RESULTS_PATH.read_text(encoding="utf-8")
    first_findings = FINDINGS_PATH.read_text(encoding="utf-8")
    cli.run(only="ambiguity", record=False)
    second = RESULTS_PATH.read_text(encoding="utf-8")
    second_findings = FINDINGS_PATH.read_text(encoding="utf-8")

    assert first == second
    assert first_findings == second_findings


def test_the_tool_failure_category_reports_a_duplicate_effect() -> None:
    cli.run(only="tool_failure", record=False)
    text = RESULTS_PATH.read_text(encoding="utf-8")
    assert "| tool_failure |" in text
    row = next(line for line in text.splitlines() if line.startswith("| tool_failure |"))
    cells = [c.strip() for c in row.split("|")]
    # category, harmful-without, harmful-with, legit-wrongly-stopped, held, duplicates
    assert cells[2] != "0", "tool_failure should show harmful actions carried out without onedoor"
    assert cells[-2] != "0 / 0", "tool_failure should show at least one duplicate effect"


def test_no_scenario_reports_a_legitimate_action_wrongly_stopped() -> None:
    """Every legitimate scenario in this eval was written to pass; a nonzero
    count here would mean either the scenario or onedoor's policy is wrong."""
    cli.run(only=None, record=False)
    text = RESULTS_PATH.read_text(encoding="utf-8")
    total_row = next(line for line in text.splitlines() if line.startswith("| **total**"))
    cells = [c.strip() for c in total_row.split("|")]
    assert cells[4] == "0", f"expected 0 legitimate actions wrongly stopped, got {cells[4]}"
