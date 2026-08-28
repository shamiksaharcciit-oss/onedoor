"""Every cited response number must name the memo that actually bears it.

**Learned the expensive way.** Core's F-B and Appendix B rulings arrived as *unnumbered
acknowledgments*. Delivery numbered them sequentially by assumption; the real `R055`
(`ND-055`) and `R056` (the seal ruling) then arrived and took those numbers. Two response
numbers each meant two different things — in the register whose whole value is that a
reader does not have to wonder.

**A number that names two rulings names neither.** The rule this enforces: *cite what the
source calls itself.* An unnumbered acknowledgment gets a date and a subject, never a
number invented to make it look like the ones around it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs" / "from_core"
CITATION = re.compile(r"### Resolved by Response (\d+) \(([\d-]{10})\)")


def _archived() -> dict[str, str]:
    """Response number -> the date the archived memo carries, from its filename."""
    found = {}
    for path in ARCHIVE.glob("Core_to_Delivery_Response_*.md"):
        number, date = path.stem.split("_")[-2:]
        found[number] = date
    return found


def test_every_cited_response_matches_an_archived_memo() -> None:
    """A citation is a claim about the archive; the archive decides."""
    archived = _archived()
    text = (ROOT / "CONFORMANCE.md").read_text(encoding="utf-8")
    wrong = []
    for number, date in CITATION.findall(text):
        actual = archived.get(number)
        if actual != date:
            wrong.append(
                f"cited R{number} ({date}) but the archive holds "
                f"{'no memo ' + number if actual is None else 'R' + number + ' (' + actual + ')'}"
            )
    assert not wrong, (
        "ruling citations disagree with the archive: "
        + "; ".join(wrong)
        + ". Cite what the source calls itself — an unnumbered acknowledgment gets a date "
        "and a subject, never an invented number."
    )


def test_no_response_number_is_cited_twice() -> None:
    """The defect's own shape: one number, two meanings.

    Distinct from the test above — a duplicate could in principle agree with the archive
    on date and still name two different rulings, and that is the failure that actually
    happened.
    """
    text = (ROOT / "CONFORMANCE.md").read_text(encoding="utf-8")
    numbers = [n for n, _ in CITATION.findall(text)]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert not duplicates, f"these response numbers head more than one section: {duplicates}"


def test_the_audit_has_something_to_audit() -> None:
    """A guard whose search space is empty passes for the wrong reason."""
    text = (ROOT / "CONFORMANCE.md").read_text(encoding="utf-8")
    assert len(CITATION.findall(text)) > 15
    assert len(_archived()) > 15
