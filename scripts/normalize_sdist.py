"""Rewrites a built sdist (`.tar.gz`) so that building the same commit twice produces
byte-identical output.

Found the hard way: a release build that builds the sdist twice and diffs the results
saw the wheel match and the sdist not. Neither of the two places that write a tarball's
timestamps reads `SOURCE_DATE_EPOCH` at all -- `setuptools.command.egg_info.run()` calls
`os.utime(self.egg_info, None)`, stamping that directory (and everything it regenerates
under it: `PKG-INFO`, `SOURCES.txt`, ...) to the real wall-clock time on every build; and
the stdlib `tarfile` module's own streaming gzip writer hardcodes
`struct.pack("<L", int(time.time()))` for the gzip header's own mtime field. Both are the
tool's behaviour, not a defect in the package being built -- so the fix lives here, in
release tooling that runs AFTER the real build, never inside `onedoor/` itself.

This module is not part of what ships: `onedoor/` (the wheel) and the sdist's own file
list don't reach `scripts/` at all (confirmed empirically against a real build before
this was written), so this file is never a member of the archive it rewrites.

What it does, given an already-built sdist and a `SOURCE_DATE_EPOCH`:
- Reads every member, in the archive's own order. Only a regular file or a directory is
  accepted -- anything else (a symlink, a hardlink, a device, a fifo) is refused outright,
  not silently skipped, since this tool has no reasoned way to say an unexpected member
  type should keep whatever timestamp or ownership it already carries.
- Writes a new archive with the same members, in the same order: name, mode, size, type
  and bytes unchanged; `mtime` pinned to `SOURCE_DATE_EPOCH` on every member; no PAX
  `mtime`/`atime`/`ctime` extended header surviving on any of them (a member built from
  scratch here never gets one in the first place -- tarfile only ever adds one because a
  caller set a fractional `.mtime` or populated `pax_headers` directly, and this code does
  neither); `uid`/`gid` zeroed, `uname`/`gname` emptied; written in PAX format.
- The gzip wrapper itself is written with `gzip.GzipFile(filename="", mtime=SOURCE_DATE_EPOCH,
  compresslevel=9)` -- no filename recorded, no wall-clock time in the header tarfile's own
  streaming writer would otherwise have stamped there.
- Then reads BOTH archives back and checks the result against the input: the same member
  names in the same order, the same type, mode and size for each, and the same bytes for
  every regular file. Only `mtime` may differ. Any other difference exits non-zero -- this
  tool rewrites metadata, and a content difference anywhere means it did something it had
  no business doing, not that the comparison should be loosened.

Usage: python -m scripts.normalize_sdist <input.tar.gz> <output.tar.gz> [--source-date-epoch N]
`--source-date-epoch` defaults to the `SOURCE_DATE_EPOCH` environment variable.
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import sys
import tarfile
from pathlib import Path

SOURCE_DATE_EPOCH_ENV = "SOURCE_DATE_EPOCH"

_TIME_PAX_KEYS = ("mtime", "atime", "ctime")


class RefusedMember(Exception):
    """A tar member that is not a plain regular file or directory."""


class VerificationFailed(Exception):
    """The normalized output differs from the input in something other than mtime."""


def _normalized_tarinfo(member: tarfile.TarInfo, epoch: int) -> tarfile.TarInfo:
    if not (member.isreg() or member.isdir()):
        raise RefusedMember(
            f"{member.name}: not a regular file or directory (type {member.type!r}) -- refused"
        )
    info = tarfile.TarInfo(name=member.name)
    info.type = member.type
    info.mode = member.mode
    info.size = member.size if member.isreg() else 0
    info.mtime = int(epoch)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    # Built fresh above, not copied from `member.pax_headers` -- so there is no PAX
    # mtime/atime/ctime to begin with. The explicit filter is still here, and still
    # applied, so a future change to build this by copying the original header first
    # can't silently let one of the three back in without this line catching it.
    info.pax_headers = {k: v for k, v in member.pax_headers.items() if k not in _TIME_PAX_KEYS}
    return info


def normalize(input_path: Path, output_path: Path, epoch: int) -> None:
    with tarfile.open(input_path, mode="r:gz") as src:
        members = src.getmembers()
        contents: dict[str, bytes] = {}
        for member in members:
            if member.isreg():
                fileobj = src.extractfile(member)
                contents[member.name] = fileobj.read() if fileobj is not None else b""

        with open(output_path, "wb") as raw:
            with gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", mtime=int(epoch), compresslevel=9
            ) as gz:
                with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT) as dst:
                    for member in members:
                        new_info = _normalized_tarinfo(member, epoch)
                        if new_info.isreg():
                            dst.addfile(new_info, io.BytesIO(contents[member.name]))
                        else:
                            dst.addfile(new_info)


def verify(input_path: Path, output_path: Path) -> None:
    with tarfile.open(input_path, mode="r:gz") as a, tarfile.open(output_path, mode="r:gz") as b:
        a_members = a.getmembers()
        b_members = b.getmembers()
        a_names = [m.name for m in a_members]
        b_names = [m.name for m in b_members]
        if a_names != b_names:
            raise VerificationFailed(f"member names/order differ: {a_names!r} vs {b_names!r}")
        for a_member, b_member in zip(a_members, b_members):
            if a_member.type != b_member.type:
                raise VerificationFailed(
                    f"{a_member.name}: type differs ({a_member.type!r} vs {b_member.type!r})"
                )
            if a_member.mode != b_member.mode:
                raise VerificationFailed(
                    f"{a_member.name}: mode differs ({a_member.mode!r} vs {b_member.mode!r})"
                )
            if a_member.size != b_member.size:
                raise VerificationFailed(
                    f"{a_member.name}: size differs ({a_member.size!r} vs {b_member.size!r})"
                )
            if a_member.isreg():
                a_file = a.extractfile(a_member)
                b_file = b.extractfile(b_member)
                assert a_file is not None and b_file is not None  # isreg() guarantees this
                if a_file.read() != b_file.read():
                    raise VerificationFailed(f"{a_member.name}: content differs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.normalize_sdist",
        description=(
            "Rewrites a built sdist so every member's mtime (and the gzip header's own "
            "mtime) is pinned to SOURCE_DATE_EPOCH, uid/gid zeroed -- so two separate "
            "builds of the same commit produce a byte-identical sdist."
        ),
    )
    parser.add_argument("input", type=Path, help="the sdist .tar.gz to read")
    parser.add_argument("output", type=Path, help="where to write the normalized .tar.gz")
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=None,
        help=f"defaults to the {SOURCE_DATE_EPOCH_ENV} environment variable",
    )
    args = parser.parse_args(argv)

    epoch = args.source_date_epoch
    if epoch is None:
        env_value = os.environ.get(SOURCE_DATE_EPOCH_ENV)
        if env_value is None:
            parser.error(f"--source-date-epoch not given and {SOURCE_DATE_EPOCH_ENV} is not set")
        epoch = int(env_value)

    try:
        normalize(args.input, args.output, epoch)
    except RefusedMember as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    try:
        verify(args.input, args.output)
    except VerificationFailed as exc:
        print(f"VERIFY FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"normalized: {args.output} (SOURCE_DATE_EPOCH={epoch})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
