"""scripts.normalize_sdist: the sdist reproducibility fix, and its own self-check.

Found the hard way: a release build that built the sdist twice and diffed the two
results byte-for-byte saw the wheel match and the sdist not -- `setuptools`'s own
`egg_info` command stamps its directory to the real wall-clock time on every build
(`os.utime(self.egg_info, None)`, no `SOURCE_DATE_EPOCH` involved), and the stdlib
`tarfile` module's streaming gzip writer hardcodes `time.time()` for the gzip header's
own mtime. This module rewrites an already-built sdist after the fact, pinning every
member's mtime (and the gzip header's) to a given `SOURCE_DATE_EPOCH`, so two builds of
the same commit can be compared.
"""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from scripts.normalize_sdist import (
    RefusedMember,
    VerificationFailed,
    main,
    normalize,
    verify,
)

EPOCH = 1700000000


def _make_sdist(
    path: Path,
    members: list[tuple[str, str, bytes | None, float, dict[str, str] | None]],
) -> None:
    """Builds a tiny PAX-format sdist at `path` from `members`, each a
    (name, type, content, mtime, extra_pax_headers) tuple. `type` is one of
    "file", "dir", "symlink". A fractional `mtime` makes tarfile itself emit a
    real PAX "mtime" extended header (see tarfile.TarInfo.create_pax_header) --
    exactly the shape a real sdist can carry and this tool must strip."""
    with tarfile.open(path, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        for name, kind, content, mtime, extra_pax in members:
            info = tarfile.TarInfo(name=name)
            info.mtime = mtime
            if extra_pax:
                info.pax_headers = dict(extra_pax)
            if kind == "file":
                assert content is not None
                info.type = tarfile.REGTYPE
                info.mode = 0o644
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.mode = 0o777
                info.linkname = "target"
                tar.addfile(info)
            else:
                raise ValueError(kind)


def _real_sdist_fixture(path: Path) -> None:
    _make_sdist(
        path,
        [
            ("pkg-1.0.0", "dir", None, 1700000123.456, None),
            ("pkg-1.0.0/PKG-INFO", "file", b"Metadata-Version: 2.1\n", 1700000124.789, None),
            (
                "pkg-1.0.0/pkg.egg-info",
                "dir",
                None,
                1700000125.111,
                {"atime": "1700000125.111", "ctime": "1700000125.111"},
            ),
            (
                "pkg-1.0.0/pkg.egg-info/SOURCES.txt",
                "file",
                b"pkg/__init__.py\n",
                1700000126.222,
                None,
            ),
            ("pkg-1.0.0/pkg", "dir", None, 1700000120.0, None),
            ("pkg-1.0.0/pkg/__init__.py", "file", b"", 1700000119.5, None),
        ],
    )


# --- the normalizer's own job: rewritten metadata, unchanged content --------------


def test_mtime_is_pinned_on_every_member(tmp_path: Path) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _real_sdist_fixture(src)
    normalize(src, out, EPOCH)
    with tarfile.open(out, mode="r:gz") as t:
        for member in t.getmembers():
            assert member.mtime == EPOCH, member.name


def test_pax_mtime_atime_ctime_do_not_survive(tmp_path: Path) -> None:
    """The planted fixture carries a real PAX mtime (from a fractional source
    mtime) and explicit PAX atime/ctime on one directory -- none of the three
    may still be present as extended headers afterward."""
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _real_sdist_fixture(src)

    with tarfile.open(src, mode="r:gz") as t:
        assert any("mtime" in m.pax_headers for m in t.getmembers()), (
            "fixture does not actually carry a PAX mtime -- test proves nothing"
        )
        assert any("atime" in m.pax_headers for m in t.getmembers())

    normalize(src, out, EPOCH)
    with tarfile.open(out, mode="r:gz") as t:
        for member in t.getmembers():
            assert "mtime" not in member.pax_headers, member.name
            assert "atime" not in member.pax_headers, member.name
            assert "ctime" not in member.pax_headers, member.name


def test_a_real_owner_is_still_zeroed(tmp_path: Path) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    with tarfile.open(src, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        info = tarfile.TarInfo(name="f")
        info.type = tarfile.REGTYPE
        info.mode = 0o644
        info.size = 1
        info.mtime = 1700000000
        info.uid = 1000
        info.gid = 1000
        info.uname = "someone"
        info.gname = "somegroup"
        tar.addfile(info, io.BytesIO(b"x"))

    normalize(src, out, EPOCH)
    with tarfile.open(out, mode="r:gz") as t:
        member = t.getmembers()[0]
        assert (member.uid, member.gid, member.uname, member.gname) == (0, 0, "", "")


def test_member_order_and_names_are_unchanged(tmp_path: Path) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _real_sdist_fixture(src)
    normalize(src, out, EPOCH)
    with tarfile.open(src, mode="r:gz") as a, tarfile.open(out, mode="r:gz") as b:
        assert [m.name for m in b.getmembers()] == [m.name for m in a.getmembers()]


def test_file_content_is_byte_identical(tmp_path: Path) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _real_sdist_fixture(src)
    normalize(src, out, EPOCH)
    with tarfile.open(src, mode="r:gz") as a, tarfile.open(out, mode="r:gz") as b:
        for ma, mb in zip(a.getmembers(), b.getmembers()):
            if ma.isreg():
                assert a.extractfile(ma).read() == b.extractfile(mb).read()


def test_the_gzip_headers_own_mtime_is_pinned_and_carries_no_filename(tmp_path: Path) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _real_sdist_fixture(src)
    normalize(src, out, EPOCH)
    with open(out, "rb") as f:
        header = f.read(10)
    assert header[:2] == b"\x1f\x8b"  # gzip magic
    flg = header[3]
    assert flg & 0x08 == 0, "FNAME flag set -- a filename was written into the gzip header"
    mtime_field = int.from_bytes(header[4:8], "little")
    assert mtime_field == EPOCH


# --- the required behaviours, named exactly as asked -----------------------------


def test_normalizing_twice_gives_identical_bytes(tmp_path: Path) -> None:
    """A planted sdist with fractional PAX mtimes, normalised twice (two separate,
    independent calls -- not comparing a file to itself), gives identical bytes."""
    src = tmp_path / "in.tar.gz"
    out_a = tmp_path / "out_a.tar.gz"
    out_b = tmp_path / "out_b.tar.gz"
    _real_sdist_fixture(src)

    normalize(src, out_a, EPOCH)
    normalize(src, out_b, EPOCH)

    assert out_a.read_bytes() == out_b.read_bytes()


def test_a_planted_single_byte_change_makes_verification_fail(tmp_path: Path) -> None:
    """`verify()` is the self-check `main()` runs after every normalize() -- a one-byte
    content change in an otherwise-identical archive must fail it, not pass silently."""
    src = tmp_path / "in.tar.gz"
    tampered = tmp_path / "tampered.tar.gz"
    _make_sdist(src, [("f", "file", b"hello", EPOCH, None)])
    _make_sdist(tampered, [("f", "file", b"hellO", EPOCH, None)])  # one byte differs

    with pytest.raises(VerificationFailed, match="content differs"):
        verify(src, tampered)


def test_verification_passes_for_a_true_normalization(tmp_path: Path) -> None:
    """The positive case the above is the negative of: a real normalize() output
    must pass its own verify() against the input it was built from."""
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _real_sdist_fixture(src)
    normalize(src, out, EPOCH)
    verify(src, out)  # must not raise


def test_a_symlink_member_is_refused(tmp_path: Path) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _make_sdist(
        src,
        [
            ("f", "file", b"x", EPOCH, None),
            ("link", "symlink", None, EPOCH, None),
        ],
    )
    with pytest.raises(RefusedMember, match="link"):
        normalize(src, out, EPOCH)


# --- the CLI ----------------------------------------------------------------------


def test_cli_reads_source_date_epoch_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _real_sdist_fixture(src)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH))
    rc = main([str(src), str(out)])
    assert rc == 0
    with tarfile.open(out, mode="r:gz") as t:
        assert t.getmembers()[0].mtime == EPOCH


def test_cli_fails_without_an_epoch_from_either_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _real_sdist_fixture(src)
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    with pytest.raises(SystemExit):
        main([str(src), str(out)])


def test_cli_returns_nonzero_and_does_not_raise_on_a_refused_member(tmp_path: Path) -> None:
    src = tmp_path / "in.tar.gz"
    out = tmp_path / "out.tar.gz"
    _make_sdist(src, [("link", "symlink", None, EPOCH, None)])
    rc = main([str(src), str(out), "--source-date-epoch", str(EPOCH)])
    assert rc == 1
