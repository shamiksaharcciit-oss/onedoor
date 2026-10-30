"""`python -m onedoor.viewer`'s own CLI: the one write path this module has.

The page is written in binary mode, deliberately, not `Path.write_text`: text mode
applies universal-newline translation, which on Windows turns every `\n` into `\r\n`
on write -- changing the bytes on disk without changing the length `main()` already
computed and printed, so the printed byte count would describe a file that was never
written.
"""

from __future__ import annotations

from onedoor.viewer.__main__ import main


def test_the_written_file_has_no_crlf(tmp_path, capsys) -> None:
    store = tmp_path / "demo.db"
    out = tmp_path / "page.html"
    assert main(["--demo-store", str(store), "--out", str(out)]) == 0

    raw = out.read_bytes()
    assert b"\r\n" not in raw, "the page must be written LF-only, regardless of platform"


def test_the_printed_byte_count_matches_the_files_real_size(tmp_path, capsys) -> None:
    store = tmp_path / "demo.db"
    out = tmp_path / "page.html"
    assert main(["--demo-store", str(store), "--out", str(out)]) == 0

    printed = capsys.readouterr().out
    reported = int(printed.split("(")[1].split(" bytes)")[0])
    assert reported == out.stat().st_size, (
        "the byte count main() prints must be the size of the file it actually wrote"
    )
