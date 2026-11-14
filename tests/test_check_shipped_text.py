"""scripts.check_shipped_text: the detector itself, and every named allowance.

One planted hit per category (ruling id, brief id, round name, role noun,
person name), each proven caught in BOTH a shipped-style path (something
under `onedoor/`) and an unshipped-style path (something under `tests/`) --
the detector's job is to find the pattern regardless of where it lives;
`ships()` is a separate, later decision about which hits are a hard
failure. Each named allowance gets its own test showing the thing it is
meant to let through still lets through, and that the allowance is no
wider than its own stated reason.
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from scripts.check_shipped_text import (
    scan_text,
    scan_tree,
    ships,
    ships_path,
)

ROOT = Path(__file__).resolve().parent.parent
SHIPPED_PATH = "onedoor/fake_module.py"
UNSHIPPED_PATH = "tests/fake_test.py"


def _categories(path: str, text: str) -> list[str]:
    return [h.category for h in scan_text(text, path=path)]


def _join(*parts: str) -> str:
    """Builds a planted string at runtime from inert fragments, so the
    assembled hit-shaped text exists only as an in-memory value during the
    test run -- never as a contiguous substring in this file's own
    source. This file ships (`tests/test_*.py` reaches the sdist), so a
    literal plant here would itself be exactly the kind of hit this
    module exists to catch."""
    return "".join(parts)


RULING_CITATION = _join("rul", "ing", " ", "30", "lv")
BARE_BRIEF_ID = _join("30", "lv")
ROUND_NAME = _join("ro", "und", " ", "7", "a")
FINDING_CITATION = _join("find", "ing", " ", "2")
VERDICT_LABEL = _join("FI", "X", " ", "3")
NUMBERED_QUESTION = _join("quest", "ions", ".md #", "32")
ROLE_NOUN = _join("old", " ", "stand", "ards")
PERSON_GIVEN_NAME = _join("Sha", "mik")
PERSON_FULL_NAME = _join("Sha", "mik", " Sa", "ha")

# --- The six widened shapes, each proven caught in three places -------------
#
# "A shipped module under onedoor/" is SHIPPED_PATH; "a top-level test file"
# is UNSHIPPED_PATH's own sibling shape (tests/test_fake.py -- the glob
# that actually ships per _SDIST_TOP_LEVEL_TEST_RE, distinct from
# UNSHIPPED_PATH's tests/fake_test.py, which does not); "inside a real
# built sdist" is simulated with the exact member-prefix form
# scan_sdist() itself produces ("<archive>!<member>") rather than
# rebuilding a real sdist per shape, which the detector's own logic
# (scan_text) treats identically either way -- `test_the_ships_
# classifier_agrees_with_a_real_built_sdist` already covers the one
# thing that genuinely requires a real build (the sdist's own file
# membership), not the pattern matching itself.

SHIPPED_TEST_PATH = "tests/test_fake.py"
SDIST_MEMBER_PATH = "onedoor-0.10.2.tar.gz!onedoor/fake_module.py"

ROUND_NAME_TRAILING_DIGIT = _join("ro", "und", " ", "7", "a", "2")
ROUND_RANGE = _join("ro", "unds", " ", "6", " to ", "8")
ALL_CAPS_BRIEF_ID = _join("30", "L", "V")
CORE_ALONE = _join("c", "ore")
PERSON_SURNAME = _join("Sa", "ha")
PERSON_HANDLE = _join("shamiksaharcciit", "-oss")
DECISION_RECORD_CITATION = _join("rul", "ing", " ", "R", "039")


@pytest.mark.parametrize(
    "path", [SHIPPED_PATH, SHIPPED_TEST_PATH, SDIST_MEMBER_PATH], ids=["module", "test", "sdist"]
)
def test_a_round_name_with_a_trailing_digit_is_caught(path: str) -> None:
    assert "round_name" in _categories(path, f"fixed in {ROUND_NAME_TRAILING_DIGIT} already")


@pytest.mark.parametrize(
    "path", [SHIPPED_PATH, SHIPPED_TEST_PATH, SDIST_MEMBER_PATH], ids=["module", "test", "sdist"]
)
def test_a_plural_round_range_is_caught(path: str) -> None:
    assert "round_name" in _categories(path, f"fixed across {ROUND_RANGE}")


@pytest.mark.parametrize(
    "path", [SHIPPED_PATH, SHIPPED_TEST_PATH, SDIST_MEMBER_PATH], ids=["module", "test", "sdist"]
)
def test_an_all_caps_brief_id_is_caught(path: str) -> None:
    assert "brief_id" in _categories(path, f"the seventh of {ALL_CAPS_BRIEF_ID}'s own list")


@pytest.mark.parametrize(
    "path", [SHIPPED_PATH, SHIPPED_TEST_PATH, SDIST_MEMBER_PATH], ids=["module", "test", "sdist"]
)
def test_the_role_noun_standing_alone_is_caught(path: str) -> None:
    assert "role_noun" in _categories(path, f"escalated to {CORE_ALONE} for review")


def test_the_role_noun_standing_alone_does_not_fire_on_ordinary_compounds() -> None:
    """The standalone-role-noun pattern's own named allowance (built into
    the pattern, not a separate allowance function): a compound technical
    term either side of the word is not this engine's own role noun."""
    assert "role_noun" not in _categories(SHIPPED_PATH, "a multicore scheduler")
    assert "role_noun" not in _categories(SHIPPED_PATH, "mandate_core_digest")
    assert "role_noun" not in _categories(SHIPPED_PATH, "git's own core.longpaths setting")
    assert "role_noun" not in _categories(SHIPPED_PATH, "from llama_index.core import X")


_CONSTITUTION_PATH = "docs/studio-constitution.md"


def test_the_real_constitution_file_carries_no_role_noun_today() -> None:
    """Regression guard: this file used to need a by-exact-line-text
    allowance for four lines that named the reviewing party; those lines
    are reworded now, the allowance is gone, and this file is scanned the
    same way as any other -- zero role_noun hits, with no special case."""
    real_text = (ROOT / "docs" / "studio-constitution.md").read_text(encoding="utf-8")
    hits = [h for h in scan_text(real_text, path=_CONSTITUTION_PATH) if h.category == "role_noun"]
    assert hits == []


def test_a_role_noun_added_to_the_constitution_is_still_caught() -> None:
    """No allowance protects this file anymore -- a mention anywhere in it
    is an ordinary hit, the same as in any other file."""
    real_text = (ROOT / "docs" / "studio-constitution.md").read_text(encoding="utf-8")
    lines = real_text.split("\n")
    lines.insert(0, f"a line that mentions {CORE_ALONE} by itself")
    assert "role_noun" in _categories(_CONSTITUTION_PATH, "\n".join(lines))


@pytest.mark.parametrize(
    "path", [SHIPPED_PATH, SHIPPED_TEST_PATH, SDIST_MEMBER_PATH], ids=["module", "test", "sdist"]
)
def test_the_authors_surname_is_caught(path: str) -> None:
    assert "person_name" in _categories(path, f"escalated to {PERSON_SURNAME} directly")


@pytest.mark.parametrize(
    "path", [SHIPPED_PATH, SHIPPED_TEST_PATH, SDIST_MEMBER_PATH], ids=["module", "test", "sdist"]
)
def test_the_account_handle_is_caught(path: str) -> None:
    assert "person_name" in _categories(path, f"filed by {PERSON_HANDLE} directly")


@pytest.mark.parametrize(
    "path", [SHIPPED_PATH, SHIPPED_TEST_PATH, SDIST_MEMBER_PATH], ids=["module", "test", "sdist"]
)
def test_a_decision_record_id_in_a_ruling_citation_context_is_caught(path: str) -> None:
    assert "ruling_id" in _categories(path, f"see {DECISION_RECORD_CITATION} for why")


def test_a_bare_decision_record_id_is_not_itself_a_citation() -> None:
    """A narrowing on the ruling-id check: an ND- requirement id or the older numeric
    scheme's own id, cited BARE (no "ruling" immediately in front), is
    this program's own legitimate normative-citation vocabulary, not a
    hit -- only the word "ruling" directly in front of one turns it into
    a citation of THIS round-based protocol instead."""
    bare_decision_record_id = _join("ND", "-0", "52")
    bare_older_scheme_id = _join("R", "0", "39")
    assert "ruling_id" not in _categories(
        SHIPPED_PATH, f"covered by {bare_decision_record_id}, see invariant 10"
    )
    assert "ruling_id" not in _categories(
        SHIPPED_PATH, f"{bare_older_scheme_id} is the seal ruling"
    )


# --- one planted hit per category, in both a shipped and an unshipped path ----


def test_a_ruling_id_citation_is_caught_in_a_shipped_file() -> None:
    assert "ruling_id" in _categories(SHIPPED_PATH, f"see {RULING_CITATION} for why")


def test_a_ruling_id_citation_is_caught_in_an_unshipped_file() -> None:
    assert "ruling_id" in _categories(UNSHIPPED_PATH, f"see {RULING_CITATION} for why")


def test_a_bare_brief_id_is_caught_in_a_shipped_file() -> None:
    assert "brief_id" in _categories(SHIPPED_PATH, f"the seventh of {BARE_BRIEF_ID}'s own list")


def test_a_bare_brief_id_is_caught_in_an_unshipped_file() -> None:
    assert "brief_id" in _categories(UNSHIPPED_PATH, f"the seventh of {BARE_BRIEF_ID}'s own list")


def test_a_round_name_is_caught_in_a_shipped_file() -> None:
    assert "round_name" in _categories(SHIPPED_PATH, f"fixed in {ROUND_NAME} already")


def test_a_round_name_is_caught_in_an_unshipped_file() -> None:
    assert "round_name" in _categories(UNSHIPPED_PATH, f"fixed in {ROUND_NAME} already")


def test_a_finding_citation_is_caught_in_a_shipped_file() -> None:
    assert "finding_citation" in _categories(SHIPPED_PATH, f"read back ({FINDING_CITATION})")


def test_a_finding_citation_is_caught_in_an_unshipped_file() -> None:
    assert "finding_citation" in _categories(UNSHIPPED_PATH, f"read back ({FINDING_CITATION})")


def test_a_verdict_label_is_caught_in_a_shipped_file() -> None:
    assert "verdict_label" in _categories(SHIPPED_PATH, f"{VERDICT_LABEL}: refused here")


def test_a_verdict_label_is_caught_in_an_unshipped_file() -> None:
    assert "verdict_label" in _categories(UNSHIPPED_PATH, f"{VERDICT_LABEL}: refused here")


def test_a_numbered_question_is_caught_in_a_shipped_file() -> None:
    assert "numbered_question" in _categories(SHIPPED_PATH, f"the same fix ({NUMBERED_QUESTION})")


def test_a_numbered_question_is_caught_in_an_unshipped_file() -> None:
    assert "numbered_question" in _categories(UNSHIPPED_PATH, f"the same fix ({NUMBERED_QUESTION})")


BARE_QUESTION_NUMBER = _join("quest", "ion", " ", "12")


def test_the_bare_question_word_followed_by_a_number_is_caught() -> None:
    """The same pointer in its plainest spelling: no file, no anchor, just
    the everyday word directly in front of a number."""
    assert "numbered_question" in _categories(SHIPPED_PATH, f"see {BARE_QUESTION_NUMBER} for why")
    assert "numbered_question" in _categories(UNSHIPPED_PATH, f"see {BARE_QUESTION_NUMBER} for why")


def test_a_role_noun_is_caught_in_a_shipped_file() -> None:
    assert "role_noun" in _categories(SHIPPED_PATH, f"{ROLE_NOUN} flagged this one")


def test_a_role_noun_is_caught_in_an_unshipped_file() -> None:
    assert "role_noun" in _categories(UNSHIPPED_PATH, f"{ROLE_NOUN} flagged this one")


def test_a_person_name_is_caught_in_a_shipped_file() -> None:
    assert "person_name" in _categories(SHIPPED_PATH, f"escalated to {PERSON_GIVEN_NAME} directly")


def test_a_person_name_is_caught_in_an_unshipped_file() -> None:
    assert "person_name" in _categories(
        UNSHIPPED_PATH, f"escalated to {PERSON_GIVEN_NAME} directly"
    )


BARE_COMMIT_ID = _join("78", "cf", "632")


def test_a_bare_commit_id_is_caught_in_a_shipped_file() -> None:
    assert "commit_id" in _categories(SHIPPED_PATH, f"fixed in {BARE_COMMIT_ID} already")


def test_a_bare_commit_id_is_caught_in_an_unshipped_file() -> None:
    assert "commit_id" in _categories(UNSHIPPED_PATH, f"fixed in {BARE_COMMIT_ID} already")


def test_a_pure_decimal_number_is_not_mistaken_for_a_commit_id() -> None:
    """A commit id's own alphabet is hex, not decimal -- a run of only
    `0-9` (a date, a count, an amount, an IP's integer form) is never one,
    however many digits long."""
    assert "commit_id" not in _categories(SHIPPED_PATH, "measured on 20260827 at 2130706433")


def test_the_signing_algorithms_name_is_not_a_commit_id() -> None:
    assert "commit_id" not in _categories(SHIPPED_PATH, "signed with Ed25519")
    assert "commit_id" not in _categories(SHIPPED_PATH, "an ed25519 key")


def test_the_hex_alphabet_literal_is_not_a_commit_id() -> None:
    assert "commit_id" not in _categories(SHIPPED_PATH, 'all(c in b"0123456789abcdef" for c in x)')


def test_a_digest_named_by_its_own_algorithm_is_not_a_commit_id() -> None:
    """A pinned dependency hash or checksum names its own algorithm
    immediately before the hex run -- that is what legitimately explains a
    bare hex string without it being a citation of this repository's own
    history."""
    assert "commit_id" not in _categories(SHIPPED_PATH, f"sha256:{BARE_COMMIT_ID}1234567")
    assert "commit_id" not in _categories(SHIPPED_PATH, f"--hash=sha256:{BARE_COMMIT_ID}1234567")


def test_a_truncated_digest_preview_is_not_a_commit_id() -> None:
    """Marked as partial by its own trailing ellipsis -- the shape a
    genuine commit-id citation never has, since an abbreviated git sha is
    always used complete."""
    assert "commit_id" not in _categories(SHIPPED_PATH, f"digest {BARE_COMMIT_ID}…b945")
    assert "commit_id" not in _categories(SHIPPED_PATH, f"digest {BARE_COMMIT_ID}...b945")


def test_a_real_commit_id_next_to_a_truncation_mark_is_still_caught_without_one() -> None:
    """The ellipsis allowance is scoped to the match's own trailing
    characters, not the sentence -- a real id with no ellipsis right after
    it must still be caught even in a sentence that also discusses a
    truncated digest elsewhere."""
    assert "commit_id" in _categories(
        SHIPPED_PATH, f"fixed in {BARE_COMMIT_ID}, see digest abc1234…b945 above"
    )


def test_a_real_published_commit_is_allowed_only_in_its_own_named_file() -> None:
    """A commit id allowed because it is real and PUBLIC (reachable from
    the public release this round started from) is scoped to the exact
    file that legitimately cites it, not to the id in the abstract --
    the identical id is still caught anywhere else."""
    published = _join("a49", "ecd7", "7af01")
    text = f"onedoor 0.10.2 ({published})."
    assert "commit_id" not in _categories("eval/RESULTS.md", text)
    assert "commit_id" in _categories(SHIPPED_PATH, text)


# --- a ruling citation is not double-counted as a bare brief id too -----------


def test_the_brief_id_inside_a_ruling_citation_is_not_double_counted() -> None:
    hits = scan_text(f"see {RULING_CITATION} for why", path=SHIPPED_PATH)
    assert sum(1 for h in hits if h.category == "brief_id") == 0
    assert sum(1 for h in hits if h.category == "ruling_id") == 1


# --- named allowances: each lets through exactly what it says it does --------


def test_an_ordinal_number_is_not_mistaken_for_a_brief_id() -> None:
    assert "brief_id" not in _categories(SHIPPED_PATH, "fixed on its 21st attempt")


def test_a_brief_id_shaped_like_an_invalid_ordinal_is_still_caught() -> None:
    """The ordinal allowance checks the NUMBER, not just the suffix
    letters -- a brief id ending in the "second" digraph is not a real
    ordinal unless its own number actually ends 2 (so "30" with that
    digraph is not one; "32" would be), which the un-narrowed
    suffix-only check swallowed by accident. The 11/12/13 numbers are
    the same trap the other direction: they always take the "th" digraph,
    never the one their last digit would otherwise suggest."""
    fake_ordinals = [
        _join("30", "n", "d"),
        _join("11", "s", "t"),
        _join("12", "n", "d"),
        _join("13", "r", "d"),
        _join("22", "t", "h"),
    ]
    for fake_ordinal in fake_ordinals:
        assert "brief_id" in _categories(SHIPPED_PATH, f"see {fake_ordinal} for why"), fake_ordinal


def test_a_css_length_is_allowed_only_in_its_own_exact_known_file() -> None:
    """The CSS-length allowance is an exact (path, matched text)
    pair, not a shape -- a real, known CSS value in a real known file is
    allowed there, but the identical string is still caught as a brief id
    anywhere else, including another shipped file."""
    css_value = _join("24", "e", "m")
    assert "brief_id" not in _categories("onedoor/studio/shell.py", f"padding: {css_value};")
    assert "brief_id" in _categories(SHIPPED_PATH, f"padding: {css_value};")


def test_a_real_brief_id_is_still_caught_next_to_an_ordinal_number() -> None:
    """The ordinal allowance is scoped to the matched text's own suffix, not
    to the surrounding sentence -- a real id beside an ordinal must still be
    caught."""
    assert "brief_id" in _categories(SHIPPED_PATH, f"the 21st fix landed in {BARE_BRIEF_ID}")


def test_the_packages_own_author_field_is_allowed_in_pyproject_toml() -> None:
    assert "person_name" not in _categories(
        "pyproject.toml", f'authors = [{{ name = "{PERSON_FULL_NAME}" }}]'
    )


def test_the_packages_own_author_field_is_allowed_in_metadata() -> None:
    assert "person_name" not in _categories(
        "onedoor-0.10.2.dist-info/METADATA", f"Author: {PERSON_FULL_NAME}"
    )


def test_the_author_field_allowance_survives_the_sdist_member_prefix() -> None:
    """`scan_sdist`/`scan_wheel` report a hit's path as `archive!member`
    (e.g. `onedoor-0.10.2.tar.gz!pyproject.toml`), never a bare tracked-file
    path -- the allowance must still recognise `pyproject.toml` underneath
    that prefix, or the package's own author line false-positives the
    moment it is scanned inside a real built sdist rather than the tree."""
    assert "person_name" not in _categories(
        "onedoor-0.10.2.tar.gz!pyproject.toml", f'authors = [{{ name = "{PERSON_FULL_NAME}" }}]'
    )
    assert "person_name" not in _categories(
        "onedoor-0.10.2-py3-none-any.whl!onedoor-0.10.2.dist-info/METADATA",
        f"Author: {PERSON_FULL_NAME}",
    )


def test_changelogs_historical_credit_is_allowed_but_only_in_changelog() -> None:
    assert "person_name" not in _categories("CHANGELOG.md", f"bug reported by {PERSON_GIVEN_NAME}")


def test_the_changelog_allowance_does_not_spread_to_other_shipped_files() -> None:
    """The narrow reason for the CHANGELOG.md allowance (pre-existing historical
    release credit in a file that genuinely ships) must not leak into any other
    shipped path just because it also happens to mention the same name."""
    assert "person_name" in _categories(
        "onedoor/other_module.py", f"bug reported by {PERSON_GIVEN_NAME}"
    )
    assert "person_name" in _categories("README.md", f"bug reported by {PERSON_GIVEN_NAME}")


def test_the_surname_is_allowed_inside_the_drafts_own_name() -> None:
    """A context allowance found empirically (beyond the
    four named contexts already allowed): the surname is part of
    `draft-saha-aadp`, the AADP Internet-Draft's formal, author-named
    identifier (`CONFORMANCE.md`, `onedoor/guardrail/models.py`, and
    anywhere else the draft is cited by its own name) -- not a citation
    of this round-based protocol."""
    surname = PERSON_FULL_NAME.split()[-1]
    assert "person_name" not in _categories(
        "onedoor/other_module.py", f"per draft-{surname.lower()}-aadp-03 section 3"
    )


def test_the_surname_allowance_does_not_spread_outside_the_drafts_name() -> None:
    surname = PERSON_FULL_NAME.split()[-1]
    assert "person_name" in _categories("onedoor/other_module.py", f"reviewed by {surname}")


def test_the_handle_is_allowed_inside_a_real_project_url() -> None:
    """The handle is part of a real `github.com/<handle>/...` project URL
    (`README.md`'s own badges and links, `onedoor/studio/store.py`'s own
    doc comment) -- not a citation either."""
    handle = PERSON_HANDLE
    assert "person_name" not in _categories(
        "onedoor/other_module.py", f"see https://github.com/{handle}/onedoor/issues"
    )


def test_the_handle_allowance_does_not_spread_outside_the_url() -> None:
    handle = PERSON_HANDLE
    assert "person_name" in _categories("onedoor/other_module.py", f"filed by {handle} directly")


def test_a_brief_id_shape_inside_a_real_uuid_is_not_a_citation() -> None:
    """A random UUID's hex digits can spell the brief id's own shape by pure
    chance (found in a real fixture's `request_id`); it stands for nothing,
    so there is no citation to reword. The UUID itself is not hit-shaped
    text for any OTHER category, so it needs no runtime building."""
    uuid_text = "request_id: f2825750-4b3a-4212-98ab-edf4cfa17f25"
    assert "brief_id" not in _categories(UNSHIPPED_PATH, uuid_text)


def test_a_real_brief_id_next_to_a_uuid_is_still_caught() -> None:
    """The UUID allowance is scoped to a match fully INSIDE a real UUID's
    own span -- a genuine id merely sitting near one must still be caught."""
    text = f"see {BARE_BRIEF_ID}, logged against f2825750-4b3a-4212-98ab-edf4cfa17f25"
    assert "brief_id" in _categories(UNSHIPPED_PATH, text)


# --- ships()/ships_path(): the classifier the detector's hits are filtered by -


def test_anything_under_the_onedoor_package_ships() -> None:
    assert ships("onedoor/guardrail/approvals.py") is True


def test_the_named_sdist_root_files_ship() -> None:
    for name in (
        "LICENSE",
        "README.md",
        "CHANGELOG.md",
        "CONFORMANCE.md",
        "pyproject.toml",
        "setup.cfg",
    ):
        assert ships(name) is True


def test_a_nested_tests_file_does_not_ship() -> None:
    """Confirmed against a real built sdist: distutils' own legacy default
    globs `tests/test*.py` -- direct children of `tests/` only, never a
    subdirectory. `tests/guardrail/test_approvals.py` reaches neither
    artifact today."""
    assert ships("tests/guardrail/test_approvals.py") is False


def test_a_top_level_tests_file_matching_the_legacy_glob_ships() -> None:
    assert ships("tests/test_decision_digest.py") is True
    assert ships("tests/test_check_shipped_text.py") is True


def test_a_top_level_tests_file_not_matching_the_glob_does_not_ship() -> None:
    """The legacy default globs `test*.py`, not every file directly under
    `tests/` -- `conftest.py` sits at the same depth but does not start
    with `test`, so it is not swept in by the same rule."""
    assert ships("tests/conftest.py") is False


def test_an_unrelated_root_file_does_not_ship() -> None:
    assert ships("PROGRESS.md") is False


def test_ships_path_strips_a_wheel_or_sdist_member_prefix_first() -> None:
    assert ships_path("onedoor-0.10.2-py3-none-any.whl!onedoor/guardrail/approvals.py") is True
    assert ships_path("onedoor-0.10.2.tar.gz!tests/guardrail/test_approvals.py") is False
    assert ships_path("onedoor-0.10.2.tar.gz!tests/test_decision_digest.py") is True


def test_the_ships_classifier_agrees_with_a_real_built_sdist() -> None:
    """The classifier's `tests/` boundary is a claim about what setuptools
    actually does, not an assumption -- skipped (not silently passed) when
    no sdist has been built, same convention as
    `tests/templates/test_pack.py::test_the_pack_is_in_the_built_wheel`.

    Checked both directions: every `tests/` member the real sdist actually
    carries must classify as shipped (no false negative -- a hit there
    would wrongly land in "report, don't fail"), and every OTHER tracked
    file under `tests/` must classify as not shipped (no false positive --
    a hit there would wrongly hard-fail the gate over something no user
    can download)."""
    sdists = sorted((ROOT / "dist").glob("*.tar.gz"))
    if not sdists:
        pytest.skip("no sdist built; run `python -m build` to check packaging")
    with tarfile.open(sdists[-1]) as t:
        names = {m.name.split("/", 1)[1] for m in t.getmembers() if m.isfile() and "/" in m.name}
    real_shipped_tests = {n for n in names if n.startswith("tests/")}

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    tracked_tests = {t for t in tracked if t.startswith("tests/")}

    assert real_shipped_tests <= tracked_tests, "the sdist carries an untracked tests/ file"
    for member in real_shipped_tests:
        assert ships(member), f"{member} really ships but the classifier says it does not"
    for path in tracked_tests - real_shipped_tests:
        assert not ships(path), f"{path} does not really ship but the classifier says it does"


# --- regression guard: the real tree, as committed, ships nothing today ------


def test_the_real_tree_carries_no_internal_process_text_anywhere() -> None:
    """What the live `shipped_text` gate checks, exercised directly here so a
    regression shows up as a unit-test failure with a path and line, not just
    a gate run. The check covers the whole tracked tree with no file
    exempted by path -- `scripts/check_shipped_text.py` itself is scanned
    exactly like any other file, its own forbidden words built from
    separately-declared fragments precisely so this reads zero; this test
    file needs no exclusion either, since its own planted examples are
    built the same way, never a literal substring of its own source."""
    hits = scan_tree()
    assert hits == []


def test_main_reads_zero_hits_with_no_path_exception() -> None:
    """The CLI itself, exercised end to end: no file anywhere is skipped by
    path (not this module's own source, not this test file), and the
    printed report says so."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_shipped_text", "--skip-build"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hit(s): 0" in result.stdout
    assert "CHECK OK" in result.stdout


def test_the_ships_tag_still_distinguishes_shipped_hits_from_the_rest() -> None:
    """`ships_path()` no longer decides pass/fail (the whole tree fails on
    any hit now), but it still answers a real, separate question -- used by
    `test_the_ships_classifier_agrees_with_a_real_built_sdist` and by this
    module's own report line. A planted hit in an unshipped path is still
    correctly classified as unshipped, even though it would fail the gate
    either way."""
    assert ships_path(UNSHIPPED_PATH) is False
    assert ships_path(SHIPPED_PATH) is True
