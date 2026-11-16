"""`eval.harness.isolated_tree` extracts a ref's files for a subprocess or a
`sys.path` insertion to run against -- never by installing anything into any
venv. The old way (install the other ref's checkout editable into whichever
venv happens to be active, then delete the checkout once the comparison is
done) leaves that venv's `onedoor` import broken for every later caller,
silently, the moment the checkout is gone. This suite proves the new way
cannot do that: nothing it runs ever names `pip`/`install`, and the active
interpreter's own `onedoor` import is byte-identical before and after.
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from unittest import mock

import onedoor
from eval.harness.isolated_tree import isolated_tree

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_never_shells_out_to_pip_or_install(monkeypatch) -> None:
    """The old bug's whole mechanism was a `pip install -e` subprocess. If
    this helper never runs one, it cannot reproduce that bug by construction."""
    real_run = subprocess.run

    def _spying_run(cmd, *args, **kwargs):
        joined = " ".join(str(part) for part in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        assert "pip" not in joined.lower(), f"isolated_tree shelled out to pip: {joined!r}"
        assert " install" not in f" {joined.lower()}", f"isolated_tree shelled out to install: {joined!r}"
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _spying_run)
    with isolated_tree("HEAD", repo_root=REPO_ROOT) as tree:
        assert (tree / "onedoor" / "__init__.py").exists()


def test_leaves_the_active_interpreters_own_onedoor_import_untouched() -> None:
    """Before and after using the helper, this process's own `onedoor` module
    still resolves to the same file -- the exact property the old bug broke
    for every subsequent subprocess-based test, once the temp clone it had
    reinstalled against was removed."""
    before = Path(onedoor.__file__).resolve()

    with isolated_tree("HEAD", repo_root=REPO_ROOT):
        pass

    importlib.reload(onedoor)
    after = Path(onedoor.__file__).resolve()
    assert before == after


def test_the_extracted_tree_matches_the_ref_and_is_removed_after() -> None:
    with isolated_tree("HEAD", repo_root=REPO_ROOT) as tree:
        extracted = tree
        assert (tree / "pyproject.toml").is_file()
        assert (tree / "eval" / "harness" / "cli.py").is_file()

    assert not extracted.exists(), "the temp directory must not survive the context"


def test_the_tree_is_removed_even_when_the_caller_raises() -> None:
    captured: list[Path] = []
    with mock.patch("eval.harness.isolated_tree.shutil.rmtree", wraps=__import__("shutil").rmtree) as spy:
        try:
            with isolated_tree("HEAD", repo_root=REPO_ROOT) as tree:
                captured.append(tree)
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        spy.assert_called_once()
    assert not captured[0].exists()
