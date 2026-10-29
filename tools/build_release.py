"""Build onedoor's release wheel and sdist, through exactly one recipe.

A plain, isolated `python -m build` installs whatever `setuptools` PyPI is
currently serving to satisfy `pyproject.toml`'s own `build-system.requires`
(deliberately unpinned there -- an sdist installer is never held to this
repository's own release pins). That gap is what let a release candidate
ship a wheel built with setuptools 84.2.1 while this repository's own pin
stayed 84.0.0: the pin was real, nothing ever checked a build actually used
it.

This script is the one place that checks. It:

1. Refuses to run unless the active Python holds exactly the versions
   `requirements-build.txt` pins (`setuptools`, `wheel`, `build`) -- create
   that venv with `pip install -r requirements-build.txt --require-hashes`.
2. Sets `SOURCE_DATE_EPOCH` to HEAD's own committer time.
3. Builds from a clean `git archive HEAD` (never the working tree, which may
   hold uncommitted changes) with `python -m build --no-isolation` --
   `--no-isolation` is what makes step 1's check meaningful: an isolated
   build would reinstall its own setuptools regardless of what step 1 just
   confirmed.
4. Runs `reproducible_sdist.rewrite` on the sdist (directory entries and the
   gzip header otherwise carry the real build-wall-clock time; see that
   module's own docstring).
5. Prints four lines of its own, beside whatever `python -m build` prints
   (not captured, not suppressed): the tool versions actually used, the
   pinned epoch (and which commit it came from), and both sha256 values.

Run this from a git checkout, not a bare export: steps 2 and 3 call
`git rev-parse HEAD` and `git archive HEAD` themselves, which need a real
`.git` directory above `tools/`. A plain `git archive <ref>` of this script
alone has nothing to read `HEAD` from and exits before building anything.

Usage: `python tools/build_release.py [--outdir DIR]` (default: `./dist`).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import subprocess
import sys
import tarfile
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_VERSIONS: dict[str, str] = {
    "setuptools": "84.0.0",
    "wheel": "0.48.0",
    "build": "1.6.1",
}


def check_pinned_versions() -> None:
    """Refuse to build unless the active Python holds exactly these three
    versions. Does not check their dependencies (`packaging`,
    `pyproject_hooks`, `colorama`): those have no effect on the bytes a
    build produces the way the three build tools themselves do."""
    wrong: dict[str, str | None] = {}
    for package, expected in REQUIRED_VERSIONS.items():
        try:
            actual: str | None = installed_version(package)
        except PackageNotFoundError:
            actual = None
        if actual != expected:
            wrong[package] = actual
    if wrong:
        detail = ", ".join(
            f"{package} is {actual!r}, not {REQUIRED_VERSIONS[package]!r}"
            for package, actual in wrong.items()
        )
        raise SystemExit(
            f"refusing to build: {detail}. Create a venv with exactly the pinned "
            f"versions first: pip install -r requirements-build.txt --require-hashes"
        )


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def _head_sha_and_epoch() -> tuple[str, int]:
    sha = _git(["rev-parse", "HEAD"])
    epoch = _git(["log", "-1", "--format=%ct", "HEAD"])
    return sha, int(epoch)


def _extract_archive(ref: str, dest: Path) -> None:
    """`git archive <ref>` piped straight into `tarfile`, never through a
    shell `tar` binary -- this runs the same way whether or not one is on
    PATH."""
    proc = subprocess.run(["git", "archive", ref], cwd=REPO_ROOT, check=True, capture_output=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as tar:
        tar.extractall(dest, filter="data")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(outdir: Path) -> tuple[Path, Path]:
    check_pinned_versions()
    sha, epoch = _head_sha_and_epoch()

    import tempfile

    with tempfile.TemporaryDirectory(prefix="onedoor-release-") as tmp:
        tree = Path(tmp) / "tree"
        tree.mkdir()
        _extract_archive("HEAD", tree)
        env = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch)}
        subprocess.run(
            [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(outdir)],
            cwd=tree,
            env=env,
            check=True,
        )

    (sdist,) = outdir.glob("*.tar.gz")
    (wheel,) = outdir.glob("*.whl")

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from reproducible_sdist import rewrite as rewrite_sdist

    rewrite_sdist(sdist, epoch)

    tool_versions = ", ".join(f"{p} {installed_version(p)}" for p in REQUIRED_VERSIONS)
    print(tool_versions)
    print(f"SOURCE_DATE_EPOCH={epoch} (head {sha})")
    print(f"{_sha256(wheel)}  {wheel.name}")
    print(f"{_sha256(sdist)}  {sdist.name}")
    return wheel, sdist


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir", type=Path, default=REPO_ROOT / "dist", help="where to write the built files"
    )
    args = parser.parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)
    build(args.outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
