"""CONFORMANCE.md's own claims, checked against the code they describe."""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECISION_PY = REPO_ROOT / "onedoor" / "guardrail" / "decision.py"
CONFORMANCE_MD = REPO_ROOT / "CONFORMANCE.md"
BOUND_PERMIT_NEXT_MD = REPO_ROOT / "docs" / "design" / "bound-permit-next.md"
TEST_CONFORMANCE_VECTORS_PY = REPO_ROOT / "tests" / "permit" / "test_conformance_vectors.py"

# A citation of the form `bound-permit-next.md, under "Heading Name"` -- the
# doc has no numbered sections, so this is the only way either file may
# point at a part of it. `re.DOTALL` so a citation wrapped across lines (as
# Markdown prose is) still matches.
_HEADING_CITATION = re.compile(r'bound-permit-next\.md.{0,40}?under "([^"]+)"', re.DOTALL)

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


def _bound_permit_next_headings() -> set[str]:
    headings = set()
    for line in BOUND_PERMIT_NEXT_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            headings.add(line.removeprefix("## ").strip())
    return headings


def _citations_in_markdown(path: Path) -> list[str]:
    return _HEADING_CITATION.findall(path.read_text(encoding="utf-8"))


def _citations_in_python(path: Path) -> list[str]:
    """Adjacent Python string literals (as `VECTOR_STATUS` uses to wrap a
    long value across lines) are joined into one `ast.Constant` by the
    parser itself, so walking the AST -- rather than regexing the raw
    source -- is what makes this immune to where the line breaks fall."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cited = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            cited.extend(_HEADING_CITATION.findall(node.value))
    return cited


def test_bound_permit_next_citations_name_a_heading_that_exists() -> None:
    """`docs/design/bound-permit-next.md` carries no numbered sections, so
    CONFORMANCE.md and test_conformance_vectors.py cite it by heading name --
    both files independently claimed different, invented section NUMBERS for
    the same two gaps until this was caught, so a heading name that drifts
    from a renamed or removed section is exactly the next way that mistake
    could recur silently."""
    headings = _bound_permit_next_headings()
    assert headings, (
        "the extractor found no '## ' heading -- it is broken, not the claim this test checks"
    )

    for source, extract in (
        (CONFORMANCE_MD, _citations_in_markdown),
        (TEST_CONFORMANCE_VECTORS_PY, _citations_in_python),
    ):
        cited = extract(source)
        assert cited, f"{source.name} cites bound-permit-next.md but names no heading"
        missing = [h for h in cited if h not in headings]
        assert not missing, (
            f"{source.name} cites heading(s) {missing} of bound-permit-next.md, "
            f"but its actual headings are {sorted(headings)}"
        )


def test_sabotage_a_renumbered_code_comment_is_caught() -> None:
    """Demonstrates what the test above actually guards against: renumber one
    step in the code (without touching the doc) and the comparison must
    fail."""
    code_labels = _code_step_labels()
    sabotaged = [*code_labels[:3], "99", *code_labels[4:]]  # drop step 4, insert a fake one
    doc_labels = _doc_step_labels()
    assert sabotaged != doc_labels, "the sabotage must actually diverge from the doc"
