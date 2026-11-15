"""``python -m eval run [--only CATEGORY] [--record]``."""

from __future__ import annotations

import argparse
import dataclasses
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from eval.harness import chart, engine, findings, measures, results, service
from eval.harness.scenario import CATEGORIES, Scenario, load_all

RECIPIENT_OPT_IN_SCENARIO = "inj_message_to_untrusted_recipient"

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


def _onedoor_tree() -> str:
    """The git tree id of `onedoor/` at `HEAD`, not a commit id -- a commit
    made on this branch is never guaranteed to reach public history (this
    file sits in the very tree its own commit would be made from, which is
    circular), while a tree id is checkable by anyone against whatever
    public commit actually ships it. Identical whether computed from this
    branch's own head or from the release commit built from the same tree,
    since both share one `onedoor/` subtree by construction."""
    out = subprocess.run(
        ["git", "rev-parse", "HEAD:onedoor"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()[:12]


def _recipient_opt_in_demo_line(scenarios: list[Scenario]) -> str | None:
    """A second, labelled run of `RECIPIENT_OPT_IN_SCENARIO` alone: the same
    scenario, but with its one action's `recipient` path marked `untrusted` by
    the caller -- onedoor 0.11's opt-in control, declared on `messages.send`
    as `untrusted_params.hold: [recipient]` (`eval/policies/eval_extra.yaml`).
    Not folded into the totals table above: it is not a new scenario, only the
    existing one's miss observed a second way, with the caller's own input
    marked. Returns `None` when the scenario is not in this run (`--only`
    scoped to a different category)."""
    base = next((s for s in scenarios if s.name == RECIPIENT_OPT_IN_SCENARIO), None)
    if base is None:
        return None
    marked_action = dataclasses.replace(base.actions[0], untrusted=("recipient",))
    marked = dataclasses.replace(base, actions=(marked_action,))
    now = datetime.now(UTC)
    with service.start(tempfile.mktemp(suffix=".db")) as svc:
        outcome = engine.run_with(marked, svc=svc, db_path="", now=now)[0]
    return (
        f"- `{marked.name}`, with the caller marking `recipient` untrusted: "
        f"decided `{outcome.decision}` (was `permitted` unmarked, by default)."
    )


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

    opt_in_line = _recipient_opt_in_demo_line(scenarios)

    totals = measures.compute(scenarios, outcomes_without, outcomes_with, parked)
    meta = results.RunMeta(onedoor_version=_onedoor_version(), onedoor_tree=_onedoor_tree())
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
            recipient_opt_in_line=opt_in_line,
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
