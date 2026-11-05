"""Addendum step 7: --record, end to end against the real onetrace package."""

from __future__ import annotations

import shutil
from pathlib import Path

from eval.harness import cli

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_DIR = REPO_ROOT / "eval" / "runs"
RESULTS_PATH = REPO_ROOT / "eval" / "RESULTS.md"


def _clear_runs() -> None:
    if RUNS_DIR.exists():
        shutil.rmtree(RUNS_DIR)


def test_record_writes_one_run_per_settling_scenario_and_all_verify() -> None:
    _clear_runs()
    cli.run(only="ordinary_work", record=True)
    try:
        for name in ("ow_transfer", "ow_refund", "ow_ledger_read", "ow_message"):
            scenario_dir = RUNS_DIR / name
            assert scenario_dir.exists(), f"no run folder for {name}"
            assert list(scenario_dir.iterdir()), f"no run written under {name}"
        text = RESULTS_PATH.read_text(encoding="utf-8")
        assert "Recorded runs verified: PASS 4 of 4." in text
    finally:
        _clear_runs()


def test_plain_run_writes_no_run_folder() -> None:
    _clear_runs()
    cli.run(only="ordinary_work", record=False)
    assert not RUNS_DIR.exists() or not list(RUNS_DIR.iterdir())


def test_a_fully_denied_scenario_is_not_recorded() -> None:
    """No action ever reaches the simulated tool, so there is no decision to
    cite -- the scenario is skipped, not recorded with an empty run."""
    _clear_runs()
    cli.run(only="ambiguity", record=True)
    try:
        assert not (RUNS_DIR / "amb_missing_destination").exists()
        assert (RUNS_DIR / "amb_legit_complete_transfer").exists()
    finally:
        _clear_runs()
