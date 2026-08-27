"""The gate runner's companion (R049 §2). Three classes, held structurally.

R049 approved two layers and named two of the three instances that landed while `0.5.0`
was being cut as **old classes wearing new clothes**. Both become tests here rather than
cautionary notes, which is the whole point of the ticket:

1. **`$?` after a pipe** — the trap itself. No committed shell may read an exit status
   that belongs to the last stage of a pipeline rather than to the gate.
2. **Proxy-for-contract, fifth instance** — a monitor filter matching `passed` fired on
   ruff's *"All checks passed!"* instead of a pytest summary. A proxy matches whatever
   else happens to say it, so the declared contracts must not be able to match each
   other.
3. **A path is data, and data pasted into a language is code until you make it not be** —
   a heredoc mangled `\\U` inside a Windows path. The runner must never build a command
   by string interpolation.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import gate

ROOT = Path(__file__).resolve().parent.parent
GATE_SOURCE = Path(gate.__file__)

SHELL_BEARING = (
    list(ROOT.glob(".github/workflows/*.yml"))
    + list(ROOT.glob("scripts/*.sh"))
    + list(ROOT.glob("*.md"))
)

PIPE_THEN_STATUS = re.compile(
    r"\|[^\n|]*\n?[^\n]*?\$\?"  # a pipe, then `$?` before the next blank line
)
FENCE = re.compile(r"```(?:bash|sh|shell|powershell|console)\n(.*?)```", re.S)


# --- 1. The trap itself -----------------------------------------------------------


def _shell_blocks(path: Path) -> list[str]:
    """Shell text in a file: whole file for scripts/workflows, fenced blocks for docs."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".md":
        return FENCE.findall(text)
    return [text]


def test_no_committed_shell_reads_a_status_that_belongs_to_a_pipe() -> None:
    """`cmd | tail` then `$?` reads *tail's* status. Third appearance, now a test.

    Scanned rather than remembered: every workflow, every `scripts/*.sh`, and every
    fenced shell block in the repo's markdown — which is where handovers live, and a
    handover is a script somebody pastes.
    """
    offenders: dict[str, list[str]] = {}
    for path in SHELL_BEARING:
        for block in _shell_blocks(path):
            for line in block.splitlines():
                if "$?" not in line:
                    continue
                if "PIPESTATUS" in line or "pipefail" in line:
                    continue
                if "|" in line.split("$?")[0]:
                    offenders.setdefault(str(path.relative_to(ROOT)), []).append(line.strip())
    assert not offenders, (
        f"committed shell reads `$?` after a pipe: {offenders}. That is the last "
        "command's status, not the gate's. Use `python -m scripts.gate`, or take "
        "PIPESTATUS[0] deliberately."
    )


def test_the_runner_never_pipes_a_gate_into_anything() -> None:
    """Structural: `shell=False`, and the command is a list, never a formatted string."""
    tree = ast.parse(GATE_SOURCE.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"run", "call", "check_output", "Popen"}
    ]
    assert calls, "the runner does not call subprocess at all"
    for call in calls:
        shell = [k for k in call.keywords if k.arg == "shell"]
        assert shell, "subprocess call without an explicit `shell=`"
        assert isinstance(shell[0].value, ast.Constant) and shell[0].value.value is False, (
            "the runner must pass shell=False — a shell is what re-parses a path"
        )
        first = call.args[0]
        assert not isinstance(first, ast.JoinedStr | ast.BinOp), (
            "the command is built by string interpolation; it must be a list"
        )


# --- 2. Proxy-for-contract, fifth instance ----------------------------------------


def _run(g: gate.Gate, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """What this gate actually prints, run for real.

    The tests gate runs `pytest -q` over a generated one-test file rather than the whole
    suite: running the suite from inside the suite recurses, and a recorded sample would
    be a fixture that drifts from the tool it claims to describe. A tiny real run is
    genuine pytest output.
    """
    if g.name == "tests":
        probe = tmp_path / "test_probe.py"
        probe.write_text("def test_ok() -> None:\n    assert True\n", encoding="utf-8")
        command = [sys.executable, "-m", "pytest", "-q", str(probe), "-p", "no:cacheprovider"]
        cwd = tmp_path
    else:
        command, cwd = list(g.command), ROOT
    return subprocess.run(  # noqa: S603 - fixed argv from the declared table
        command, capture_output=True, text=True, shell=False, check=False, cwd=cwd
    )


def _real_output(g: gate.Gate, tmp_path: Path) -> str:
    return (lambda c: c.stdout + c.stderr)(_run(g, tmp_path))


def test_each_pattern_matches_its_own_gates_real_output(tmp_path: Path) -> None:
    """A contract nothing emits would fail every run forever.

    **Three outcomes, not two.** If the gate itself is currently red, this test cannot
    tell a badly-written contract from a repository that simply does not pass — that is
    *unverifiable*, and R010 says an unverifiable result is surfaced, never collapsed
    into the failure next to it. An earlier version reported "the gate can never pass"
    whenever `mypy` had an error, which sent the reader hunting for a contract bug that
    was not there.
    """
    for g in gate.GATES:
        completed = _run(g, tmp_path)
        output = completed.stdout + completed.stderr
        if completed.returncode != 0:
            raise AssertionError(
                f"the {g.name} gate is currently RED, so its contract could not be "
                f"checked here. This is not a contract defect — fix the gate first. "
                f"Tail: {output.strip().splitlines()[-1] if output.strip() else '(no output)'}"
            )
        assert g.satisfied_by(output), (
            f"{g.name}'s contract {g.expect!r} does not appear in its own PASSING "
            "output — the gate can never report success"
        )


def test_no_pattern_matches_another_gates_real_output(tmp_path: Path) -> None:
    """The fifth proxy-for-contract instance, encoded as the confusion that occurred.

    Not substring containment between the declared strings — **the real thing**: one
    gate's output must not satisfy another gate's contract. The first draft of the table
    declared the tests gate as the literal `" passed"`, which ruff's *"All checks
    passed!"* satisfies, so a lint run would have counted as a passing test run. This
    test caught it on its first execution, inside the tool built to prevent exactly that
    confusion.
    """
    outputs = {g.name: _real_output(g, tmp_path) for g in gate.GATES}
    for g in gate.GATES:
        for other_name, other_output in outputs.items():
            if other_name == g.name:
                continue
            assert not g.satisfied_by(other_output), (
                f"{g.name}'s contract {g.expect!r} is satisfied by {other_name}'s "
                f"output — one gate can be marked green by another gate's words"
            )


def test_no_contract_is_a_bare_common_word() -> None:
    """`passed` alone is a proxy; a pattern requiring a **count** is a contract."""
    for g in gate.GATES:
        assert g.expect.strip() != "passed"
        assert len(g.expect) >= 7, f"{g.name}'s contract {g.expect!r} is too generic"


# --- 3. A path is data ------------------------------------------------------------


def test_a_path_with_a_backslash_escape_survives_the_runner(tmp_path: Path) -> None:
    r"""`C:\Users\...` contains `\U`, which is an escape in several languages.

    The heredoc that mangled it was building a command by pasting a path into source.
    The runner passes argv as a list, so nothing ever parses the path — asserted by
    round-tripping a directory whose name carries the exact hazard.
    """
    hostile = tmp_path / "Users" / "unicode-\\U-and space"
    hostile.mkdir(parents=True)
    marker = hostile / "marker.txt"
    marker.write_text("contract-token", encoding="utf-8")

    completed = subprocess.run(  # noqa: S603 - a fixed interpreter with a list argv
        [sys.executable, "-c", "import sys; print(open(sys.argv[1]).read())", str(marker)],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "contract-token" in completed.stdout


# --- The runner's own behaviour ---------------------------------------------------


def test_a_green_exit_with_no_contract_is_a_failure(capsys: pytest.CaptureFixture[str]) -> None:
    """The `python3`-on-Windows shape: exits 0, checked nothing, must not pass.

    This is the failure the whole tool exists for, so it is asserted rather than
    described.
    """
    liar = gate.Gate(
        name="liar",
        command=(sys.executable, "-c", "print('Python was not found')"),
        expect="Success: no issues found in",
        distribution="mypy",
    )
    assert gate.run(liar) is False
    out = capsys.readouterr().out
    assert "exit code    0" in out
    assert "NOT FOUND" in out
    assert "exited 0 but did not say so" in out


def test_a_nonzero_exit_with_the_contract_present_is_also_a_failure() -> None:
    """Both halves, not either. A contract in the output of a failing process is noise."""
    contradictory = gate.Gate(
        name="contradictory",
        command=(sys.executable, "-c", "print('All checks passed!'); raise SystemExit(3)"),
        expect="All checks passed!",
        distribution="ruff",
    )
    assert gate.run(contradictory, echo=False) is False


def test_the_runner_prints_what_it_ran_and_where(capsys: pytest.CaptureFixture[str]) -> None:
    """R049 §2: a control indistinguishable from its own absence is not yet a control."""
    ok = gate.Gate(
        name="ok",
        command=(sys.executable, "-c", "print('All checks passed!')"),
        expect="All checks passed!",
        distribution="ruff",
    )
    assert gate.run(ok) is True
    out = capsys.readouterr().out
    assert "gate: ok" in out
    assert "cwd" in out and "python" in out and "platform" in out
    assert "GATE PASS" in out


def test_a_missing_tool_is_reported_as_having_checked_nothing() -> None:
    """An absent distribution is not a version string, and must not read as one."""
    absent = gate.Gate(
        name="absent",
        command=(sys.executable, "-c", "print('x')"),
        expect="x",
        distribution="a-distribution-that-does-not-exist",
    )
    labels = dict(gate._environment(absent))
    assert "NOT INSTALLED" in labels["a-distribution-that-does-not-exist"]
    assert "cannot have checked anything" in labels["a-distribution-that-does-not-exist"]
