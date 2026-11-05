"""Addendum step 7: ``python -m eval run --record``.

Re-runs each scenario's with-onedoor side a second time, this time wrapped in
one onetrace run per scenario under ``eval/runs/<scenario>/``: one stage per
proposed action, labelled by the simulated tool's own effect kind, citing
``ot.decision(ref, permit, action)`` with what onedoor actually returned right
before the simulated tool acts. Every run is then checked with
``onetrace-verify``. The without-onedoor side is never recorded -- there is no
decision to cite.

Only onetrace's public, documented 0.7.0 API. Nothing from onetrace's private
repository or unreleased work, and no change to ``onedoor/`` or to any
installed package.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import onetrace as ot
from onetrace.emit import Instrument

from eval.harness import engine, service
from eval.harness import tool as tool_mod
from eval.harness.scenario import Scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "eval" / "runs"
TOOL_INSTRUMENT = Instrument(id="eval-simulated-tool", kind="tool", version="1", config={})

_WRITE_KINDS = {"money_moved", "rows_deleted", "message_sent"}


def _effect_for(action_type: str, params: dict) -> str:
    kind, _ = tool_mod.effect_of(action_type, params)
    return "write" if kind in _WRITE_KINDS else "read"


def _as_decimal_strings(value: object) -> object:
    """onetrace's canonical form carries amounts as decimal strings, never a
    float (JCS has no non-integer number canonicalization it relies on)."""
    if isinstance(value, float):
        return format(value, ".2f") if value == round(value, 2) else repr(value)
    if isinstance(value, dict):
        return {k: _as_decimal_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_as_decimal_strings(v) for v in value]
    return value


def _record_one_scenario(
    scenario: Scenario, now: datetime, *, settling_indices: set[int]
) -> Path | None:
    """Runs this scenario's with-onedoor side once, recorded. Returns the
    written run folder, or ``None`` if no action of this scenario ever
    reaches the simulated tool in the original run (nothing to cite)."""
    if not settling_indices:
        return None
    stage_names = [f"action-{i}" for i in sorted(settling_indices)]

    def hook(_scenario, index, action, decision_ref, bound_permit, call_tool):
        effect = _effect_for(action.action_type, action.params)
        action_object = {
            "action_type": action.action_type,
            "params": _as_decimal_strings(action.params),
        }

        @ot.stage(f"action-{index}", instrument=TOOL_INSTRUMENT, effect=effect)
        def _step() -> dict:
            if decision_ref is not None:
                ot.decision(decision_ref, permit=bound_permit, action=action_object)
            return {"outcome": call_tool()}

        return _step()["outcome"]

    @ot.run(str(RUNS_DIR / scenario.name / "{run_id}"), stages=stage_names)
    def _pipeline() -> None:
        if scenario.category == "permits":
            engine._run_with_permits(
                scenario, db_path=tempfile.mktemp(suffix=".db"), now=now, record_hook=hook
            )
        else:
            ttl = 2 if scenario.category == "approval" else None
            with service.start(tempfile.mktemp(suffix=".db"), approval_ttl_seconds=ttl) as svc:
                engine.run_with(scenario, svc=svc, db_path="", now=now, record_hook=hook)

    scenario_dir = RUNS_DIR / scenario.name
    before = set(scenario_dir.glob("*")) if scenario_dir.exists() else set()
    _pipeline()
    after = set(scenario_dir.glob("*"))
    written = sorted(after - before)
    return written[-1] if written else None


def record_and_verify(scenarios: list[Scenario], outcomes_with: dict) -> str:
    """Records every scenario, verifies each run, and returns the RESULTS.md
    line addendum 1 adds. Does not touch RESULTS.md or FINDINGS.md itself --
    the caller folds the returned line in."""
    now = datetime.now(UTC)
    verdicts: dict[str, str] = {}
    for scenario in scenarios:
        settling = {
            o.action_index
            for o in outcomes_with.get(scenario.name, [])
            if o.decision in ("executed", "permitted")
        }
        run_dir = _record_one_scenario(scenario, now, settling_indices=settling)
        if run_dir is None:
            continue
        verify_exe = str(Path(sys.executable).parent / "onetrace-verify")
        result = subprocess.run(
            [verify_exe, str(run_dir)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        tail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        verdicts[scenario.name] = "PASS" if tail.rstrip().endswith("PASS") else f"not PASS ({tail})"

    total = len(verdicts)
    passed = sum(1 for v in verdicts.values() if v == "PASS")
    others = {name: v for name, v in verdicts.items() if v != "PASS"}
    line = f"Recorded runs verified: PASS {passed} of {total}."
    if others:
        line += " Not PASS: " + ", ".join(f"`{n}` ({v})" for n, v in sorted(others.items())) + "."
    return line
