"""Make a built sdist byte-identical across two builds from the same source.

`python -m build`'s sdist step (setuptools 84.0.0, this project's pinned
version) gives every **file** entry a deterministic mtime -- inherited from
`git archive`'s own `SOURCE_DATE_EPOCH` support, preserved through the copy
into setuptools' release tree -- but the **directories** that same release
tree creates to hold those files get `os.makedirs`'s real, build-wall-clock
mtime instead. Nothing in setuptools' sdist command or in `distutils`'s
`archive_util` reads `SOURCE_DATE_EPOCH` at all (checked directly, in this
pinned version's own source); there is no supported setting that closes
this, so the gap is closed here, after the fact, rather than left or worked
around by changing the pinned tool versions.

This rewrites every tar member's mtime to one pinned epoch, and replaces the
gzip wrapper with a deterministic one (mtime 0, no filename/extra/comment
fields -- written via a `fileobj`, which the stdlib `gzip` module never
stamps with a name). Member order and content are untouched; only mtime
metadata moves. Run after `python -m build` builds the sdist, naming the
exact file it just produced.
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import sys
import tarfile
from pathlib import Path


def rewrite(path: Path, epoch: int) -> None:
    """Rewrite `path` (a `.tar.gz` sdist) in place, pinning every member's
    mtime to `epoch` and the gzip wrapper to a deterministic header."""
    with gzip.open(path, "rb") as f:
        original_tar_bytes = f.read()

    src = tarfile.open(fileobj=io.BytesIO(original_tar_bytes), mode="r:")
    rebuilt = io.BytesIO()
    # GNU_FORMAT: the format setuptools' own tar writer already uses for an
    # sdist this size (any long path needs GNU's extension); matching it
    # keeps this rewrite a pure metadata change, never a format downgrade.
    dst = tarfile.open(fileobj=rebuilt, mode="w:", format=tarfile.GNU_FORMAT)
    for member in src.getmembers():
        member.mtime = epoch
        if member.isfile():
            dst.addfile(member, src.extractfile(member))
        else:
            dst.addfile(member)
    dst.close()
    src.close()

    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0) as gz:
        gz.write(rebuilt.getvalue())
    path.write_bytes(compressed.getvalue())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", type=Path, help="the built .tar.gz to rewrite in place")
    parser.add_argument(
        "--epoch",
        type=int,
        default=None,
        help="defaults to $SOURCE_DATE_EPOCH",
    )
    args = parser.parse_args(argv)
    epoch = args.epoch
    if epoch is None:
        raw = os.environ.get("SOURCE_DATE_EPOCH")
        if raw is None:
            parser.error("--epoch not given and $SOURCE_DATE_EPOCH is not set")
        epoch = int(raw)
    rewrite(args.sdist, epoch)
    print(f"rewrote {args.sdist} to mtime {epoch}, deterministic gzip header")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
