from __future__ import annotations

import re
from pathlib import Path

from eval.harness import cli

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHART_PATH = REPO_ROOT / "docs" / "img" / "eval-results.svg"
RESULTS_PATH = REPO_ROOT / "eval" / "RESULTS.md"


def test_the_chart_s_numbers_equal_results_md() -> None:
    cli.run(only=None, record=False)
    chart_values = [int(m) for m in re.findall(r'class="value">(\d+)<', CHART_PATH.read_text())]

    results_text = RESULTS_PATH.read_text(encoding="utf-8")
    table_values: list[int] = []
    for line in results_text.splitlines():
        if not line.startswith("| ") or line.startswith("| category") or "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")][1:-1]
        if cells[0] in ("**total**",):
            continue
        table_values.append(int(cells[1]))
        table_values.append(int(cells[2]))

    assert chart_values == table_values


def test_a_partial_run_does_not_overwrite_the_chart() -> None:
    cli.run(only=None, record=False)
    before = CHART_PATH.read_bytes()
    cli.run(only="permits", record=False)
    assert CHART_PATH.read_bytes() == before
