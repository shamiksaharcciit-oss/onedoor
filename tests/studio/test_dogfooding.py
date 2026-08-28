"""Every command in `docs/DOGFOODING.md`, executed before a person types it.

R064 §5: *the walkthrough is a served artifact — every command in it is executed by a test
before a person ever types it. An untested walkthrough command has bitten this programme
before; it does not get a second chance.*

**The commands are read out of the document**, not copied here. A test that ran
*similar* commands would drift from the file the moment either changed, and the drift
would be invisible: the test would pass, the walkthrough would be wrong, and the person
following it would find out. Same reasoning as X-11 — the artifact and the check share one
source.

Two commands cannot run offline. They are named in `NOT_EXECUTED` with the reason, the
document says so at the top, and what *is* checkable about them is checked: the extra
exists and everything it names imports. **Absent, unverifiable and failed stay apart**,
including here.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WALKTHROUGH = ROOT / "docs" / "DOGFOODING.md"

CHECKED_NOT_RUN = {
    "python -m venv .venv": "creating a virtualenv would test venv, not onedoor",
    '.venv/bin/pip install -e ".[studio]"': "installing needs the network CI does not give",
    "python -m onedoor.studio --db onedoor.db --studio-db studio.db --port 8787": (
        "it serves until stopped; its argv goes through the real parser instead"
    ),
    "curl -X POST 'http://127.0.0.1:8787/drafts' --data-urlencode 'title=first policy set'": (
        "CI need not have curl; the route and field it names are checked against the app"
    ),
}
"""Commands validated rather than executed, each with its reason.

**Four, not two.** The first draft of this file said two and called the rest executed,
which was wrong about the start command and the curl line — both are *checked*, not run.
A walkthrough claiming more testing than it has is the overclaim this project spends its
time removing from other people's pages; it does not get to keep one of its own.

Everything not listed here is run to completion, with its exit code asserted.
"""


def _commands() -> list[str]:
    """Every fenced `shell` command in the walkthrough, in document order."""
    text = WALKTHROUGH.read_text(encoding="utf-8")
    blocks = re.findall(r"```shell\n(.*?)```", text, re.S)
    return [line.strip() for block in blocks for line in block.splitlines() if line.strip()]


# --- The document and this test cannot drift apart -------------------------------------


def test_the_walkthrough_exists_and_has_commands() -> None:
    assert WALKTHROUGH.is_file(), "the walkthrough is gone; this test guards nothing"
    assert len(_commands()) >= 6


#: Run to completion by a test below, exit code asserted. Named here so the two lists
#: together must account for every command in the document — a command in neither is a
#: command nobody checked, and it fails the test below rather than reaching a person.
RUN = {
    "python -m onedoor.studio --help",
    "python -m onedoor.studio.walkthrough --db onedoor.db",
    "python -m onedoor.studio.verify receipt.json snapshot.json",
}


def test_every_command_is_accounted_for_as_run_or_as_checked() -> None:
    """**The claim the document makes at the top, checked against the document.**

    A walkthrough that says every command is tested, with an unexamined command in it, is
    worse than one that says nothing — it spends trust it has not earned. So the two
    lists must partition the document exactly: nothing missing, nothing invented.
    """
    commands = set(_commands())
    accounted = RUN | set(CHECKED_NOT_RUN)
    assert commands - accounted == set(), (
        f"commands in the walkthrough that nothing checks: {sorted(commands - accounted)}"
    )
    assert accounted - commands == set(), (
        f"commands this test claims to check that the walkthrough does not contain: "
        f"{sorted(accounted - commands)}"
    )
    assert RUN & set(CHECKED_NOT_RUN) == set(), "a command is claimed as both run and checked"


def test_the_document_marks_each_command_run_or_checked() -> None:
    """The distinction is visible to the person following the walkthrough, not only to
    the test. **An exemption nobody reading the document can see is a silent one.**"""
    text = WALKTHROUGH.read_text(encoding="utf-8")
    assert text.count("`[run]`") >= 3
    assert text.count("`[checked]`") >= 4
    assert "tests/studio/test_dogfooding.py" in text


# --- The exemptions, checked as far as they can be --------------------------------------


def test_the_studio_extra_exists_and_everything_it_names_imports() -> None:
    """What replaces executing `pip install -e ".[studio]"`.

    Not "we could not check this" — the *installable* claim is checkable even when the
    install is not runnable here.
    """
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = config["project"]["optional-dependencies"]
    assert "studio" in extras, "the walkthrough installs an extra that does not exist"
    assert extras["studio"], "the studio extra names nothing"

    import importlib

    for requirement in extras["studio"]:
        module = re.split(r"[<>=!\[ ]", requirement)[0].replace("-", "_")
        importlib.import_module(module)


# --- The executed commands ----------------------------------------------------------------


def _run(command: str, cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run a walkthrough command with THIS interpreter, never a bare `python`.

    R010's own trap: on Windows a bare `python3` prints "Python was not found" and exits
    0, so a gate can pass while running nothing. The document says `python` meaning the
    virtualenv's interpreter; here that is `sys.executable`, stated rather than assumed.
    """
    parts = shlex.split(command)
    assert parts[0] == "python", f"only `python ...` commands run here: {command}"
    return subprocess.run(
        [sys.executable, *parts[1:]],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_step_2_the_help_command_runs_and_names_its_flags(tmp_path) -> None:
    command = next(c for c in _commands() if c.endswith("--help"))
    result = _run(command, tmp_path)
    assert result.returncode == 0, result.stderr
    for flag in ("--db", "--studio-db", "--host", "--port"):
        assert flag in result.stdout, f"{flag} is documented and absent from --help"


def test_step_3_the_start_command_is_accepted_by_the_parser(tmp_path) -> None:
    """The one command that cannot simply be run to completion — it serves forever.

    Its **arguments** are executed against the real parser, which is what could actually
    be wrong in a written command: a renamed flag, a changed default, a typo. Serving is
    covered by `test_server_served.py`, over a real socket.
    """
    from onedoor.studio.__main__ import main as studio_main

    command = next(c for c in _commands() if "--studio-db" in c and "--help" not in c)
    argv = shlex.split(command)[3:]
    assert argv[0].startswith("--"), f"unexpected shape: {command}"

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--studio-db")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parsed = parser.parse_args(argv)
    assert parsed.db == "onedoor.db", "the walkthrough's --db is not the one F-H needs"
    assert parsed.studio_db == "studio.db"
    assert parsed.port == 8787

    # And the real parser accepts the same argv, refusing on a bad flag rather than
    # silently ignoring it.
    with pytest.raises(SystemExit) as exit_info:
        studio_main([*argv, "--not-a-flag"])
    assert exit_info.value.code == 2


def test_step_5_the_curl_line_posts_where_the_app_actually_routes() -> None:
    """`curl` is not run — CI need not have it — but the **claim inside it** is checked
    against the app's own route table and its own field name.

    That is what could be wrong in a written curl line, and it is exactly the class of
    error that stranded F-G's one-liner when Drafts moved to `/drafts`.
    """
    from onedoor.studio import server

    command = next(c for c in _commands() if c.startswith("curl "))
    url = re.search(r"'(http://[^']+)'", command).group(1)
    field = re.search(r"--data-urlencode '([^=]+)=", command).group(1)

    path = url.split("127.0.0.1:8787", 1)[1]
    state = server.open_state(":memory:", ":memory:")
    try:
        app = server.create_app(state)
        posts = {r.path for r in app.routes if "POST" in getattr(r, "methods", set())}
        assert path in posts, f"the walkthrough curls {path}, which the app does not POST"
    finally:
        state.close()
    assert field == "title", f"the form field is named {field!r}, not `title`"


def test_step_7_the_decision_command_runs_and_writes_one_audit_row(tmp_path) -> None:
    command = next(c for c in _commands() if "walkthrough" in c)
    result = _run(command, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "payments.transfer" in result.stdout

    from onedoor.store.db import Database

    conn = Database(str(tmp_path / "onedoor.db")).connect()
    try:
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM actions_audit WHERE kind='decision'"
        ).fetchone()["n"]
    finally:
        conn.close()
    assert rows == 1, "the walkthrough's decision step wrote no decision"


def test_step_8_the_verify_command_runs_on_a_receipt_this_walkthrough_produced(
    tmp_path,
) -> None:
    """**The walkthrough end to end**, exactly as R064 §5 asks: the last command runs
    against a receipt the walkthrough itself produced, not against a fixture.

    Ratify → export the two files the Verify page shows → run the printed command → `0`.
    """
    from onedoor.guardrail import policy_loader
    from onedoor.guardrail.models import Bounds, Policy, Tier
    from onedoor.studio import server, verify

    state = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    try:
        policy_loader.upsert(
            state.enforcer,
            Policy(
                action_type="reports.read",
                tier=Tier.OBSERVE,
                dry_run=False,
                compensating_command="",
                bounds=Bounds(strict_params=False),
            ),
        )
        draft = server.new_draft(state, title="first policy set")
        server.save_draft(
            state,
            draft.draft_id,
            policies=[
                *draft.policies,
                Policy(
                    action_type="payments.transfer",
                    tier=Tier.CONFIRM,
                    dry_run=False,
                    compensating_command="payments.reverse",
                    bounds=Bounds(strict_params=False),
                ),
            ],
            effects=list(draft.effects),
        )
        outcome = server.ratify_draft(state, draft.draft_id, session="dogfooding")
        assert outcome.ratified, outcome.message
        digest = outcome.receipt.sealed()["ratification_digest"]
        dep = verify.deposition(state.enforcer, digest)
        assert dep is not None
    finally:
        state.close()

    (tmp_path / "receipt.json").write_text(dep.receipt_json, encoding="utf-8")
    (tmp_path / "snapshot.json").write_text(dep.snapshot_text, encoding="utf-8")

    command = next(c for c in _commands() if "studio.verify" in c)
    result = _run(command, tmp_path)
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "verified" in result.stdout


def test_the_verify_commands_other_two_outcomes_are_what_the_document_says(tmp_path) -> None:
    """The walkthrough documents exit 1 and exit 2. Both are executed, because a
    documented exit code nobody ran is a documented guess."""
    command = next(c for c in _commands() if "studio.verify" in c)
    (tmp_path / "receipt.json").write_text('{"ratification_digest": "x"}', encoding="utf-8")
    (tmp_path / "snapshot.json").write_text("{}", encoding="utf-8")
    assert _run(command, tmp_path).returncode == 1

    (tmp_path / "snapshot.json").unlink()
    assert _run(command, tmp_path).returncode == 2


def test_the_screens_the_walkthrough_names_are_the_tabs_that_exist() -> None:
    """A walkthrough naming a screen that is not there sends a person looking for it."""
    from onedoor.studio import shell

    text = WALKTHROUGH.read_text(encoding="utf-8")
    for tab in shell.TABS:
        assert f"**{tab.label}**" in text, f"the walkthrough never mentions {tab.label}"
