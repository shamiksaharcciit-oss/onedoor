"""Run a gate and report it honestly. `python -m scripts.gate --all` (R049 §2).

Why this exists
-----------------
Three laws had accumulated about how a gate must be verified, and all three lived in
prose:

- **A verification claim about a gate must come from the gate's own commands, verbatim**
  (R010). *Exit codes travel badly; the output contract is the only thing that travels.*
- **A gate is a command and the world it runs in** (R048). *A green gate is a claim about
  an environment; state the environment or the claim is unbound.*
- And the trap that made both urgent: `cmd | tail` followed by `$?` reads **`tail`'s**
  status, not the gate's. Third appearance on this programme, documented throughout, and
  it landed anyway.

R044's ranking applies: *laws pushed into construction outrank laws kept in tests, which
outrank laws kept in memos.* All three were in the weakest tier while being cited as
though they were in the strongest. This module moves them into the first.

What it does that a hand-typed pipeline cannot
------------------------------------------------
The command runs through `subprocess` with **no shell and no pipe**, so there is no
second process whose exit status could be mistaken for the gate's. The gate passes only
when **both** halves hold: the process exited `0` **and** the declared output contract
appears. Either alone is not a pass — `python3` on Windows prints *"Python was not
found"* and exits `0`, and a passing exit code with no contract is exactly that failure
wearing a green hat.

Every run prints **what it ran, where, and with which versions**, so its output is
distinguishable from a hand-run transcript. R049 §2: *a control that is
indistinguishable from its own absence is not yet a control.*

The honest limit, which core ratified as the right standard: this helps only when it is
**called**. It does not eliminate what must be remembered; it reduces it to one atom —
*use the runner* — instead of per-command vigilance about pipes, `PIPESTATUS`, and which
process `$?` is carrying. *An irreducible remainder is not a failure of the tool; it is
the thing the tool exists to make small and conspicuous.*
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version


@dataclass(frozen=True)
class Gate:
    """One gate: the exact command, and a pattern that only its own output satisfies."""

    name: str
    command: tuple[str, ...]
    expect: str
    distribution: str

    def satisfied_by(self, output: str) -> bool:
        return re.search(self.expect, output) is not None


GATES: tuple[Gate, ...] = (
    Gate("lint", ("ruff", "check", "."), r"All checks passed!", "ruff"),
    Gate("format", ("ruff", "format", "--check", "."), r"\d+ files already formatted", "ruff"),
    Gate("types", ("mypy", "onedoor"), r"Success: no issues found in \d+ source files", "mypy"),
    Gate("tests", ("pytest", "-q"), r"\d+ passed", "pytest"),
)
r"""The four gates, declared once.

**The contracts are patterns, not substrings, and that is the fifth proxy-for-contract
instance being paid for.** The first draft of this table declared the tests gate as the
literal `" passed"` — which is a substring of ruff's *"All checks passed!"*, so the lint
gate's output would have satisfied the test gate's contract. Exactly the confusion that
made a monitor filter fire on the wrong line, reproduced inside the tool built to prevent
it, and caught by `test_no_pattern_matches_another_gates_real_output` on its first run.

`\d+ passed` cannot match *"All checks passed!"* because a pytest summary **counts**, and
a sentence merely asserts. Requiring the count is what turns a proxy into a contract.
"""


def _environment(gate: Gate) -> list[tuple[str, str]]:
    """What world this ran in. R048's law needs stating, not assuming."""
    try:
        tool = version(gate.distribution)
    except PackageNotFoundError:
        tool = "NOT INSTALLED — the gate cannot have checked anything"
    return [
        ("cwd", os.getcwd()),
        ("python", f"{platform.python_version()} ({platform.python_implementation()})"),
        ("platform", platform.platform()),
        (gate.distribution, tool),
    ]


def run(gate: Gate, *, echo: bool = True) -> bool:
    """Run one gate. True only if the exit code **and** the output contract both hold."""
    if echo:
        print(f"\n=== gate: {gate.name} — {' '.join(gate.command)}")
        for label, value in _environment(gate):
            print(f"  {label:<12} {value}")

    # No shell, no pipe. The command is a LIST, never a string: a path is data, and data
    # pasted into a language is code until you make it not be (R049 §2). A directory
    # named `C:\Users\...` or one with a space in it reaches the process unchanged
    # because nothing ever parsed it.
    completed = subprocess.run(  # noqa: S603 - fixed argv lists, shell=False by construction
        list(gate.command),
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    output = completed.stdout + completed.stderr
    contract = gate.satisfied_by(output)
    ok = completed.returncode == 0 and contract

    if echo:
        print(f"  exit code    {completed.returncode}")
        print(f"  contract     {gate.expect!r} {'FOUND' if contract else 'NOT FOUND'}")
        tail = [line for line in output.splitlines() if line.strip()][-3:]
        for line in tail:
            print(f"  > {line}")
        print(f"  {'GATE PASS' if ok else 'GATE FAIL'}  {gate.name}")
        if completed.returncode == 0 and not contract:
            # The failure mode this tool exists for: green exit, absent contract.
            print(
                "  ^ exited 0 but did not say so. An exit code alone is not a pass — "
                "this is the shape of `python3` printing 'Python was not found' and "
                "exiting 0."
            )
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.gate",
        description="Run a declared gate and report its exit code, output contract, and environment.",
    )
    parser.add_argument("--all", action="store_true", help="run every declared gate and summarise")
    parser.add_argument("gate", nargs="?", choices=[g.name for g in GATES])
    args = parser.parse_args(argv)

    if not args.all and args.gate is None:
        parser.error("name a gate, or pass --all")

    selected = GATES if args.all else tuple(g for g in GATES if g.name == args.gate)
    results = {gate.name: run(gate) for gate in selected}

    if args.all:
        print("\n=== summary")
        for name, ok in results.items():
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":  # pragma: no cover - the entry point
    raise SystemExit(main())
