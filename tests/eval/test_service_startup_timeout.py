"""`eval.harness.service.start`'s own startup wait: a configurable readiness poll,
not a fixed 10s sleep, failing with how long it actually waited.
"""

from __future__ import annotations

import os
import re

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
    tmp_path,
) -> None:
    bound = 0.01
    db_path = str(tmp_path / "onedoor.db")
    with pytest.raises(RuntimeError) as excinfo:
        # a near-zero bound: real subprocess startup overhead alone guarantees it
        # elapses before the service can ever answer, regardless of machine speed.
        with service.start(db_path, startup_timeout_seconds=bound):
            pass  # pragma: no cover
    message = str(excinfo.value)
    assert "did not come up within 0.0s" in message
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
