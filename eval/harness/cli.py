"""``python -m eval run [--only CATEGORY] [--record]``."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from eval.harness import chart, engine, findings, measures, results, service
from eval.harness.scenario import CATEGORIES, load_all

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_DIR = REPO_ROOT / "eval" / "scenarios"
RESULTS_PATH = REPO_ROOT / "eval" / "RESULTS.md"
FINDINGS_PATH = REPO_ROOT / "eval" / "FINDINGS.md"
CHART_PATH = REPO_ROOT / "docs" / "img" / "eval-results.svg"

APPROVAL_TTL_SECONDS = 2  # short enough to demonstrate expiry without a slow run


def _onedoor_version() -> str:
    """The source tree's own declared version -- never the installed package's
    metadata, which this shared venv does not refresh on every release."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError("pyproject.toml has no top-level version")
    return match.group(1)


def _onedoor_commit() -> str:
    out = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "onedoor"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()[:12]


def run(*, only: str | None, record: bool, out_dir: Path | None = None) -> int:
    """``out_dir``, test-only: write ``RESULTS.md``/``FINDINGS.md``/the chart under
    this directory instead of the tracked `eval/` and `docs/img/` paths. ``python -m
    eval run`` itself never passes this -- a real run still writes the tracked files,
    exactly as before."""
    scenarios = load_all(SCENARIOS_DIR, only=only)
    outcomes_without = {s.name: engine.run_without(s) for s in scenarios}

    outcomes_with: dict[str, list] = {}
    parked: dict[str, str] = {}
    now = datetime.now(UTC)

    # One fresh database (and, for every category but permits, one fresh
    # service instance) per scenario -- caps, approvals and the kill switch
    # are all process-wide state, and a scenario's measures must not depend
    # on which other scenario happened to run through the same one before it.
    for s in scenarios:
        if s.category == "permits":
            outcomes_with[s.name] = engine.run_with(
                s, svc=None, db_path=tempfile.mktemp(suffix=".db"), now=now
            )
            continue
        ttl = APPROVAL_TTL_SECONDS if s.category == "approval" else None
        with service.start(tempfile.mktemp(suffix=".db"), approval_ttl_seconds=ttl) as svc:
            outcomes_with[s.name] = engine.run_with(s, svc=svc, db_path="", now=now)

    record_line = None
    if record:
        from eval.harness import record as record_mod

        record_line = record_mod.record_and_verify(scenarios, outcomes_with)

    totals = measures.compute(scenarios, outcomes_without, outcomes_with, parked)
    meta = results.RunMeta(onedoor_version=_onedoor_version(), onedoor_commit=_onedoor_commit())
    results_path = out_dir / "RESULTS.md" if out_dir else RESULTS_PATH
    findings_path = out_dir / "FINDINGS.md" if out_dir else FINDINGS_PATH
    chart_path = out_dir / "eval-results.svg" if out_dir else CHART_PATH
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        results.render(
            meta=meta,
            scenarios=scenarios,
            outcomes_without=outcomes_without,
            outcomes_with=outcomes_with,
            totals=totals,
            record_verify_line=record_line,
        ),
        encoding="utf-8",
        newline="\n",
    )
    all_findings = findings.compute(scenarios, outcomes_with)
    findings_path.write_text(findings.render(all_findings), encoding="utf-8", newline="\n")
    if only is None:
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        chart_path.write_text(chart.render(totals), encoding="utf-8", newline="\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--only", choices=CATEGORIES, default=None)
    run_parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run":
        return run(only=args.only, record=args.record)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
