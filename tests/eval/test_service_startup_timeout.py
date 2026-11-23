"""`eval.harness.service.start`'s own startup wait: a configurable readiness poll,
not a fixed 10s sleep, failing with how long it actually waited.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from eval.harness import service


def test_default_timeout_is_60_seconds_unless_the_env_var_overrides_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ONEDOOR_EVAL_SERVICE_STARTUP_TIMEOUT", raising=False)
    assert service._startup_timeout_seconds() == service.DEFAULT_STARTUP_TIMEOUT_SECONDS == 60.0

    monkeypatch.setenv("ONEDOOR_EVAL_SERVICE_STARTUP_TIMEOUT", "12.5")
    assert service._startup_timeout_seconds() == 12.5


def test_a_too_short_timeout_fails_with_the_bound_and_the_time_actually_waited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # CI run 45166369479: a near-zero bound against the REAL service raced real machine
    # speed, not just startup overhead -- on CI's Linux the service answered within the
    # 0.01s bound, so RuntimeError never fired. Relying on the service losing a timing
    # race is inherently machine-dependent; this instead makes the readiness check
    # itself never satisfiable, so the timeout must fire however fast the real service
    # (started for real, underneath) would otherwise answer.
    def _never_ready(self: httpx.Client, *args: object, **kwargs: object) -> httpx.Response:
        raise httpx.TransportError("planted: the health probe never succeeds in this test")

    monkeypatch.setattr(httpx.Client, "get", _never_ready)

    bound = 0.2
    db_path = str(tmp_path / "onedoor.db")
    with pytest.raises(RuntimeError) as excinfo:
        with service.start(db_path, startup_timeout_seconds=bound):
            pass  # pragma: no cover
    message = str(excinfo.value)
    assert "did not come up within 0.2s" in message
    assert "waited" in message
    # The waited figure must be a real elapsed measurement that actually reached the
    # bound -- never the literal bound padded out, and never some unrelated figure
    # either. Checked as a range, not an exact value, since real process startup
    # overhead (not just the poll interval) makes the precise figure machine- and
    # load-dependent -- but it can never be below the bound it was measured against,
    # and 30s of slack is far more than startup overhead alone ever needs.
    match = re.search(r"waited (\d+\.\d+)s", message)
    assert match, f"no parseable 'waited X.Xs' figure in: {message!r}"
    waited = float(match.group(1))
    assert bound <= waited < bound + 30.0, (
        f"waited {waited}s does not land in [{bound}, {bound + 30.0}) for bound {bound}s"
    )
