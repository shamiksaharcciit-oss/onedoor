"""No formatter may reach outside the source tree it was pointed at.

**Learned expensively.** A `ruff check . --fix` run from the repo root walked into
`onedoor-trial/venv/` — an operator's validation workspace, untracked, sitting beside the
source — and rewrote 411 third-party files. Nothing of ours was touched and nothing was
lost, but that is luck, not design: **a byte-rewriting tool that reaches outside its fence
is the exact hazard E10 names**, and the repository already fences vendored bytes against
it. It had simply never fenced *someone else's* bytes.

Ruff's defaults exclude `.venv`. They do not exclude `venv`, and they cannot know what an
operator will leave in the working directory. So this asserts the thing that actually
matters: **every directory that is a virtualenv is excluded**, whatever it is named,
discovered by looking for `pyvenv.cfg` rather than by guessing names.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["ruff"][
    "exclude"
]


def _virtualenvs() -> list[Path]:
    """Every virtualenv in the working tree, found by its marker file.

    `pyvenv.cfg` is the thing that makes a directory a virtualenv, so it is what the
    search looks for — a name-based search would find `venv` and `.venv` and miss
    `trial-env`, which is precisely the class of miss that caused this.
    """
    return [cfg.parent for cfg in ROOT.rglob("pyvenv.cfg")]


def _covered(directory: Path) -> bool:
    relative = directory.relative_to(ROOT).as_posix()
    return any(
        relative == pattern
        or relative.endswith("/" + pattern.removeprefix("**/"))
        or relative == pattern.removeprefix("**/")
        for pattern in EXCLUDE
    )


def test_every_virtualenv_in_the_tree_is_excluded_from_the_formatter() -> None:
    """A formatter pointed at `.` must not rewrite someone else's dependencies."""
    uncovered = [str(v.relative_to(ROOT)) for v in _virtualenvs() if not _covered(v)]
    assert not uncovered, (
        f"these virtualenvs are inside the tree and NOT excluded from ruff: {uncovered}. "
        "A `ruff check . --fix` would rewrite every Python file in them. Add the "
        "directory to `[tool.ruff] exclude` in pyproject.toml."
    )


def test_the_common_virtualenv_names_are_excluded_even_when_absent() -> None:
    """Both directions: the fence must stand before the venv exists, not after.

    A test that only checked venvs currently on disk would pass on a clean checkout and
    let the next one through — the fence has to be there when someone creates it.
    """
    for pattern in ("**/venv", "**/.venv", "**/site-packages"):
        assert pattern in EXCLUDE, f"{pattern} is not fenced against the formatter"
