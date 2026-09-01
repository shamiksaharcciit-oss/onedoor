"""The `0.7.0` release prose, held to the same fences the surfaces are (R070 §2.3).

The forbidden-phrase lists were built to guard rendered screens. Release notes are read by
more people than any screen, are quoted onward, and outlive the release — so a claim that
would fail on a page must fail here too. *The discipline you sell is the discipline your
own pages keep*, and a release note is a page.

Three things are checked:

1. **Capability language.** Nothing may make the model the author or remove the person.
2. **Aspiration as capability.** Nothing may describe as shipped what has not shipped, and
   variant B may not promise T3 rather than omitting it.
3. **The two variants are honestly partitioned.** Every T3-dependent sentence in variant A
   is marked, and variant B contains none of them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from onedoor.studio import api, live_proposer

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "docs" / "release-0.7.0"
VARIANT_A = DRAFTS / "RELEASE_NOTES_v0.7.0-DRAFT-A-T3-ships.md"
VARIANT_B = DRAFTS / "RELEASE_NOTES_v0.7.0-DRAFT-B-T3-slips.md"
CHANGELOG = ROOT / "CHANGELOG.md"

DOCUMENTS = {"variant A": VARIANT_A, "variant B": VARIANT_B, "changelog": CHANGELOG}


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


# --- the two variants, honestly partitioned ---------------------------------------------


def test_both_variants_exist_and_say_which_they_are() -> None:
    assert VARIANT_A.is_file() and VARIANT_B.is_file()
    assert "DRAFT A: T3 SHIPS" in _text(VARIANT_A)
    assert "DRAFT B: T3 SLIPS" in _text(VARIANT_B)
    for path in (VARIANT_A, VARIANT_B):
        text = _text(path)
        assert "not published" in text and "delivery does not publish it" in text, (
            f"{path.name} must say on its face that it is a draft"
        )
        # R073 §2's naming law, pinned where it was broken. The header called the
        # management act "ratification", colliding with the ceremony the rest of the
        # document describes — in the first line, which R072 §1 ruled is where stating
        # happens. A vocabulary fix left unpinned is a vocabulary fix that comes back.
        head = text[: text.index("---")]
        assert "Shamik's scope approval" in head, (
            f"{path.name}'s header must name the management act as SCOPE APPROVAL"
        )
        assert "Shamik's ratification" not in head, (
            f"{path.name}'s header uses 'ratification' for the management act; that word "
            "is reserved for the ceremony in the product"
        )


def test_variant_a_marks_every_t3_dependent_sentence() -> None:
    """R070 §2: *mark every sentence that depends on the T3 decision.*

    Checked by deleting the marked material and asserting nothing about the model is left
    — a marking that missed a sentence would leave a T3 claim in a document whose header
    says there are none.
    """
    text = _text(VARIANT_A)
    assert "[T3]" in text, "variant A must mark its T3-dependent claims"

    # Everything from the T3 section heading to the next top-level rule is T3 material.
    start = text.index("### **[T3]** In plain words, if you bring a model")
    end = text.index("---\n\n## Two lists, and why they are two")
    remainder = (text[:start] + text[end:]).lower()

    for word in ("model", "propose", "instrument", "prompt"):
        assert word not in remainder, (
            f"{word!r} appears in variant A outside the marked T3 section, so a sentence "
            "whose truth depends on the T3 decision is unmarked"
        )


def test_variant_b_omits_t3_rather_than_promising_it() -> None:
    """The capability rule's sharpest edge: **absent, not announced.**

    A release note that says a feature is coming has made a claim it cannot keep, in the
    document people quote. So variant B does not mention the model track at all.
    """
    folded = _folded(VARIANT_B)
    assert "[t3]" not in folded
    for word in ("model", "propose", "instrument", "prompt digest", live_proposer.CAPABILITY):
        assert str(word).lower() not in folded, (
            f"variant B mentions {word!r}; it must omit T3 entirely rather than promise it"
        )
    # And it says WHY it omits, so a reviewer can tell omission from oversight.
    assert "aspiration presented as capability" in _text(VARIANT_B)


def test_the_variants_differ_only_where_t3_does() -> None:
    """Both must tell the same story about everything else.

    Otherwise the choice between them silently changes claims that have nothing to do with
    T3 — and whichever is published, the other's corrections are lost.
    """
    for anchor in (
        "Two lists, and why they are two",
        "Why the number is `0.7.0` and not `0.6.3`",
        "This release removes nothing",
        "The v1 API adds no approval route",
        "The rest of the room",
        "What has not changed, and what this does not claim",
    ):
        assert anchor in _text(VARIANT_A), f"variant A lost {anchor!r}"
        assert anchor in _text(VARIANT_B), f"variant B lost {anchor!r}"


def test_variant_b_counts_the_authoring_paths_it_actually_describes() -> None:
    """A count in prose is a claim. Two paths ship in B, and B must say two."""
    text = _text(VARIANT_B)
    assert "## Writing a policy, two ways" in text
    assert "three ways to write a policy" not in text
    assert "plus two new authoring paths" in text


def test_variant_a_counts_three() -> None:
    text = _text(VARIANT_A)
    assert "## Writing a policy, three ways" in text
    assert "plus three new authoring paths" in text


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


def test_the_drafts_are_marked_as_drafts_and_live_outside_the_published_path() -> None:
    """They must not be mistaken for the published notes on release day."""
    assert DRAFTS.is_dir()
    assert not (ROOT / "RELEASE_NOTES_v0.7.0.md").exists(), (
        "a file at the published path would be indistinguishable from ratified notes"
    )
    for path in (VARIANT_A, VARIANT_B):
        assert "DRAFT" in path.name


def test_the_changelog_draft_section_is_marked_as_one() -> None:
    text = _text(CHANGELOG)
    unreleased = text[text.index("## Unreleased") : text.index("## 0.6.2")]
    assert "DRAFT for `0.7.0`" in unreleased
    assert "gated on the operator dogfooding pass" in unreleased
    for track in ("`ND-056` T1", "`ND-056` T2", "`ND-056` T3"):
        assert track in unreleased, f"the changelog draft does not cover {track}"


def test_the_changelog_marks_t3_as_conditional() -> None:
    """T3's entry must not read as shipped while its gate is open."""
    text = _text(CHANGELOG)
    t3 = text[text.index("### Added — `ND-056` T3") :]
    t3 = t3[: t3.index("### Added — an operator script")]
    assert "only if its published-misses benchmark clears" in t3
    assert "otherwise it follows as" in t3


def test_no_document_carries_crlf() -> None:
    for name, path in DOCUMENTS.items():
        assert b"\r" not in path.read_bytes(), f"{name} carries CRLF"


def test_the_drafts_do_not_quote_a_test_count_or_a_digest_they_cannot_hold() -> None:
    """Release prose must not transcribe numbers that a run owns (R010, X-11).

    A test count or an artifact digest in a draft would be stale the moment anything
    changed, and the release's real digests are recorded at build time, before upload.
    """
    for name, path in DOCUMENTS.items():
        assert not re.search(r"\b\d{3,4} (?:tests? )?pass(?:ed|ing)\b", _body_of(path)), (
            f"{name} transcribes a test count"
        )
        assert not re.search(r"\b[0-9a-f]{64}\b", _body_of(path)), f"{name} transcribes a digest"


def test_each_sealed_draft_carries_exactly_one_integrity_footer() -> None:
    """The seal is generated, and there is exactly one — the protocol's producer rule."""
    for path in (VARIANT_A, VARIANT_B):
        footers = [line for line in _text(path).splitlines() if line.startswith("Integrity: ")]
        assert len(footers) == 1, f"{path.name} has {len(footers)} integrity footers"
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
