"""`eval/` is a repository-only evaluation harness: it must never reach the
wheel or the sdist, both checked by actually building them, the same way
`tests/test_packaging.py` checks every other packaging claim."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path


def test_eval_examples_and_docs_img_are_absent_from_the_built_artifacts(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
    from build_release import build as build_release  # noqa: PLC0415

    wheel_path, sdist_path = build_release(tmp_path)

    with zipfile.ZipFile(wheel_path) as whl:
        wheel_names = whl.namelist()
    with tarfile.open(sdist_path) as tar:
        sdist_names = tar.getnames()

    for prefix in ("eval/", "examples/integrations/", "docs/img/"):
        wheel_hits = [n for n in wheel_names if n.startswith(prefix)]
        assert not wheel_hits, f"the wheel contains {prefix} file(s): {wheel_hits}"
        sdist_hits = [n for n in sdist_names if f"/{prefix}" in n or n.startswith(prefix)]
        assert not sdist_hits, f"the sdist contains {prefix} file(s): {sdist_hits}"
