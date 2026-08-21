"""Core memos must still hash to the digest core stamped on them.

From Response 008 every core memo ends with `Integrity: sha256(body) = <hex>`. The
footer exists because relay damaged two memos in a row -- UTF-8 decoded as cp1252
with the C1 continuation bytes discarded -- and without it the only detection was
reading the mojibake and judging whether a sequence had "probably" been an arrow.

These memos are the authoritative record of every ruling delivery builds to, so the
check belongs in CI rather than in a habit: it catches a damaged memo on arrival,
and equally catches a well-meaning later edit to an archived one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_memo import verify

ARCHIVE = Path(__file__).resolve().parents[2] / "docs" / "from_core"
MEMOS = sorted(ARCHIVE.glob("Core_to_Delivery_Response_*.md"))


def test_archive_is_present() -> None:
    """A missing archive must fail loudly, not vacuously pass the check below."""
    assert MEMOS, f"no core memos found in {ARCHIVE}"


@pytest.mark.parametrize("memo", MEMOS, ids=lambda p: p.name.split("_")[4])
def test_memo_integrity_footer(memo: Path) -> None:
    result = verify(memo)
    if result is None:
        pytest.skip("predates the integrity-footer protocol (Response 008)")
    assert result, (
        f"{memo.name} does not match its claimed digest. Either it was damaged in "
        f"relay or it was edited after archiving. Do not 'fix' the footer -- get "
        f"core's original bytes."
    )
