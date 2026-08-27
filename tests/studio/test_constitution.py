"""The living constitution and its pinned origin (R054 §2).

**The archive is immutable; the constitution is alive; the origin and the in-force text
are different documents, and each says so on its face.** A constitution that could only be
amended by editing history would make every amendment a small forgery.

So the living text pins the origin by digest, and this recomputes it — descent is
*checkable*, not narrated.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
LIVING = DOCS / "studio-constitution.md"
ORIGIN = DOCS / "from_core" / "Policy_Studio_Design_Note_2026-08-22.md"

PINNED = re.compile(r"sha256\(Policy_Studio_Design_Note_2026-08-22\.md\) = ([0-9a-f]{64})")


def test_the_living_text_pins_its_origin_by_digest() -> None:
    match = PINNED.search(LIVING.read_text(encoding="utf-8"))
    assert match, "the living constitution does not pin its origin"
    assert match.group(1) == hashlib.sha256(ORIGIN.read_bytes()).hexdigest(), (
        "the pinned origin digest has drifted from the archived memo's bytes. Either the "
        "archive was edited -- which the immutability rule forbids -- or the pin was not "
        "regenerated. Look at which before changing either."
    )


def test_the_pin_is_labelled_an_observation_and_not_an_integrity_hash() -> None:
    """The memo has no footer, so calling this its integrity hash would invent a claim.

    R054 asked for "the memo's integrity hash". The design note carries none and is
    recorded ABSENT under R030 §2. Pinning a delivery-computed file digest satisfies the
    instruction's purpose; calling it something it is not would be the exact failure a
    provenance document exists to prevent.
    """
    text = LIVING.read_text(encoding="utf-8")
    assert "OBSERVATION, not the memo's integrity hash" in text
    assert "the memo has none" in text
    assert "INTEGRITY.md" in text, "the observation must point at where it is also recorded"


def _flat(text: str) -> str:
    """Content with line wrapping collapsed.

        A claim in a prose document is about its words, not about where the paragraph
        happened to wrap. The first version of the test below searched the raw text and
        failed because *"the memo is the
    origin"* is wrapped mid-phrase — a check outrunning
        what it meant to assert, which is a false alarm rather than a finding.
    """
    return " ".join(text.split()).lower()


def test_both_documents_state_which_one_they_are() -> None:
    """Each says so on its face — the standing law R054 §2 elevated it to."""
    text = _flat(LIVING.read_text(encoding="utf-8"))
    assert "the memo is the origin" in text
    assert "this document is what is in force" in text
    assert "living text" in text
    assert "change history" in text


def test_principle_five_carries_the_amended_wording() -> None:
    text = LIVING.read_text(encoding="utf-8")
    assert "Every derivation gets a record" in text
    assert "A record that promises re-derivation is a receipt" in text
    assert "R053" in text, "the amendment must cite the ruling that made it"


def test_the_archived_memo_still_says_receipt() -> None:
    """The origin is unedited. If this ever fails, history was rewritten.

    The old wording surviving in the archive is not an inconsistency to tidy — it is the
    evidence that the amendment was an amendment rather than a quiet substitution.
    """
    assert "The derivation gets a receipt." in ORIGIN.read_text(encoding="utf-8")
