"""A `git archive` of one ref, extracted to a throwaway directory, for running
`python -m eval run` against a tree other than the one `onedoor` is installed
from -- without ever touching an active venv's own install.

The eval harness needs this to answer "does the current tree's own evaluation
numbers differ from some other ref's" without two separate venvs. The naive
way -- `pip install -e <checkout-of-the-other-ref>` into whichever venv is
active, run the comparison, then delete that checkout -- leaves the venv's
editable install pointing at a directory that no longer exists the moment the
checkout is removed, breaking `import onedoor` for every subsequent caller of
that venv (any subprocess-based test included) until someone notices and
reinstalls. This happened once, during onedoor 0.11.2's third release
candidate, costing a real gate failure traced back to environment corruption
rather than a code defect.

This module never installs anything. `isolated_tree(ref)` only extracts the
ref's files; the caller runs a subprocess against that directory with
`PYTHONPATH` (or `sys.path`, for an in-process import) pointed at it, which
needs no install step at all and cannot mutate any venv's own state, active
or otherwise.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def isolated_tree(ref: str, *, repo_root: Path = REPO_ROOT) -> Iterator[Path]:
    """Extract `git archive <ref>` from `repo_root` into a fresh temp directory,
    yield that directory, and always remove it on the way out -- including
    when the caller's own code raises. Never installs the extracted tree
    anywhere, and never touches any venv's state; callers run a subprocess
    against the yielded path with `PYTHONPATH` set to it, or insert it into
    `sys.path` directly, instead.
    """
    archive = subprocess.run(
        ["git", "archive", ref],
        cwd=repo_root,
        capture_output=True,
        check=True,
    ).stdout
    tmp = Path(tempfile.mkdtemp(prefix="onedoor-isolated-tree-"))
    try:
        with tarfile.open(fileobj=BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
