"""No test under `tests/eval` may leave the tracked
`eval/RESULTS.md`/`FINDINGS.md` modified. Every test here now passes `cli.run(...,
out_dir=tmp_path)` instead of writing the tracked paths -- this fixture is the
check that it held, not an assumption from reading the other tests' own source: a
new test added later, here or anywhere else in the suite, that calls `cli.run`
without `out_dir` would otherwise reintroduce the bug silently."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_TRACKED = (REPO_ROOT / "eval" / "RESULTS.md", REPO_ROOT / "eval" / "FINDINGS.md")


@pytest.fixture(scope="session", autouse=True)
def _tracked_eval_files_stay_untouched() -> Iterator[None]:
    before = {path: path.read_bytes() for path in _TRACKED}
    yield
    changed = [path for path in _TRACKED if path.read_bytes() != before[path]]
    assert not changed, (
        f"tests/eval left these tracked files modified: {[str(p) for p in changed]} -- "
        "pass out_dir=tmp_path to cli.run() instead of writing the tracked paths"
    )
