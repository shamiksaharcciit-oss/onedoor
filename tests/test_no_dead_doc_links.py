"""No tracked file links a file this tree does not actually hold.

Found the hard way: `BACKLOG.md` was linked from eleven places across this
repository -- `ROADMAP.md`'s own table, this changelog's own opening line,
a docstring in `onedoor/studio/store.py`, release notes, example docs -- and
never existed on `main` at all. Every one of those was a real markdown link
or file reference a reader could click and get nowhere. This is the general
check that catches the next one of those, for any file, not only this one.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]

_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
"""A markdown link's own target: `[text](target)`. Deliberately not also
matching a bare angle-bracket autolink or an HTML `href` -- those are rare
in this tree's own prose, and a pattern this narrow stays easy to reason
about and to extend, the same discipline `check_shipped_text.py`'s own
patterns are held to."""

_SKIP_SCHEMES = {"http", "https", "mailto", "ftp"}
_SKIP_SUFFIXES = {".pyc"}


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def _is_external_or_special(target: str) -> bool:
    if target.startswith("#"):
        return True  # an in-page anchor, not a file
    scheme = urlsplit(target).scheme
    return scheme in _SKIP_SCHEMES


def _resolved_target_path(linking_file: str, target: str) -> Path | None:
    """The real filesystem path `target` names, relative to the file that
    links it -- `None` for anything not resolvable as a repo-relative file
    reference (an external URL, a pure anchor, a `mailto:`, ...)."""
    if _is_external_or_special(target):
        return None
    target = target.split("#", 1)[0]  # drop a same-document anchor suffix
    if not target:
        return None  # was anchor-only before the split
    linking_dir = (ROOT / linking_file).parent
    return (linking_dir / target).resolve()


def _tracked_file_set() -> frozenset[str]:
    return frozenset(_tracked_files())


def _is_tracked(resolved: Path, tracked: frozenset[str]) -> bool:
    """Whether `resolved` names a file this tree actually tracks, or a
    directory that holds at least one tracked file -- checked against
    `git ls-files`, never the filesystem directly. A file that merely
    exists on disk (a build artifact, a local scratch file, anything
    sitting in the working tree but never staged) is not something a
    fresh clone of this repository would ever have, so a link to one is
    still dead even though `Path.exists()` would say otherwise. `git
    ls-files` names files only, never a directory on its own -- a link to
    a directory (browsing into `examples/foo/`, a common convention) is
    tracked precisely when some tracked file's own path starts with it."""
    try:
        rel = resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return False  # outside the repo entirely
    if rel in tracked:
        return True
    prefix = rel if rel.endswith("/") else rel + "/"
    return any(t.startswith(prefix) for t in tracked)


def _iter_markdown_links() -> list[tuple[str, str]]:
    """`(linking_file, target)` for every markdown-style link in every
    tracked `.md` file -- scoped to `.md` specifically, not every text file:
    the identical `](...)` shape turns up constantly in `.py` source as an
    ordinary regex literal (`r"(?:https?://...)"`) and in a `.patch` file's
    own diff body (a byte-exact artifact, never ours to edit) -- neither is
    a real link for a reader to follow, and scanning them only produces
    noise no fix could ever resolve."""
    pairs: list[tuple[str, str]] = []
    for rel_path in _tracked_files():
        if not rel_path.endswith(".md"):
            continue
        path = ROOT / rel_path
        if path.suffix in _SKIP_SUFFIXES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in _LINK_RE.finditer(text):
            pairs.append((rel_path, m.group(1)))
    return pairs


def test_no_tracked_file_links_a_path_this_tree_does_not_hold() -> None:
    tracked = _tracked_file_set()
    dead: list[tuple[str, str]] = []
    for linking_file, target in _iter_markdown_links():
        resolved = _resolved_target_path(linking_file, target)
        if resolved is None:
            continue
        if not _is_tracked(resolved, tracked):
            dead.append((linking_file, target))
    assert dead == [], (
        "the following tracked files link a path this tree does not hold "
        "(file, target): " + ", ".join(f"{f} -> {t}" for f, t in dead)
    )


def test_a_directory_holding_tracked_files_is_not_a_dead_link() -> None:
    """`git ls-files` names files only -- a link to the directory itself
    (`examples/foo/`, browsed into rather than opened) is tracked exactly
    when some tracked file's own path starts with it."""
    resolved = _resolved_target_path("README.md", "examples/integrations/plain_python/")
    assert resolved is not None
    assert _is_tracked(resolved, _tracked_file_set())


def test_a_directory_holding_no_tracked_files_is_still_a_dead_link() -> None:
    resolved = _resolved_target_path("README.md", "examples/integrations/does-not-exist/")
    assert resolved is not None
    assert not _is_tracked(resolved, _tracked_file_set())


def test_an_untracked_file_on_disk_is_still_a_dead_link() -> None:
    """The planted gap this check used to have: resolving against the
    filesystem (`Path.exists()`) says a merely-present, untracked file is
    fine, when a fresh clone would never have it at all. Plants a real
    file on disk, outside git's own index, and confirms the two checks
    actually disagree -- `exists()` says yes, `_is_tracked` says no --
    before relying on the one this module's own main test now uses."""
    planted = ROOT / "docs" / "_test_planted_untracked_link_target.md"
    assert not planted.exists(), "a previous run of this test left its own planted file behind"
    planted.write_text("planted by a test, never staged", encoding="utf-8")
    try:
        resolved = _resolved_target_path(
            "docs/integration-mcp.md", "_test_planted_untracked_link_target.md"
        )
        assert resolved == planted.resolve()
        assert resolved.exists()
        assert not _is_tracked(resolved, _tracked_file_set())
    finally:
        planted.unlink()


@pytest.mark.parametrize(
    "target",
    ["https://example.com/BACKLOG.md", "mailto:someone@example.com", "#a-heading"],
)
def test_an_external_url_or_anchor_is_not_treated_as_a_file_reference(target: str) -> None:
    assert _resolved_target_path("README.md", target) is None


def test_a_relative_link_resolves_against_its_own_linking_files_directory() -> None:
    resolved = _resolved_target_path("docs/integration-litellm.md", "../README.md")
    assert resolved == (ROOT / "README.md").resolve()


def test_an_anchor_suffix_on_a_real_file_is_stripped_before_checking() -> None:
    resolved = _resolved_target_path("README.md", "CHANGELOG.md#0.11.0")
    assert resolved == (ROOT / "CHANGELOG.md").resolve()
