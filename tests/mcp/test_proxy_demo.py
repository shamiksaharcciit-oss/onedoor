"""End-to-end smoke of the MCP proxy via the demo driver (subprocess, stdio)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def test_mcp_demo_end_to_end() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "scripts.demo_mcp"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    text = out.stdout
    assert "Weather in Amsterdam" in text  # permitted read forwarded
    assert "Thermostat set to 21.0" in text  # bounded actuation
    assert "above max 23.0" in text  # bounds denial at the proxy
    assert "requires approval" in text and "approval_id=1" in text  # tier 3 money
    assert "Sent €49.99 to webshop" in text  # approval released it
    assert "default_deny" in text  # unknown tool escalated
    assert "kill_switch" in text  # kill switch clamps reads' tier
