"""``python -m scripts.parity --base <rev>``

Decision parity between a base revision and the current checkout, for every
action type a shipped example policy (``examples/*.yaml``) or an evaluation
policy (``eval/policies/*.yaml``) declares, PLUS every scripted action in the
evaluation's own scenarios (``eval/scenarios/*.yaml``), run in order with its
own real params against a fresh store per scenario. A round is opt-in, so a
policy that declares none of a round's new fields must decide exactly as the
base did: same decision, same reason code, same tier.

Two probes, not one: an empty-params probe (one synthetic
request per action type, ``params={}``) proves only the paths that ignore a
request's own values -- kill switch, tier assignment, a missing-required-param
denial. It cannot see a bound, a cap or a budget move, because every probed
request already fails before reaching one. The scenario probe closes that gap
with real amounts, run in the order a scenario scripts them (caps and budgets
are cumulative across a scenario's own actions), against the same policy set
the evaluation itself loads (the shipped payments pack plus
``eval/policies/eval_extra.yaml``). Kept as two separate checks rather than
folded into one: the empty-params probe also covers every example policy's
action type that no scenario happens to exercise, which the scenario probe
alone would miss.

Why this exists at all: an earlier round touched nothing under
``onedoor/guardrail`` or ``onedoor/service``, so the suite passing unchanged
was proof enough on its own. A round that changes the engine itself needs an
explicit, opt-in-aware check instead -- "the suite already proves it" stops
holding once the engine the suite exercises is the thing that changed.

Runs the base at a git-archive of ``--base`` in a throwaway directory and the
current checkout in place, each in its own subprocess (so two versions of the
same package are never imported into one process), diffs the two result
tables, and fails on any difference.

Out of scope, by choice, not oversight: the scenario probe calls
``decide_and_reserve`` (and ``report_result`` for a permitted action) directly,
the same single library entry point the empty-params probe already uses. It
does not toggle the kill switch, resolve an approval, or present a permit the
way a scenario's own script and ``eval/harness/engine.py`` do for a full
evaluation run -- reproducing that orchestration here would duplicate what
``python -m eval run``'s own base-vs-head comparison, already a separate step
in every round's gate, already checks. This probe's job is the one the suite
and the eval comparison do not cover: a real amount, run through the engine
directly, in a store that accumulates the way a scenario's actions do.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_GLOBS = ("examples/*.yaml", "eval/policies/*.yaml")

# Run via `python -c`, which (like `-m`) prepends the invoking process's own
# cwd to sys.path as "" -- cwd is set per call below to either the base's
# materialized tree or this checkout, so `import onedoor` always resolves to
# whichever tree is being probed, never to an unrelated installed copy.
_PROBE = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from datetime import datetime, UTC
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo
import yaml
from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve, report_result, PermittedIntent
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Source
from onedoor.store.db import Database

policy_files = json.loads(sys.argv[1])
db_path = sys.argv[2]

database = Database(db_path)
database.init()
conn = database.connect()
action_types = []
for pf in policy_files:
    policy_loader.load_file(conn, pf)
    doc = yaml.safe_load(Path(pf).read_text(encoding="utf-8")) or {}
    for entry in doc.get("policies", []):
        at = entry.get("action_type")
        if at and at not in action_types:
            action_types.append(at)

config = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=1.0, tz=ZoneInfo("UTC"))
now = datetime(2026, 1, 1, tzinfo=UTC)
results = {}
for at in action_types:
    req = ActionRequest(
        request_id=uuid4(), action_type=at, params={}, source=Source.UI,
        rationale="parity probe", cost_eur=Decimal(0), created_at=now,
    )
    try:
        out = decide_and_reserve(req, conn=conn, config=config, now=now)
    except Exception as exc:
        results[at] = {"error": f"{type(exc).__name__}: {exc}"}
        continue
    if isinstance(out, PermittedIntent):
        results[at] = {"decision": "permit", "reason_code": None, "tier": out.effective_tier.value}
        try:
            report_result(out, conn=conn, outcome="success", now=now)
        except Exception:
            pass
    else:
        results[at] = {
            "decision": out.decision.decision.value,
            "reason_code": out.decision.reason_code.value,
            "tier": out.decision.effective_tier.value,
        }
print(json.dumps(results))
"""

# The same policy set `eval/harness/service.py` loads for every scenario category
# but `permits` (which runs in-process, never through this probe's own direct
# `decide_and_reserve` calls either -- see the module docstring's "out of scope").
SCENARIO_POLICY_FILES = (
    "onedoor/templates/payments/policies.yaml",
    "eval/policies/eval_extra.yaml",
)

# One fresh store per scenario (caps and budgets are cumulative across a
# scenario's own actions, never across scenarios), actions run in the order the
# scenario scripts them. Keyed `"<scenario>:<index>"` rather than by action type
# alone -- two actions of the same type in one scenario script are two separate
# probes, deliberately (the second one's decision depends on what the first one
# already reserved).
_SCENARIO_PROBE = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from datetime import datetime, UTC
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo
from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve, report_result, PermittedIntent
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Source
from onedoor.store.db import Database
from eval.harness.scenario import load_all

policy_files = json.loads(sys.argv[1])
scenarios_dir = sys.argv[2]
db_dir = sys.argv[3]

config = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=1.0, tz=ZoneInfo("UTC"))
now = datetime(2026, 1, 1, tzinfo=UTC)
results = {}
for scenario in load_all(Path(scenarios_dir)):
    db_path = str(Path(db_dir) / f"{scenario.name}.db")
    database = Database(db_path)
    database.init()
    conn = database.connect()
    for pf in policy_files:
        policy_loader.load_file(conn, pf)
    for i, action in enumerate(scenario.actions):
        key = f"{scenario.name}:{i}"
        req = ActionRequest(
            request_id=uuid4(), action_type=action.action_type, params=action.params,
            source=Source.LLM, rationale="parity probe (scenario)", cost_eur=Decimal(0),
            created_at=now,
        )
        try:
            out = decide_and_reserve(req, conn=conn, config=config, now=now)
        except Exception as exc:
            results[key] = {"action_type": action.action_type, "error": f"{type(exc).__name__}: {exc}"}
            continue
        if isinstance(out, PermittedIntent):
            results[key] = {
                "action_type": action.action_type, "decision": "permit",
                "reason_code": None, "tier": out.effective_tier.value,
            }
            try:
                report_result(out, conn=conn, outcome="success", now=now)
            except Exception:
                pass
        else:
            results[key] = {
                "action_type": action.action_type,
                "decision": out.decision.decision.value,
                "reason_code": out.decision.reason_code.value,
                "tier": out.decision.effective_tier.value,
            }
    conn.close()
print(json.dumps(results))
"""


def _policy_files(root: Path, globs: tuple[str, ...]) -> list[str]:
    files: list[str] = []
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            files.append(str(path.relative_to(root)).replace("\\", "/"))
    return files


def _probe(tree: Path, policy_files: list[str]) -> dict[str, dict[str, object]]:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "parity.db")
        completed = subprocess.run(
            [sys.executable, "-c", _PROBE, json.dumps(policy_files), db_path],
            cwd=tree,
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"probe failed in {tree}:\n{completed.stderr}")
    # stdout may carry warnings above the one JSON line this probe ever prints.
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _probe_scenarios(
    tree: Path, policy_files: list[str], scenarios_dir: str
) -> dict[str, dict[str, object]]:
    with tempfile.TemporaryDirectory() as td:
        completed = subprocess.run(
            [sys.executable, "-c", _SCENARIO_PROBE, json.dumps(policy_files), scenarios_dir, td],
            cwd=tree,
            capture_output=True,
            text=True,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"scenario probe failed in {tree}:\n{completed.stderr}")
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _materialize(rev: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="parity-base-"))
    archive = subprocess.run(
        ["git", "archive", rev], cwd=REPO_ROOT, capture_output=True, check=True
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tf:
        tf.extractall(tmp, filter="data")
    return tmp


def _diff_examples(
    base_tree: Path, head_tree: Path, policy_files: list[str], exclude: frozenset[str]
) -> tuple[list[str], int]:
    base_results = _probe(base_tree, policy_files)
    head_results = _probe(head_tree, policy_files)
    all_types = sorted((set(base_results) | set(head_results)) - exclude)
    diffs = []
    for at in all_types:
        b, h = base_results.get(at), head_results.get(at)
        if b != h:
            diffs.append(f"  {at}: base={b!r} head={h!r}")
    return diffs, len(all_types)


def _diff_scenarios(
    base_tree: Path,
    head_tree: Path,
    policy_files: list[str],
    base_scenarios_dir: Path,
    head_scenarios_dir: Path,
    exclude: frozenset[str],
) -> tuple[list[str], int]:
    base_results = _probe_scenarios(base_tree, policy_files, str(base_scenarios_dir))
    head_results = _probe_scenarios(head_tree, policy_files, str(head_scenarios_dir))
    # A key's own action type decides exclusion, not the scenario:index key itself --
    # `exclude` names action types, as it already does for the empty-params probe.
    all_keys = sorted(set(base_results) | set(head_results))
    diffs = []
    for key in all_keys:
        b, h = base_results.get(key), head_results.get(key)
        at = (b or h or {}).get("action_type")
        if at in exclude:
            continue
        if b != h:
            diffs.append(f"  {key} ({at}): base={b!r} head={h!r}")
    return diffs, len(all_keys)


def diff_trees(
    base_tree: Path,
    head_tree: Path,
    *,
    exclude: frozenset[str] = frozenset(),
    base_scenarios_dir: Path | None = None,
    head_scenarios_dir: Path | None = None,
) -> tuple[bool, str]:
    """The comparison itself, between two already-materialized trees -- what `run`
    delegates to once it has git-archived `--base`. Exposed separately so this
    module's own test can diff two local, hand-built trees directly (a live
    checkout and a one-cent-mutated copy of it), without needing either side to be
    a real git revision.
    """
    policy_files = _policy_files(head_tree, DEFAULT_POLICY_GLOBS)
    base_scen = (
        base_scenarios_dir if base_scenarios_dir is not None else base_tree / "eval" / "scenarios"
    )
    head_scen = (
        head_scenarios_dir if head_scenarios_dir is not None else head_tree / "eval" / "scenarios"
    )

    example_diffs, n_types = _diff_examples(base_tree, head_tree, policy_files, exclude)
    scenario_diffs, n_actions = _diff_scenarios(
        base_tree, head_tree, list(SCENARIO_POLICY_FILES), base_scen, head_scen, exclude
    )

    diffs = example_diffs + scenario_diffs
    if diffs:
        return (
            False,
            f"{len(example_diffs)} action type(s) and {len(scenario_diffs)} scenario "
            f"action(s) differ between base and head:\n" + "\n".join(diffs),
        )
    return (
        True,
        f"{n_types} action type(s) across {len(policy_files)} policy file(s) (empty-params "
        f"probe) and {n_actions} scenario action(s) across {len(SCENARIO_POLICY_FILES)} policy "
        f"file(s) (real-params probe), all identical",
    )


def run(base: str, *, exclude: frozenset[str] = frozenset()) -> tuple[bool, str]:
    """The live checkout's own gate entry point: git-archives `--base` into a
    throwaway tree, diffs it against `REPO_ROOT` as it stands, and cleans up."""
    base_tree = _materialize(base)
    try:
        return diff_trees(base_tree, REPO_ROOT, exclude=exclude)
    finally:
        import shutil

        shutil.rmtree(base_tree, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.parity")
    parser.add_argument("--base", required=True, help="the revision to compare against")
    parser.add_argument(
        "--exclude-action-type",
        action="append",
        default=[],
        help="an action type a later round deliberately changed on purpose (uses a "
        "new, opt-in field); repeatable",
    )
    args = parser.parse_args(argv)
    ok, message = run(args.base, exclude=frozenset(args.exclude_action_type))
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
