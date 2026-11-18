"""`eval/RESULTS.md`'s own header cites the `onedoor/` tree it was run against,
by id. That citation must actually match the tree at `HEAD` -- the staleness
`scripts/check_shipped_text.py` exists to catch is the checker's allowance
list moving out of step with it, not the citation itself ever being read back
against a live git checkout. This is that read-back.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_PATH = REPO_ROOT / "eval" / "RESULTS.md"

_TREE_ID_RE = re.compile(r"\(onedoor/ tree ([0-9a-f]{12})\)")


def _git_tree_id_at_head() -> str | None:
    """Returns `HEAD:onedoor`'s own tree id (first 12 hex chars), or `None`
    when this is not a git checkout at all -- an sdist or wheel install has
    no `.git` to ask, and that absence is not itself a staleness finding."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD:onedoor"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()[:12]


def test_results_md_cites_the_tree_actually_at_head() -> None:
    head_tree = _git_tree_id_at_head()
    if head_tree is None:
        pytest.skip("not a git checkout -- no HEAD:onedoor to read back against")

    text = RESULTS_PATH.read_text(encoding="utf-8")
    match = _TREE_ID_RE.search(text)
    assert match is not None, "eval/RESULTS.md's header no longer cites a tree id at all"
    cited_tree = match.group(1)

    assert cited_tree == head_tree, (
        f"eval/RESULTS.md cites tree {cited_tree!r} but HEAD:onedoor is {head_tree!r} -- "
        "the eval was run at a different tree than the one actually committed; rerun it"
    )
