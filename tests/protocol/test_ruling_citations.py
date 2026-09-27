"""A cited response number must never be reused for two different rulings.

**Learned the expensive way.** Core's F-B and Appendix B rulings arrived as *unnumbered
acknowledgments*. Delivery numbered them sequentially by assumption; the real `R055`
(`ND-055`) and `R056` (the seal ruling) then arrived and took those numbers. Two response
numbers each meant two different things — in the register whose whole value is that a
reader does not have to wonder.

**A number that names two rulings names neither.** The rule this enforces: *cite what the
source calls itself.* An unnumbered acknowledgment gets a date and a subject, never a
number invented to make it look like the ones around it. This file used to check every
citation's date against the archived memo's own filename too; that side of the check now
runs wherever the correspondence is actually kept, since it moved outside this repository.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CITATION = re.compile(r"### Resolved by Response (\d+) \(([\d-]{10})\)")

# The archive this used to check citations against (`docs/from_core/`) now lives
# outside this public repository, so the one check that needs both sides --
# does every cited number and date match the memo's own filename? -- runs
# wherever that correspondence is actually kept. What stays checkable here,
# from CONFORMANCE.md alone, is below.


def test_no_response_number_is_cited_twice() -> None:
    """The defect's own shape: one number, two meanings.

    A duplicate could in principle name a real, correctly-dated memo both times and
    still mean two different rulings -- the failure that actually happened -- so this
    holds regardless of whether the date-matching check above can run.
    """
    text = (ROOT / "CONFORMANCE.md").read_text(encoding="utf-8")
    numbers = [n for n, _ in CITATION.findall(text)]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert not duplicates, f"these response numbers head more than one section: {duplicates}"


def test_the_audit_has_something_to_audit() -> None:
    """A guard whose search space is empty passes for the wrong reason."""
    text = (ROOT / "CONFORMANCE.md").read_text(encoding="utf-8")
    assert len(CITATION.findall(text)) > 15
