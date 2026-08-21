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

import os
import re
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
_SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "onedoor.egg-info",
}


def _our_files() -> list[Path]:
    """Every file in the repository that is ours, pruning as we walk.

    `Path.rglob("*")` filtered afterwards traverses .venv in full -- 10,788 paths
    instead of 199, about six seconds per call and twice per run. Pruning the
    directory list in place is what makes a whole-repo assertion cheap enough to keep.
    """
    out: list[Path] = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        out.extend(Path(root) / f for f in files)
    return out


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
    for path in _our_files():
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


def test_the_digest_register_is_generated_not_transcribed() -> None:
    """R012: a digest in a ledger is generated, never transcribed.

    `docs/from_core/INTEGRITY.md` records every memo's body digest. Those cells are
    emitted by the verifier that computes them, and this asserts the committed block
    still matches what it emits -- which is the guard a hand-copied digest does not
    have. Core's own ledger drifted exactly this way: a whole-file hash, circulated as
    a transfer aid, was hand-copied into a cell meant for the protocol body digest and
    sat there green.

    Regenerate with:  python -m scripts.verify_memo --table docs/from_core/*.md
    """
    from scripts.verify_memo import BEGIN_MARK, END_MARK, render_block

    ledger = (ARCHIVE / "INTEGRITY.md").read_text(encoding="utf-8")
    start = ledger.find(BEGIN_MARK)
    end = ledger.find(END_MARK)
    assert start != -1 and end != -1, "the generated digest block is missing from INTEGRITY.md"

    committed = ledger[start : end + len(END_MARK)]
    expected = render_block(sorted(ARCHIVE.glob("*.md")))
    assert committed == expected, (
        "the digest register in INTEGRITY.md has drifted from what the verifier "
        "emits. Do not hand-edit it -- regenerate with "
        "`python -m scripts.verify_memo --table docs/from_core/*.md`."
    )


def test_no_whole_file_hash_is_recorded_beside_a_body_digest() -> None:
    """The two registers must never mix (R012).

    A body digest is a memo's recorded identity; a whole-file hash is an ephemeral
    transfer aid, used to prove a copy operation and then discarded. Mixing them is
    how core's ledger came to carry the wrong number, and the only defence is that
    delivery's ledgers record exactly one register. Any 64-hex string in our own
    ledger files that is not in the generated block is a transcribed digest.
    """
    from scripts.verify_memo import BEGIN_MARK, END_MARK

    hex64 = re.compile(r"\b[0-9a-f]{64}\b")
    offenders = []
    for name in ("INTEGRITY.md", "unverified/README.md"):
        path = ARCHIVE / name
        text = path.read_text(encoding="utf-8")
        start, end = text.find(BEGIN_MARK), text.find(END_MARK)
        outside = text[:start] + text[end:] if start != -1 and end != -1 else text
        offenders += [f"{name}: {m}" for m in hex64.findall(outside)]
    assert not offenders, (
        f"digests recorded outside the generated register: {offenders}. The register "
        f"is the only place a digest is written, and it is generated."
    )


def test_preimage_strips_ascii_whitespace_only_never_unicode(tmp_path: Path) -> None:
    """Forward 003 §1: the strip is byte-level ASCII, never text semantics.

    The preimage is defined over bytes, and the strip set is ` \t\n\r\f\v`.
    `str.rstrip()` consults the Unicode database and would eat U+00A0, so a body
    ending in a non-breaking space would digest differently across UCD versions --
    the same reasoning that removed Unicode normalisation from ACJ preimages (E14).
    Operating on bytes is what makes this true here, so it gets a test rather than a
    comment.
    """
    import hashlib

    text = "# Memo\n\nEnds with a non-breaking space:  "
    assert text.rstrip() != text, "the probe is pointless unless str.rstrip() would strip it"

    body = text.encode("utf-8").rstrip() + b"\n"
    assert b"\xc2\xa0" in body, "the NBSP must survive a byte-level strip"

    memo = tmp_path / "nbsp.md"
    digest = hashlib.sha256(body).hexdigest()
    memo.write_bytes(body + f"\nIntegrity: sha256(body) = {digest}\n".encode())
    assert verify(memo).status == "ok"


def test_the_footer_line_ends_the_file(tmp_path: Path) -> None:
    """Forward 003 §2: any byte after the footer's terminating LF is malformed.

    Binding, not advisory: a passing verification must attest every byte in the
    file, so the permissive reading would let unattested content ride under a green
    verdict. This checker used to do `raw[start:].rstrip(b"\r\n")`, which tolerated
    any number of trailing CR/LF bytes -- a divergence in the permissive direction,
    found by probing the clause rather than by re-reading the code, and escalated
    rather than quietly patched.
    """
    body = b"# Memo\n\nA ruling.\n"
    good = _memo("# Memo\n\nA ruling.\n")
    assert body in good
    ok = tmp_path / "ok.md"
    ok.write_bytes(good)
    assert verify(ok).status == "ok", "the canonical form must still verify"

    for label, trailing in [
        ("content", b"trailing junk\n"),
        ("one extra LF", b"\n"),
        ("a NUL", b"\x00"),
        ("a bare CR", b"\r"),
    ]:
        bad = tmp_path / f"bad_{label.replace(' ', '_')}.md"
        bad.write_bytes(good + trailing)
        result = verify(bad)
        assert result.status == "damaged", f"{label} after the footer must be malformed"
        assert "after the footer" in result.detail

    # At MOST one terminating LF: a missing final LF is TOLERATED (ratified on the
    # forensics channel, relayed in R014 section 3). Delivery's first pass required
    # the LF -- stricter than the rule, the opposite error to the permissive one it
    # had just fixed. Tightening is not automatically conforming.
    missing_lf = tmp_path / "no_lf.md"
    missing_lf.write_bytes(good.rstrip(b"\n"))
    assert verify(missing_lf).status == "ok", "a missing final LF is well-formed"

    # ...but only one. A second LF is a byte after the terminating one.
    two_lf = tmp_path / "two_lf.md"
    two_lf.write_bytes(good + b"\n")
    assert verify(two_lf).status == "damaged"


def test_no_gate_command_of_ours_spells_python3() -> None:
    """Forward 004: on Windows the Store `python3` alias exits 0 running nothing.

    A gate invoked by that name and checked on exit code alone reports success while
    executing nothing -- the gate-that-never-fired class in its sharpest form, because
    the check passes for the person running it and attests nothing. Verified live on
    this host: `python3 -c "print(...)"` prints "Python was not found" and exits 0.

    So no command WE publish or run may spell it. Excluded: `reference/` (core's
    vendored artifact, not ours to edit) and `docs/from_core/` (received memos).
    A `#!/usr/bin/env python3` shebang is fine and is not a gate invocation -- it is
    correct on POSIX and inert on Windows -- so only command-position uses count.
    """
    import re

    ours = [
        REPO / "README.md",
        REPO / "CONTRIBUTING.md",
        REPO / "CHANGELOG.md",
        REPO / ".github" / "workflows" / "ci.yml",
        *(REPO / "docs").glob("*.md"),
        *(REPO / "scripts").glob("*.py"),
    ]
    # command position: start of line or after a shell separator, not a shebang
    pattern = re.compile(r"(?<!env )\bpython3\b")
    offenders = []
    for path in ours:
        if not path.is_file():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if line.startswith("#!"):
                continue
            if pattern.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{n}: {line.strip()[:70]}")
    assert not offenders, (
        f"these spell `python3`, which exits 0 without running on a Windows host: "
        f"{offenders}. Use `python -m ...`, or sys.executable from inside Python."
    )
