"""A cited response number must never be reused for two different rulings, and
must name the memo it actually claims to.

**Learned the expensive way.** Core's F-B and Appendix B rulings arrived as *unnumbered
acknowledgments*. Delivery numbered them sequentially by assumption; the real `R055`
(`ND-055`) and `R056` (the seal ruling) then arrived and took those numbers. Two response
numbers each meant two different things — in the register whose whole value is that a
reader does not have to wonder.

**A number that names two rulings names neither.** The rule this enforces: *cite what the
source calls itself.* An unnumbered acknowledgment gets a date and a subject, never a
number invented to make it look like the ones around it.

This file used to audit `CONFORMANCE.md`'s own citations directly (no duplicate response
number, and a minimum count so an empty search space couldn't pass for the wrong reason).
That document has since moved out of this repository entirely, along with every other
document whose subject was the internal delivery-process itself: a public tree with zero
internal-process citations has nothing left in it for that specific audit to run against. The MATCHING LOGIC itself (a cited number and date must agree with the
memo's own filename) still matters wherever a citation like this could recur, so
`test_the_matcher_catches_a_real_mismatch` below keeps proving it against a synthetic
fixture built in this file: invented response numbers, invented dates, no real
correspondence content anywhere in it.
"""

from __future__ import annotations

import re
from pathlib import Path

CITATION = re.compile(r"### Resolved by Response (\d+) \(([\d-]{10})\)")


def archived_dates(paths: list[Path]) -> dict[str, str]:
    """Response number -> the date a `Core_to_Delivery_Response_NNN_DATE.md`-shaped
    filename carries. The exact matching logic this file's real check used to run
    against the archive; factored out so it can be proven against a fixture instead."""
    found = {}
    for path in paths:
        parts = path.stem.split("_")
        number, date = parts[-2], parts[-1]
        found[number] = date
    return found


def mismatched_citations(text: str, archived: dict[str, str]) -> list[str]:
    """Every citation in `text` whose date disagrees with (or is missing from)
    `archived`, described in plain words. Empty means every citation matches."""
    wrong = []
    for number, date in CITATION.findall(text):
        actual = archived.get(number)
        if actual != date:
            wrong.append(
                f"cited R{number} ({date}) but the archive holds "
                f"{'no memo ' + number if actual is None else 'R' + number + ' (' + actual + ')'}"
            )
    return wrong


def test_the_matcher_catches_a_real_mismatch(tmp_path: Path) -> None:
    """The mechanism this file used to check against the real archive, proven
    against an invented one instead: three fixture filenames, in `tmp_path`,
    naming no real correspondence, plus a small synthetic document quoting them.

    One citation matches, one names the wrong date for a memo that exists, one
    names a number the fixture archive doesn't have at all -- the same two ways
    a real citation could disagree with a real archive, both required to surface
    as named mismatches, and the matching one required not to.
    """
    for name in (
        "Core_to_Delivery_Response_101_2027-01-01.md",
        "Core_to_Delivery_Response_102_2027-01-02.md",
    ):
        (tmp_path / name).write_text("fixture only, not a real memo\n", encoding="utf-8")
    archived = archived_dates(sorted(tmp_path.glob("Core_to_Delivery_Response_*.md")))
    assert archived == {"101": "2027-01-01", "102": "2027-01-02"}

    fixture_doc = (
        "### Resolved by Response 101 (2027-01-01)\n"  # correct
        "one.\n\n"
        "### Resolved by Response 102 (2027-01-09)\n"  # wrong date
        "two.\n\n"
        "### Resolved by Response 103 (2027-01-03)\n"  # not in the fixture archive
        "three.\n"
    )
    wrong = mismatched_citations(fixture_doc, archived)
    assert len(wrong) == 2
    assert any("102" in w and "2027-01-09" in w for w in wrong)
    assert any("103" in w and "no memo" in w for w in wrong)
    assert not any("101" in w for w in wrong)
