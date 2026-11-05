from __future__ import annotations

import tempfile
from datetime import UTC, datetime

from eval.harness import permits

NOW = datetime(2026, 11, 5, 18, 0, 0, tzinfo=UTC)


def _fresh_run() -> permits.PermitRun:
    return permits.start(tempfile.mktemp(suffix=".db"), now=NOW)


def test_a_fresh_permit_verifies() -> None:
    verified, detail, decision_ref, bound_permit = permits.present(
        _fresh_run(), shape="fresh", now=NOW
    )
    assert verified, detail
    assert decision_ref is not None and decision_ref["format"] == "onedoor-decision-ref/1"
    assert bound_permit is not None


def test_reusing_an_already_consumed_permit_is_refused() -> None:
    run = _fresh_run()
    verified_first, _, _, _ = permits.present(run, shape="fresh", now=NOW)
    assert verified_first
    verified_second, detail, _, _ = permits.present(run, shape="reuse_prior", now=NOW)
    assert not verified_second
    assert "Content-Digest" in detail


def test_presenting_to_the_wrong_recipient_is_refused() -> None:
    verified, detail, _, _ = permits.present(_fresh_run(), shape="wrong_recipient", now=NOW)
    assert not verified
    assert "aud=" in detail


def test_an_expired_permit_is_refused() -> None:
    verified, detail, _, _ = permits.present(_fresh_run(), shape="expired", now=NOW)
    assert not verified
    assert "exp" in detail
