from __future__ import annotations

import re
from pathlib import Path

from eval.harness import cli


def test_the_chart_s_numbers_equal_results_md(tmp_path: Path) -> None:
    cli.run(only=None, record=False, out_dir=tmp_path)
    chart_path = tmp_path / "eval-results.svg"
    results_path = tmp_path / "RESULTS.md"
    chart_values = [int(m) for m in re.findall(r'class="value">(\d+)<', chart_path.read_text())]

    results_text = results_path.read_text(encoding="utf-8")
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


def test_a_partial_run_does_not_overwrite_the_chart(tmp_path: Path) -> None:
    chart_path = tmp_path / "eval-results.svg"
    cli.run(only=None, record=False, out_dir=tmp_path)
    before = chart_path.read_bytes()
    cli.run(only="permits", record=False, out_dir=tmp_path)
    assert chart_path.read_bytes() == before
