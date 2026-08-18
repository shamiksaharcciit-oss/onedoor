"""The downstream command must survive both platforms' quoting rules.

`shlex.split` is POSIX by default and treats a backslash as an escape, so a
Windows interpreter path is silently mangled into a path that does not exist.
The spawn then fails with WinError 2 and the proxy cannot start at all. These
tests pin both branches from either platform, since the bug is only reachable
on one of them.
"""

from __future__ import annotations

from onedoor.mcp.proxy import split_command

WIN_CMD = r"C:\Users\a\.venv\Scripts\python.exe -m onedoor.mcp.demo_server"
POSIX_CMD = "/usr/bin/python3 -m onedoor.mcp.demo_server"


def test_windows_command_is_passed_through_unsplit() -> None:
    """Popen on Windows parses the string itself; splitting it here corrupts it."""
    assert split_command(WIN_CMD, windows=True) == WIN_CMD


def test_windows_path_backslashes_are_not_eaten() -> None:
    """The regression itself: POSIX splitting destroys the interpreter path."""
    posix_result = split_command(WIN_CMD, windows=False)
    assert isinstance(posix_result, list)
    assert "\\" not in posix_result[0]  # the damage, pinned so it stays visible
    assert split_command(WIN_CMD, windows=True) == WIN_CMD


def test_posix_command_is_split_into_argv() -> None:
    assert split_command(POSIX_CMD, windows=False) == [
        "/usr/bin/python3",
        "-m",
        "onedoor.mcp.demo_server",
    ]


def test_posix_quoting_still_honoured() -> None:
    assert split_command('/bin/sh -c "echo hi"', windows=False) == [
        "/bin/sh",
        "-c",
        "echo hi",
    ]
