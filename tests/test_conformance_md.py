"""CONFORMANCE.md's own claims, checked against the code they describe."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECISION_PY = REPO_ROOT / "onedoor" / "guardrail" / "decision.py"
CONFORMANCE_MD = REPO_ROOT / "CONFORMANCE.md"

_STEP_COMMENT = re.compile(r"^\s*# (\d+[a-z]?(?:/\d+)?)\.\s")
# Anchored to the START of a bullet line, not any backtick-quoted number in
# its prose: section 1 cross-references other steps from within a bullet
# (step 1's own text names step 7, for instance), and only the label the
# bullet actually introduces should count.
_STEP_LABEL_IN_DOC = re.compile(r"^- `(\d+[a-z]?(?:/\d+)?)`", re.MULTILINE)


def _code_step_labels() -> list[str]:
    """Every numbered step comment inside `_decide_and_reserve`, in the order
    the code itself runs them. Stops at the next top-level `def`, so a
    label-shaped comment anywhere else in the file is never picked up by
    accident."""
    labels = []
    in_function = False
    for line in DECISION_PY.read_text(encoding="utf-8").splitlines():
        if line.startswith("def _decide_and_reserve("):
            in_function = True
            continue
        if in_function and line.startswith("def "):
            break
        if in_function:
            match = _STEP_COMMENT.match(line)
            if match:
                labels.append(match.group(1))
    return labels


def _doc_step_labels() -> list[str]:
    """Every backtick-quoted step label in CONFORMANCE.md's section 1, in the
    order they appear."""
    text = CONFORMANCE_MD.read_text(encoding="utf-8")
    section = text.split("## 1.", 1)[1].split("\n## 2.", 1)[0]
    return _STEP_LABEL_IN_DOC.findall(section)


def test_conformance_md_section_1_matches_the_codes_own_step_order() -> None:
    code_labels = _code_step_labels()
    doc_labels = _doc_step_labels()
    assert code_labels, (
        "the extractor found no numbered step comment in _decide_and_reserve -- "
        "it is broken, not the claim this test checks"
    )
    assert doc_labels == code_labels, (
        f"CONFORMANCE.md section 1 lists {doc_labels}, but "
        f"_decide_and_reserve's own numbered step comments are {code_labels}, "
        f"in that order -- section 1 gained, lost or reordered a step"
    )


def test_sabotage_a_renumbered_code_comment_is_caught() -> None:
    """Demonstrates what the test above actually guards against: renumber one
    step in the code (without touching the doc) and the comparison must
    fail."""
    code_labels = _code_step_labels()
    sabotaged = [*code_labels[:3], "99", *code_labels[4:]]  # drop step 4, insert a fake one
    doc_labels = _doc_step_labels()
    assert sabotaged != doc_labels, "the sabotage must actually diverge from the doc"
