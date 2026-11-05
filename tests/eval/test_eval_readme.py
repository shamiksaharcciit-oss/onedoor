"""The top-level README's "tested against irreversible actions" table must
hold the same numbers as eval/RESULTS.md's own totals table -- it is a copy
for readers who never run the eval themselves, and a stale copy would claim
a result nothing measured."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
README_PATH = REPO_ROOT / "README.md"
RESULTS_PATH = REPO_ROOT / "eval" / "RESULTS.md"


def _totals_table(text: str) -> list[list[str]]:
    rows = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| category"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if "---" in line:
                continue
            cells = [c.strip().strip("*") for c in line.split("|")][1:-1]
            rows.append(cells)
    return rows


def test_the_readme_s_totals_table_matches_results_md() -> None:
    readme_rows = _totals_table(README_PATH.read_text(encoding="utf-8"))
    results_rows = _totals_table(RESULTS_PATH.read_text(encoding="utf-8"))
    assert readme_rows, "README.md has no totals table to check"
    assert readme_rows == results_rows, (
        f"README.md's totals table has drifted from eval/RESULTS.md: "
        f"{readme_rows} != {results_rows}"
    )
