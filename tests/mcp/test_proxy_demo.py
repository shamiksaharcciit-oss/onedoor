"""End-to-end smoke of the MCP proxy via the demo driver (subprocess, stdio)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def test_mcp_demo_end_to_end() -> None:
    # Both ends of the pipe state UTF-8 rather than inheriting a locale (R048: a green
    # gate is a claim about an environment). `text=True` alone decodes with the PARENT's
    # locale -- cp1252 on Windows -- while the child writes UTF-8 whenever
    # PYTHONIOENCODING says so. The only non-ASCII assertion below then failed on the
    # euro sign against a mojibake capture, and passed again once the variable was
    # unset: a test whose verdict depends on the caller's shell. CI never saw it because
    # CI runners are UTF-8, which is what "unbound" means -- the gate was making a claim
    # about an environment nobody had stated.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run(
        [sys.executable, "-m", "scripts.demo_mcp"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    text = out.stdout
    assert "Weather in Amsterdam" in text  # permitted read forwarded
    assert "Thermostat set to 21.0" in text  # bounded actuation
    # "23", not "23.0": bounds are Decimal from 0.4.0, so the denial reason no
    # longer carries a float artefact the policy author never wrote.
    assert "above max 23" in text  # bounds denial at the proxy
    assert "requires approval" in text and "approval_id=1" in text  # tier 3 money
    assert "Sent €49.99 to webshop" in text  # approval released it
    assert "default_deny" in text  # unknown tool escalated
    assert "kill_switch" in text  # kill switch clamps reads' tier
