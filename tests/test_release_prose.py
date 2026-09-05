"""The `0.7.0` release prose, held to the same fences the surfaces are (R070 §2.3).

The forbidden-phrase lists were built to guard rendered screens. Release notes are read by
more people than any screen, are quoted onward, and outlive the release — so a claim that
would fail on a page must fail here too. *The discipline you sell is the discipline your
own pages keep*, and a release note is a page.

Two things are checked, against the one document that ships (R094 §2): this file used to
hold two drafts apart while the T3 decision was still open — variant A assuming T3 shipped,
variant B assuming it slipped — and the fence that mattered most was keeping them honestly
partitioned. That decision is now made and recorded (T3 measured 0 of 11 and does not ship
in `0.7.0`), the drafts are retired, and `RELEASE_NOTES_v0.7.0.md` is the one sealed
document the fences below apply to, alongside the changelog section it was sliced from:

1. **Capability language.** Nothing may make the model the author or remove the person.
2. **Aspiration as capability.** Nothing may describe as shipped what has not shipped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from onedoor.studio import api, live_proposer

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "docs" / "release-0.7.0"
NOTES = DRAFTS / "RELEASE_NOTES_v0.7.0.md"
DRAFT_A = DRAFTS / "RELEASE_NOTES_v0.7.0-DRAFT-A-T3-ships.md"
DRAFT_B = DRAFTS / "RELEASE_NOTES_v0.7.0-DRAFT-B-T3-slips.md"
CHANGELOG = ROOT / "CHANGELOG.md"

DOCUMENTS = {"release notes": NOTES, "changelog": CHANGELOG}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _body_of(path: Path) -> str:
    """The document with its OWN seal removed — by POSITION, never by pattern (R071 §3.1).

    The distinction being enforced: **a digest a document computes about itself is its
    address; a digest a document repeats about another artifact is a transcription, and
    transcriptions go stale in silence.** Only the second is forbidden.

    The first version of this exemption dropped *every* line beginning `Integrity: `,
    anywhere in the file. That is pattern-based, and core was right that it had not been
    fixed but switched off: a draft quoting another memo's footer on its own line would
    have been exempted by the very fence meant to catch it.

    So the exemption is anchored to one position — the last non-empty line, and only when
    it is this document's own seal. Everything above it is body, and a 64-hex string in
    the body is a transcription no matter how it is introduced.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and re.fullmatch(r"Integrity: sha256\(body\) = [0-9a-f]{64}", lines[-1]):
        lines.pop()
    return "\n".join(lines)


def _folded(path: Path) -> str:
    """Whitespace-folded, so a phrase wrapped across two lines is still caught.

    A fence that missed `"AI writes\\nyour policies"` because of a line break would be a
    fence that any editor defeats by accident.
    """
    return " ".join(_text(path).split()).lower()


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_no_release_document_claims_the_model_writes_policy(name: str) -> None:
    """Wall 5's fence, applied to prose that will be quoted onward."""
    folded = _folded(DOCUMENTS[name])
    for forbidden in live_proposer.CAPABILITY_FORBIDDEN:
        assert forbidden not in folded, (
            f"{name} carries {forbidden!r}. Release prose is read by more people than any "
            "screen and outlives the release."
        )


#: Phrases that turn a plan into a claim. A release note is a statement about what IS.
ASPIRATIONAL = (
    "will soon",
    "coming soon",
    "in a future release we will",
    "is planned for this release",
    "ships with support for everything",
    "fully automatic",
    "no configuration required",
    "guarantees your policies are correct",
    "makes your agents safe",
)


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_no_release_document_presents_a_plan_as_a_capability(name: str) -> None:
    folded = _folded(DOCUMENTS[name])
    for phrase in ASPIRATIONAL:
        assert phrase not in folded, f"{name} presents a plan as a capability: {phrase!r}"


@pytest.mark.parametrize("name", sorted(DOCUMENTS))
def test_no_release_document_claims_the_studio_edits_live_rules(name: str) -> None:
    """The fence-post-one claim, in the words a reader would take away."""
    folded = _folded(DOCUMENTS[name])
    for claim in ("edit the live rules", "change the rules in force directly"):
        assert claim not in folded, f"{name} suggests the Studio edits live rules"


def test_the_published_notes_omit_t3_rather_than_promising_it() -> None:
    """The capability rule's sharpest edge, carried over from variant B: **absent, not
    announced.** T3 measured 0 of 11 (R094 §1) and does not ship, so the one document a
    reader takes as the record of what `0.7.0` IS does not mention the model track at
    all — a release note that promised a feature coming has made a claim it cannot keep,
    in the document people quote onward."""
    folded = _folded(NOTES)
    for word in ("propose", "instrument", "prompt digest", live_proposer.CAPABILITY):
        assert str(word).lower() not in folded, f"the notes mention {word!r}; T3 must be absent"


# --- the release, not-shipped, and cutover facts -----------------------------------------


def test_the_published_notes_exist_and_the_two_drafts_are_gone() -> None:
    """R094 §2.3: the notes are core-written, sealed, and committed as delivered; the
    two forks that existed while the T3 decision was open are retired in the same
    commit — a draft left beside the published notes would be indistinguishable from
    them to a reader who does not already know which is which."""
    assert NOTES.is_file()
    assert not DRAFT_A.exists(), "DRAFT-A must be deleted alongside the cutover"
    assert not DRAFT_B.exists(), "DRAFT-B must be deleted alongside the cutover"


def test_the_notes_say_which_draft_they_supersede() -> None:
    assert "supersedes draft B" in _text(NOTES)
    assert re.search(r"[0-9a-f]{64}", _text(NOTES).split("supersedes draft B")[1][:120]), (
        "the superseded draft's digest must be carried, not merely named"
    )


def test_the_changelog_t3_entry_says_it_did_not_ship() -> None:
    """T3's entry must read as what happened — a benchmark run and its result — never
    as a shipped feature with a conditional footnote. The condition is resolved now."""
    text = _text(CHANGELOG)
    t3 = text[text.index("### Not shipped in `0.7.0` — `ND-056` T3") :]
    t3 = t3[: t3.index("### Added — an operator script")]
    assert "0 of 11" in t3
    assert "0.7.1" in t3
    assert "### Added — `ND-056` T3" not in text, (
        "T3 must not also carry an `Added` heading — it did not ship"
    )


# --- the sentences that must appear verbatim, because a ruling fixed their wording -------


def test_the_legacy_route_sentence_is_the_ruled_form_in_every_document() -> None:
    """R066 §1 fixed this wording because an earlier form would have been FALSE.

    It is quoted rather than paraphrased in each document, and matched here against the
    constant the API itself serves — so the notes, the changelog and the running app
    cannot drift into three accounts of one route.
    """
    for name, path in DOCUMENTS.items():
        # Blockquote markers are stripped before folding: `> ` is markup, not a change to
        # the sentence. A check that failed on it would force the documents to carry the
        # quotation as one unreadable long line to satisfy a checker -- the same trap
        # `assert_reader_sees` exists to avoid, one document type over.
        unquoted = [
            line[2:] if line.startswith("> ") else line for line in _text(path).splitlines()
        ]
        folded = " ".join(" ".join(unquoted).split())
        assert " ".join(api.NO_APPROVAL_NOTE.split()) in folded, (
            f"{name} does not carry R066 §1's ruled sentence about the legacy route"
        )


def test_every_document_states_that_nothing_is_removed() -> None:
    """R070 §2.1: this release removes nothing, and the notes say so."""
    for name, path in DOCUMENTS.items():
        folded = _folded(path)
        assert "removes nothing" in folded, f"{name} does not say the release removes nothing"


def test_every_document_tells_the_version_number_story() -> None:
    """R070 §2.2: why 0.7.0 — the content defines the number."""
    for name, path in DOCUMENTS.items():
        folded = _folded(path)
        assert "content defines the number" in folded or "number describes content" in folded, (
            f"{name} does not explain why this is 0.7.0"
        )


def test_no_document_carries_crlf() -> None:
    for name, path in DOCUMENTS.items():
        assert b"\r" not in path.read_bytes(), f"{name} carries CRLF"


def test_the_notes_do_not_quote_a_test_count_they_cannot_hold() -> None:
    """Release prose must not transcribe numbers that a run owns (R010, X-11).

    A test count in either document would be stale the moment anything changed, and the
    release's real build-artifact digests are recorded at build time, before upload — a
    different discipline from the supersede citation checked below, which is a citation
    of a sealed, frozen prior document, not a number this run owns.
    """
    for name, path in DOCUMENTS.items():
        assert not re.search(r"\b\d{3,4} (?:tests? )?pass(?:ed|ing)\b", _body_of(path)), (
            f"{name} transcribes a test count"
        )


def test_the_notes_carry_exactly_one_integrity_footer() -> None:
    """The seal is generated, and there is exactly one — the protocol's producer rule."""
    footers = [line for line in _text(NOTES).splitlines() if line.startswith("Integrity: ")]
    assert len(footers) == 1, f"the notes have {len(footers)} integrity footers"
    assert re.fullmatch(r"Integrity: sha256\(body\) = [0-9a-f]{64}", footers[0])


def test_the_digest_exemption_is_anchored_to_position_and_not_to_pattern() -> None:
    """R071 §3.1's mechanism, proven in both directions on synthetic documents.

    A fence loosened until it stops complaining has been switched off. This proves the
    narrowing: the document's own final seal is exempt, and a digest anywhere else — even
    on a line that *looks* like a seal — is not.
    """
    digest = "a" * 64
    sealed = f"# notes\n\nsome prose\n\nIntegrity: sha256(body) = {digest}\n"
    quoting = f"# notes\n\nsee memo Integrity: sha256(body) = {digest}\n\nmore prose\n"
    in_prose = f"# notes\n\nthe wheel hashes to {digest}.\n\nIntegrity: sha256(body) = {digest}\n"

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:

        def _write(name: str, text: str) -> Path:
            p = Path(tmp) / name
            p.write_text(text, encoding="utf-8")
            return p

        # 1. The document's own seal is exempt: the body is clean.
        assert not re.search(r"\b[0-9a-f]{64}\b", _body_of(_write("sealed.md", sealed)))

        # 2. A quoted digest mid-document is NOT exempt, even introduced by the marker.
        #    This is the case the pattern-based version walked past.
        assert re.search(r"\b[0-9a-f]{64}\b", _body_of(_write("quoting.md", quoting))), (
            "a digest quoted mid-document survived the exemption; the fence is pattern-based again"
        )

        # 3. A digest in ordinary prose is caught even when the document is properly
        #    sealed — the seal exempts itself and nothing else.
        assert re.search(r"\b[0-9a-f]{64}\b", _body_of(_write("prose.md", in_prose)))
