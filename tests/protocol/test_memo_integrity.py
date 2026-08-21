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
# Everything received from core/forensics, selected by PROVENANCE (location) and never
# by scanning content for the marker: the forensics session hit exactly that trap when
# a content scan matched their own index file quoting the convention. Our generated
# sidecar is excluded BY NAME, per Forward 001 -- "exclude your generated files
# explicitly". unverified/ is a subdirectory and glob is non-recursive, so quarantined
# memos never count toward the archive's guarantee.
GENERATED = {"INTEGRITY.md"}
MEMOS = sorted(p for p in ARCHIVE.glob("*.md") if p.name not in GENERATED)


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


def test_midline_quotation_of_the_marker_is_fine(tmp_path: Path) -> None:
    """Response 008 quotes its own footer format mid-line; that must still verify."""
    quoting = tmp_path / "quoting.md"
    quoting.write_bytes(_memo("# Memo\n\nEnds with `Integrity: sha256(body) = <hex>`.\n"))
    assert verify(quoting).status == "ok", "a mid-line marker is not a second footer"


def test_two_marker_lines_are_rejected_as_malformed(tmp_path: Path) -> None:
    """Response 010 superseded 009's final-line anchoring: ambiguity is an error.

    009 said anchor on the FINAL such line. The forensics session's independent
    verifier raised instead, and core ruled the stricter behaviour is the rule --
    two checkers returning different verdicts on one file is the E005 defect class
    reproduced inside the memo protocol. ACJ already rules duplicate keys malformed
    rather than last-one-wins; resolving the ambiguity silently was the move this
    programme forbids everywhere else.
    """
    duplicated = tmp_path / "two.md"
    good = _memo("# Memo\n\nA ruling.\n")
    duplicated.write_bytes(b"Integrity: sha256(body) = " + b"0" * 64 + b"\n" + good)
    result = verify(duplicated)
    assert result.status == "damaged"
    assert not result
    assert "exactly one is permitted" in result.detail


REPO = Path(__file__).resolve().parents[2]
_SKIP_DIRS = {".git", ".venv", "__pycache__", "dist", "node_modules", ".pytest_cache"}


def test_our_own_documents_satisfy_the_producer_obligation() -> None:
    """The producer obligation, checked on ourselves.

    Response 010: exactly one line of a memo may begin with `Integrity:`, and a
    verifier seeing more than one MUST reject the file. That binds producers, and
    this repository quotes the convention in a dozen places -- .gitattributes,
    CLAUDE.md, CONFORMANCE.md, BACKLOG.md, pyproject.toml, the checker, this file,
    the archive sidecar. All mid-line, which was luck rather than a property.

    The forensics session tripped exactly this on itself within hours of arguing for
    it: their Note_002 quoted Response 008's footer at line start inside a code
    fence, which would have made that file malformed the moment they adopted a footer
    of their own. It is what happens when you quote a protocol inside a document that
    speaks the protocol.

    The rule, not the exception: any file of ours carrying the marker at line start
    must be a *well-formed memo* -- exactly one marker, in the footer position, whose
    digest checks. `verify()` decides that, so the test states the obligation rather
    than a proxy for it. An earlier version asserted zero markers anywhere outside the
    archive, which was correct only while delivery sent no memos of its own; the
    0.3.6 release ping made it wrong. Delivery's outbound memos carry footers now, so
    the channel is verifiable in both directions.
    """
    offenders = []
    for path in REPO.rglob("*"):
        if not path.is_file() or _SKIP_DIRS & set(path.parts):
            continue
        if ARCHIVE in path.parents:  # received memos, verified by the tests above
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not any(line.startswith("Integrity:") for line in text.split("\n")):
            continue
        result = verify(path)
        if result.status != "ok":
            offenders.append(f"{path.relative_to(REPO)}: {result.status} ({result.detail})")
    assert not offenders, (
        "these files start a line with the integrity marker but are not well-formed "
        f"memos: {offenders}. Either indent the quotation / keep it mid-line, or give "
        f"the file a single correct footer."
    )
