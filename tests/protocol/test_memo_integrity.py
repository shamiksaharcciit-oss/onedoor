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
# Selected by PROVENANCE (filename), never by scanning content for the marker.
# The forensics session hit exactly that trap: a content scan matched their own
# index file quoting the convention. INTEGRITY.md quotes it here too.
MEMOS = sorted(ARCHIVE.glob("Core_to_*_Response_*.md"))


def test_archive_is_present() -> None:
    """A missing archive must fail loudly, not vacuously pass the check below."""
    assert MEMOS, f"no core memos found in {ARCHIVE}"


@pytest.mark.parametrize("memo", MEMOS, ids=lambda p: p.name.split("_")[4])
def test_memo_integrity_footer(memo: Path) -> None:
    result = verify(memo)
    if result.status == "no-footer":
        pytest.skip("predates the integrity-footer protocol (Response 008)")
    assert result, (
        f"{memo.name} does not match its claimed digest. Either it was damaged in "
        f"relay or it was edited after archiving. Do not 'fix' the footer -- get "
        f"core's original bytes. {result.detail}"
    )


def _memo(body: str) -> bytes:
    """A well-formed memo: body, blank separator, correct footer."""
    import hashlib

    preimage = body.rstrip().encode("utf-8") + b"\n"
    digest = hashlib.sha256(preimage).hexdigest()
    return preimage + f"\nIntegrity: sha256(body) = {digest}\n".encode()


def test_crlf_corruption_fails_and_is_not_mistaken_for_an_old_memo(tmp_path: Path) -> None:
    """The bug this test exists for: CRLF must FAIL, never silently skip.

    An earlier checker matched the footer with a regex requiring LF, so a
    CRLF-corrupted memo did not match, fell through to "no footer", and was reported
    as predating the protocol. That is a silent pass on precisely the corruption the
    footer exists to catch -- and it is how the .gitattributes gap would have gone
    unnoticed. Absence of a marker and a marker that does not verify are different
    facts and must never collapse into one.
    """
    good = tmp_path / "good.md"
    good.write_bytes(_memo("# Memo\n\nSome ruling.\n"))
    assert verify(good).status == "ok"

    crlf = tmp_path / "crlf.md"
    crlf.write_bytes(good.read_bytes().replace(b"\n", b"\r\n"))
    result = verify(crlf)
    assert result.status == "damaged", "CRLF corruption must fail, not skip"
    assert not result
    assert "core.autocrlf" in result.detail, "diagnosis must name the encoding cause"


def test_absent_footer_is_reported_as_absent_not_damaged(tmp_path: Path) -> None:
    """The other direction: a genuinely pre-protocol memo must not fail the suite."""
    old = tmp_path / "old.md"
    old.write_text("# Memo 001\n\nNo footer here.\n", encoding="utf-8", newline="\n")
    assert verify(old).status == "no-footer"


def test_footer_is_read_from_the_final_line_not_the_first_match(tmp_path: Path) -> None:
    """Response 008 quotes its own footer format; Response 009 amended the rule."""
    quoting = tmp_path / "quoting.md"
    quoting.write_bytes(
        _memo("# Memo\n\nEvery memo ends with `Integrity: sha256(body) = <hex>`.\n")
    )
    assert verify(quoting).status == "ok", "must anchor on the FINAL Integrity: line"
