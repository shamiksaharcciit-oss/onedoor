"""``scripts.parity`` demonstrated against a known, deliberately injected
divergence: a bound moved by one cent, in a throwaway copy of
the tree, must be caught by the scenario probe (the empty-params probe
cannot see it -- no probed request there carries a value at all) -- and the
check must be clean again once the mutation is undone.

Nothing here touches the real worktree: both trees this test builds are
materialized under `tmp_path`, and `scripts.parity.diff_trees` (not `run`,
which always git-archives `--base`) is called directly on them.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scripts import parity

REPO_ROOT = Path(__file__).resolve().parent.parent

_MUTATION_DEMO_SCENARIO = """\
name: zz_parity_mutation_demo
category: ordinary_work
description: >
  not a real evaluation scenario -- built only to sit exactly on the
  payments.transfer bound this test moves by one cent.
actions:
  - action_type: payments.transfer
    params: {amount_eur: 2000.00, destination_account: "acct-parity-demo"}
    ground_truth: legitimate
    why: "at the shipped pack's own declared maximum, inclusive"
"""


def _materialize_head(tmp_path: Path, name: str) -> Path:
    tree = tmp_path / name
    archive = subprocess.run(
        ["git", "archive", "HEAD"], cwd=REPO_ROOT, capture_output=True, check=True
    )
    tree.mkdir()
    import io
    import tarfile

    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tf:
        tf.extractall(tree, filter="data")
    return tree


def test_parity_catches_a_bound_moved_by_one_cent_and_is_clean_once_reverted(
    tmp_path: Path,
) -> None:
    unmutated = _materialize_head(tmp_path, "unmutated")
    mutated = _materialize_head(tmp_path, "mutated")

    # The same new scenario, identical in both trees -- only the policy's own
    # bound differs between them. Without a real request sitting at the bound,
    # moving it by one cent would change nothing this probe could observe.
    for tree in (unmutated, mutated):
        (tree / "eval" / "scenarios" / "zz_parity_mutation_demo.yaml").write_text(
            _MUTATION_DEMO_SCENARIO, encoding="utf-8"
        )

    policy_path = mutated / "onedoor" / "templates" / "payments" / "policies.yaml"
    original = policy_path.read_text(encoding="utf-8")
    assert "max: 2000.00" in original, "the bound this test moves is no longer where it was"
    mutated_text = original.replace("max: 2000.00", "max: 1999.99", 1)
    policy_path.write_text(mutated_text, encoding="utf-8")

    caught_ok, caught_message = parity.diff_trees(unmutated, mutated)
    assert not caught_ok, (
        f"parity.diff_trees did not catch the one-cent bound move: {caught_message}"
    )
    assert "zz_parity_mutation_demo:0" in caught_message
    assert "payments.transfer" in caught_message

    # Restore the one line -- the mutated tree is now byte-identical to the
    # unmutated one again, bar the scenario file both already carry.
    policy_path.write_text(original, encoding="utf-8")
    clean_ok, clean_message = parity.diff_trees(unmutated, mutated)
    assert clean_ok, (
        f"parity.diff_trees is not clean once the mutation is reverted: {clean_message}"
    )

    for tree in (unmutated, mutated):
        shutil.rmtree(tree, ignore_errors=True)


def test_empty_params_probe_alone_would_not_have_caught_the_same_mutation(
    tmp_path: Path,
) -> None:
    """Documents, as a test rather than only as a comment, exactly the gap this
    script's scenario probe closes: the empty-params probe's own request for
    `payments.transfer` carries no `amount_eur` at all, so it is refused as a
    missing required param before the bound is ever reached -- identically,
    whether the bound is 2000.00 or 1999.99."""
    unmutated = _materialize_head(tmp_path, "unmutated2")
    mutated = _materialize_head(tmp_path, "mutated2")

    policy_path = mutated / "onedoor" / "templates" / "payments" / "policies.yaml"
    original = policy_path.read_text(encoding="utf-8")
    policy_path.write_text(original.replace("max: 2000.00", "max: 1999.99", 1), encoding="utf-8")

    policy_files = parity._policy_files(mutated, parity.DEFAULT_POLICY_GLOBS)
    base_results = parity._probe(unmutated, policy_files)
    head_results = parity._probe(mutated, policy_files)
    assert base_results.get("payments.transfer") == head_results.get("payments.transfer")

    for tree in (unmutated, mutated):
        shutil.rmtree(tree, ignore_errors=True)
