"""Scan for internal-process text that should never appear in this
repository at all -- not only in what an installed user gets.

A multi-party review process produced this codebase, and that process
has its own working vocabulary: a short alphanumeric code naming one
piece of work; a citation built from one of those codes, in a few
different typed forms; a name for a numbered unit of work, with an
optional trailing version digit or a range of several; a label pairing
a verdict word with a number, pointing at an item in an external list;
a bare pointer into an external list using an everyday word instead of
a formal label; the role-titles of the people and processes involved,
used as titles rather than as the ordinary English words they also
are; and the real name, surname, and account handle of the person who
owns this project. None of these belong in a public repository, read
by anyone who clones it, whether or not any of it ever reaches an
installed package. This module is that check, over the whole tracked
tree, with no file exempted -- including this one.

Scoped deliberately away from an older, unrelated memo-style citation
convention this repository also carries, with its own dedicated
verification tool and test: that convention's own ids are purely
numeric, with no trailing letters, and never share this module's own
alphanumeric code shape by construction, so the two cannot be confused
for one another. That older convention's own normative-requirement
citation shape (a short dashed code, cited bare) is likewise left
alone -- it becomes a hit only in the specific context of the word
that introduces THIS process's own citations, immediately in front of
one of the older scheme's ids, since neither scheme's own legitimate
use ever writes itself that way.

**What "ships" means here.** The wheel (the installed package's own
top-level directory, per `pyproject.toml`'s own package-discovery
rule) is what an installed user actually gets; the sdist adds a
handful of named root files plus, confirmed by actually unpacking a
real built sdist rather than reading `MANIFEST.in` and assuming, a
top-level `tests/test*.py` file -- distutils' own legacy default,
direct children of `tests/` only, never a subdirectory (see
`_SDIST_TOP_LEVEL_TEST_RE`). The sdist is shipped in full: anyone can
download it from a package index, so the same rule applies as the
wheel.

`ships()`/`ships_path()` answer that question and are used to tag each
hit's own report line, but they do not decide pass or fail: `main()`
fails on ANY hit in ANY tracked file, with no file exempted by path.
Two kinds of exact, narrow, named-and-tested data allowance exist
instead, for values that are legitimately shaped like a citation
without being one -- a CSS length that happens to end in a unit
suffix also used by this module's own citation shape; a handful of
real, already-public commit ids a few tests name on purpose -- and
both extend to cover this file's own necessary mention of that same
data (its allowance tables have to hold the exact values they allow,
which means holding them here too).

Every regex below that must search for one of the forbidden words or
phrases is built from separately-declared string fragments, joined
only at the point the pattern itself is compiled -- never as one
contiguous literal anywhere in this file's own source. This is the
same technique this module's own dedicated test already uses to plant
a proven example of each shape without the shape itself ever sitting
in that file's own text; applied here too, it is what lets this
module scan its own source and still read zero.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- building the forbidden words from parts, never as one contiguous literal ---

_ROLE_WORD_1 = "co" + "re"
_ROLE_WORD_2 = "old" + " " + "stand" + "ards"
_ROLE_WORD_3 = "age" + "nt"

_PERSON_GIVEN_NAME = "Sha" + "mik"
_PERSON_SURNAME = "Sa" + "ha"
_PERSON_HANDLE = "shamiksaharcciit" + "-oss"

# --- pattern categories ------------------------------------------------------

_BRIEF_ID = r"\d{2}[a-z]{2}"
"""The short alphanumeric code's own shape: two digits, two lowercase
letters. Also, by pure coincidence of alphabet, the shape of a CSS
length ending in a two-letter unit (`em`, `ch`) or, taken four
characters at a time, `px` -- see `_CSS_UNIT_EXACT_ALLOWANCES`."""
_UNIT_NUM = r"\d+[a-z]{0,2}\d*"
"""A work-unit's own number shape: digits, 0-2 lowercase letters, more
digits -- covers a bare number, one with a single trailing letter, and
one with a further trailing version digit after that letter."""

RULING_ID_RE = re.compile(
    rf"\bruling\s+{_BRIEF_ID}\b"  # the introducing word plus the short code
    rf"|\b{_ROLE_WORD_1}_{_BRIEF_ID}(?:\.\w+)?\b"  # a role-word-prefixed filename built from the code
    rf"|\bR-\d{{4}}-\d{{2}}-\d{{2}}{_BRIEF_ID}\b"  # a dated form carrying the code at the end
    # The older, unrelated convention's own normative-requirement citation
    # (a short dashed code) or its own numeric memo id is not itself a hit --
    # both are real, legitimate citation schemes with their own dedicated
    # tests. Either becomes one only in a RULING-citation context: the
    # introducing word immediately in front of it, which neither scheme's
    # own legitimate usage ever writes (that kind of requirement id is cited
    # bare; the older scheme names itself a different way, never this one).
    # Scoped to that introducing word specifically, not any id-shaped token,
    # so ordinary English stays unmatched.
    rf"|\bruling\s+(?:ND-\d+|R\d{{2,4}}|Response\s+\d{{2,4}})\b",
    re.IGNORECASE,
)
BRIEF_ID_RE = re.compile(rf"\b{_BRIEF_ID}\b", re.IGNORECASE)
"""Case-insensitive: the same short code, typed in capitals, is the same
citation in a different case."""
UNIT_NAME_RE = re.compile(rf"\bround\s+{_UNIT_NUM}\b", re.IGNORECASE)
UNIT_RANGE_RE = re.compile(rf"\brounds\s+{_UNIT_NUM}\s*(?:to|-)\s*{_UNIT_NUM}\b", re.IGNORECASE)
"""A plural range names every unit in between as surely as naming each
one alone would -- reported under the same category as a single named
unit, since it is the same kind of citation."""
FINDING_RE = re.compile(r"\bfinding\s+\d+\b", re.IGNORECASE)
"""A numbered citation to an external document a reader of this
repository cannot see, rather than a statement of what the code or the
change actually does."""
VERDICT_LABEL_RE = re.compile(r"\b(?:FIX|NOTE|STOP)\s+\d+\b")
"""A numbered label from a verdict vocabulary external to this
repository -- always written in capitals in practice, so matched that
way rather than case-insensitively, to leave the ordinary English verb
and noun these three words also are untouched. The label tells a
reader which numbered item to go look up elsewhere; the comment or
docstring carrying it should instead just say what the code does."""
QUESTION_RE = re.compile(
    r"\bquestions?\.md\s*#\s*\d+\b"
    r"|\bquestions?\s+\d+\b"
    r"|\b(?:item|backlog)\s+\d+\b",
    re.IGNORECASE,
)
"""A numbered reference into an external questions file, the same
pointer in its bare everyday spelling (the plain word "question" or
"questions" immediately followed by a number, with no file or anchor
at all), or the same underlying problem again in a different everyday
spelling (the bare word "item" or "backlog" immediately followed by a
number). Every one of these is a pointer to something a reader of this
repository cannot open, standing in for an explanation that belongs in
the comment or docstring itself -- all reported under the one
category, since it is the same kind of pointer either way."""
_ROLE_WORD_1_POSSESSIVE_RE = re.compile(rf"\b{_ROLE_WORD_1}['’]s\b")
_ROLE_WORD_1_ALONE_RE = re.compile(
    rf"(?<![-\w./\\]){_ROLE_WORD_1}(?!['’]s)(?![-\w])(?![./\\]\w)", re.IGNORECASE
)
"""The first role-word used standalone, not only possessive -- excluded
is a compound technical term either side of it (preceded by a word
character, `-`, `.` or `\\`, or followed by one, or by `.`/`\\`/`/` and
then a word character), so an ordinary compound or a dotted import
path never matches, while the word used alone -- naming the process
rather than meaning "central" or "essential" -- still does. This is a
recall-favoring pattern: every hit it finds in a file that does not
ship is reported, not assumed away -- only a hit that actually ships
forces a reword or a named, tested allowance."""
_ROLE_WORD_2_RE = re.compile(rf"\b{_ROLE_WORD_2}\b", re.IGNORECASE)
_ROLE_WORD_3_RE = re.compile(rf"\bonedoor\s+{_ROLE_WORD_3}\b", re.IGNORECASE)
_MEMO_HEADER_RE = re.compile(
    rf"^\s*(?:to|from|copy)\s*:[^\n]*\b{_ROLE_WORD_1}\b", re.IGNORECASE | re.MULTILINE
)
PERSON_NAME_RE = re.compile(
    rf"\b{_PERSON_GIVEN_NAME}\b|\b{_PERSON_SURNAME}\b|\b{_PERSON_HANDLE}\b", re.IGNORECASE
)
"""The project owner's own given name, surname, and account handle (the
part of the no-reply commit identity after the numeric prefix) --
allowed only where `_is_allowed_person_name` already allows it (the
package's own declared author/maintainer field, or a historical
release-note credit) -- everywhere else, any of the three is a hit."""

_ORDINAL_SUFFIXES = {"st", "nd", "rd", "th"}
"""An English ordinal has the short code's own shape, but only for the
number it actually follows -- `_is_real_ordinal` below checks the
digits, not just the suffix letters, because the suffix alone is too
broad: a two-digit-two-letter run can take this shape without being a
real ordinal for its own number."""


def _is_real_ordinal(matched: str) -> bool:
    """Whether `matched` (shaped like the short code: two digits then
    two letters) is actually the correct English ordinal for its own
    number (grammar: a number ending 11/12/13 always takes "th";
    otherwise 1/2/3 take st/nd/rd and everything else takes "th")."""
    suffix = matched[-2:].lower()
    if suffix not in _ORDINAL_SUFFIXES:
        return False
    number = int(matched[:2])
    if number % 100 in (11, 12, 13):
        return suffix == "th"
    last_digit = number % 10
    return {1: "st", 2: "nd", 3: "rd"}.get(last_digit, "th") == suffix


_CSS_UNIT_EXACT_ALLOWANCES: dict[str, frozenset[str]] = {
    "onedoor/studio/shell.py": frozenset(
        {"02em", "05em", "06em", "10px", "12em", "14px", "24em", "34em", "62ch"}
    ),
    "onedoor/viewer/canvas.py": frozenset({"08em"}),
    "onedoor/viewer/coverage.py": frozenset({"06em", "08em"}),
    "onedoor/viewer/page.py": frozenset(
        {
            "02em",
            "03em",
            "04em",
            "06em",
            "08em",
            "10px",
            "11px",
            "12px",
            "13px",
            "14em",
            "14px",
            "16px",
            "17px",
            "18px",
            "19px",
            "20px",
            "22px",
            "24px",
            "26px",
            "30px",
            "48px",
            "52ch",
            "56ch",
            "64ch",
            "72px",
            "86px",
        }
    ),
    "onedoor/viewer/proposal.py": frozenset({"08em"}),
    "docs/img/eval-results.svg": frozenset({"12px"}),
    "eval/harness/chart.py": frozenset({"12px"}),
    "tests/studio/test_tokens.py": frozenset({"66px"}),
    "docs/oneview/oneview.html": frozenset(
        {
            "02em",
            "03em",
            "04em",
            "05em",
            "08em",
            "10px",
            "11px",
            "12em",
            "12px",
            "13px",
            "14em",
            "14px",
            "16px",
            "17px",
            "18px",
            "19px",
            "20px",
            "22px",
            "24px",
            "26px",
            "28px",
            "30px",
            "34px",
            "46ch",
            "48px",
            "52ch",
            "64ch",
            "64px",
            "72px",
            "86px",
        }
    ),
}
"""Named allowance for the CLASSIFIER, not a content allowance: an exact
(path, matched text) pair, not a shape -- a shape-only rule swallows a
real short code by accident the moment one happens to end in a real
unit suffix too. This list is the complete, exact set of genuine CSS
lengths every file in this repository that actually contains one is
known to have, generated by running this module's own short-code
pattern (case-insensitively) over the current tree and keeping only
the hits ending in a real CSS unit -- never hand-typed, so
transcription cannot drop or add one. A value that moves to a
different file, or a new one appearing anywhere not on this exact
list, is NOT silently allowed -- it is a new hit, reported for a human
to extend this list consciously, which is the point: an allowance this
narrow can go stale and fail loud, never swallow a real id quietly."""

_THIS_FILE_PATH = Path(__file__).resolve().relative_to(ROOT).as_posix()
_ALL_ALLOWED_CSS_UNIT_VALUES: frozenset[str] = frozenset().union(
    *_CSS_UNIT_EXACT_ALLOWANCES.values()
)
"""This module's own source necessarily holds every value in
`_CSS_UNIT_EXACT_ALLOWANCES` literally, as that table's own data -- none
of it is a citation of anything, so this file's own path is allowed
against the exact union of values the table itself already names, and
only that union; a short code appearing in this file for any OTHER
reason is still a hit."""

COMMIT_ID_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.IGNORECASE)
"""A bare git commit id, 7 to 40 hex characters as a standalone word --
this process's own private history gets cited this way in a handful of
places (a docstring or a test name naming the exact commit that fixed
something), which is exactly as unreadable to anyone outside this
repository's own history as the short code or a numbered finding is,
and worse: the commit itself may never be published at all. Scoped to
a STANDALONE word (`\\b...\\b` on both sides) specifically so it cannot
match a substring of something longer -- a 64-character sha256 digest,
for instance, has no word boundary anywhere in its own middle, so no
7-to-40-character slice of one can ever satisfy both boundaries at
once; this is a property of the pattern itself, not a named allowance.
A 40-character bare hex run is the one truly ambiguous case (an
abbreviated git commit id and a raw sha1 digest are the identical
shape) -- `_is_allowed_commit_id` below allows the specific, named
contexts a pass over the real tree actually found."""
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE
)
"""Named allowance: a random UUID's hex digits can incidentally spell the
short code's own shape purely by chance. A short-code-shaped match whose
span sits entirely inside a real UUID is structurally not a citation --
the id has no process meaning to stand for, so there is nothing to
reword."""


@dataclass(frozen=True)
class Hit:
    category: str
    path: str
    line: int
    matched: str

    def __str__(self) -> str:
        return f"[{self.category}] {self.path}:{self.line}  {self.matched!r}"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_text_of(text: str, offset: int) -> str:
    """The full line containing `offset`, no trailing newline."""
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return text[start:] if end == -1 else text[start:end]


def scan_text(text: str, *, path: str) -> list[Hit]:
    """Every hit this module's own patterns find in `text`, named `path`
    only for the hit's own report line -- callers decide what `path`
    means (a tracked file, a member inside an unpacked wheel, ...)."""
    hits: list[Hit] = []
    ruling_spans: list[tuple[int, int]] = []
    for m in RULING_ID_RE.finditer(text):
        ruling_spans.append(m.span())
        hits.append(Hit("ruling_id", path, _line_of(text, m.start()), m.group()))
    uuid_spans = [m.span() for m in UUID_RE.finditer(text)]
    for m in BRIEF_ID_RE.finditer(text):
        if _is_allowed_brief_id(m.group(), path, m.start(), m.end(), uuid_spans):
            continue
        if any(s <= m.start() and m.end() <= e for s, e in ruling_spans):
            continue  # already counted as the containing ruling_id hit
        hits.append(Hit("brief_id", path, _line_of(text, m.start()), m.group()))
    for m in UNIT_NAME_RE.finditer(text):
        hits.append(Hit("round_name", path, _line_of(text, m.start()), m.group()))
    for m in UNIT_RANGE_RE.finditer(text):
        hits.append(Hit("round_name", path, _line_of(text, m.start()), m.group()))
    for m in FINDING_RE.finditer(text):
        hits.append(Hit("finding_citation", path, _line_of(text, m.start()), m.group()))
    for m in VERDICT_LABEL_RE.finditer(text):
        hits.append(Hit("verdict_label", path, _line_of(text, m.start()), m.group()))
    for m in QUESTION_RE.finditer(text):
        hits.append(Hit("numbered_question", path, _line_of(text, m.start()), m.group()))
    for m in _ROLE_WORD_1_POSSESSIVE_RE.finditer(text):
        line = _line_of(text, m.start())
        if _is_allowed_role_noun(path, _line_text_of(text, m.start())):
            continue
        hits.append(Hit("role_noun", path, line, m.group()))
    for m in _ROLE_WORD_1_ALONE_RE.finditer(text):
        line = _line_of(text, m.start())
        if _is_allowed_role_noun(path, _line_text_of(text, m.start())):
            continue
        hits.append(Hit("role_noun", path, line, m.group()))
    for m in _MEMO_HEADER_RE.finditer(text):
        line = _line_of(text, m.start())
        if _is_allowed_role_noun(path, _line_text_of(text, m.start())):
            continue
        hits.append(Hit("role_noun", path, line, m.group().strip()))
    for m in _ROLE_WORD_2_RE.finditer(text):
        line = _line_of(text, m.start())
        if _is_allowed_role_noun(path, _line_text_of(text, m.start())):
            continue
        hits.append(Hit("role_noun", path, line, m.group()))
    for m in _ROLE_WORD_3_RE.finditer(text):
        line = _line_of(text, m.start())
        if _is_allowed_role_noun(path, _line_text_of(text, m.start())):
            continue
        hits.append(Hit("role_noun", path, line, m.group()))
    for m in PERSON_NAME_RE.finditer(text):
        if _is_allowed_person_name(path, text, m.start(), m.end()):
            continue
        hits.append(Hit("person_name", path, _line_of(text, m.start()), m.group()))
    for m in COMMIT_ID_RE.finditer(text):
        if _is_allowed_commit_id(m.group(), path, text, m.start(), m.end(), uuid_spans):
            continue
        hits.append(Hit("commit_id", path, _line_of(text, m.start()), m.group()))
    return hits


def _is_allowed_brief_id(
    matched: str, path: str, start: int, end: int, uuid_spans: list[tuple[int, int]]
) -> bool:
    if _is_real_ordinal(matched):
        return True
    clean_path = path.split("!", 1)[1] if "!" in path else path
    if matched in _CSS_UNIT_EXACT_ALLOWANCES.get(clean_path, frozenset()):
        return True
    if clean_path == _THIS_FILE_PATH and matched in _ALL_ALLOWED_CSS_UNIT_VALUES:
        return True
    if _is_patch_file(path):
        return True
    if any(s <= start and end <= e for s, e in uuid_spans):
        return True
    return False


_DIGEST_PREFIX_RE = re.compile(r"(?:sha256|sha1|sha512|md5)[:\-=]?\s*$", re.IGNORECASE)
"""A hex run directly preceded by a digest algorithm's own name (a
requirements-file pinned-hash line, a checksum listing, a lock file's
own pinned digest) is a content hash, not a commit id -- nothing about
this process's own history to cite. Checked on the text immediately
before the match, not the match itself, since the match's own hex
digits never carry the algorithm name."""

_COMMIT_ID_ALLOWED_EXACT: dict[str, frozenset[str]] = {
    "eval/RESULTS.md": frozenset({"a49ecd77af01"}),
    "tests/guardrail/test_resume_key_approval_state.py": frozenset({"5b7a260", "f7a9333"}),
    "tests/guardrail/test_stored_v2_chain.py": frozenset({"61aaeed", "8ac78aa"}),
}
"""A real commit id that must legitimately stay, by exact (path, id)
pair: every one of these is a real, PUBLISHED commit on this project's
own public history (confirmed by checking ancestry directly against
the public release this process started from) -- a reader of the file
can actually open the commit being named, which is the one thing that
makes naming it by id fine rather than a citation of something nobody
outside this repository's own private history can ever see. Not a
path-wide or shape-wide allowance: anywhere else, or any OTHER id in
these same files, is still a hit, reworded into a plain description
(the normal remedy for a commit id that is NOT one of these)."""

_ALL_ALLOWED_COMMIT_IDS: frozenset[str] = frozenset().union(*_COMMIT_ID_ALLOWED_EXACT.values())
"""This module's own source necessarily holds every value in
`_COMMIT_ID_ALLOWED_EXACT` literally, as that table's own data -- each
one is already independently confirmed real and public there, so this
file's own path is allowed against the exact union of values the table
itself already names, and only that union."""

_COMMIT_ID_GLOBAL_ALLOWANCES = {
    "ed25519",
    "0123456789abcdef",
    "29e85d2c5166",
}
"""Named allowances, not scoped to any one path:

- a signing algorithm's own name, used throughout this codebase
  wherever a key or a signature is discussed, which happens to BE a
  valid 7-character hex string purely by coincidence of its own
  letters and digits.
- the hex alphabet itself, typed in order, used as a character-class
  literal inside actual validation code and quoted in a test
  illustrating the same check -- not a citation of anything, a
  sequence stating what a hex digit IS.
- a synthetic test value (a made-up 64-character digest never claimed
  to be real, sliced to its own first-eight-plus-last-four) used as
  the non-truncated counter-example a short-digest format check must
  NOT match -- it names no real commit or digest, only a shape a regex
  is tested against.

Checked case-insensitively, exactly like every other allowance here."""


def _is_allowed_commit_id(
    matched: str,
    path: str,
    text: str,
    start: int,
    end: int,
    uuid_spans: list[tuple[int, int]],
) -> bool:
    if not any(c in "abcdef" for c in matched.lower()):
        return True  # all-digit: a decimal number (a date, a count, an
        # amount, an IP's own integer form), never a real git commit id,
        # which is drawn from a near-uniform 16-symbol alphabet -- a true
        # commit id containing not one single a-f digit is astronomically
        # unlikely, while a 7-to-40-digit DECIMAL number appears constantly
        # in ordinary test data and prose.
    if matched.lower() in _COMMIT_ID_GLOBAL_ALLOWANCES:
        return True
    if any(s <= start and end <= e for s, e in uuid_spans):
        return True  # a UUID's own hex digits, not a commit id
    if _is_patch_file(path):
        return True  # a format-patch file's own blob/commit headers
    clean_path = path.split("!", 1)[1] if "!" in path else path
    if matched.lower() in _COMMIT_ID_ALLOWED_EXACT.get(clean_path, frozenset()):
        return True
    if clean_path == _THIS_FILE_PATH and matched.lower() in _ALL_ALLOWED_COMMIT_IDS:
        return True
    window = text[max(0, start - 16) : start]
    if _DIGEST_PREFIX_RE.search(window):
        return True  # a pinned dependency digest or checksum, not a commit id
    after = text[end : end + 3]
    if after.startswith("…") or after.startswith("..."):
        return True  # a truncated digest PREVIEW -- marked as partial by
        # its own trailing ellipsis, the natural shape a genuine commit-id
        # citation never has (an abbreviated git sha is used complete,
        # never shown with "more cut off here"). A real commit id reworded
        # away does not reappear as a truncated preview anywhere else, so
        # this needs no per-path scoping, only the shape itself.
    return False


_PERSON_NAME_ALLOWED_PATHS = {
    "pyproject.toml",
    "PKG-INFO",
    "CHANGELOG.md",
    "RELEASE_NOTES_v0.6.1.md",
    "RELEASE_NOTES_v0.6.2.md",
    ".gitattributes",
}
"""Named allowance: the package's own declared author
(`[project.authors]` in `pyproject.toml`, carried into the built
`PKG-INFO`/`METADATA`) legitimately names the real person who owns this
project -- that is what the field is for, not a process citation.
`CHANGELOG.md`'s own two mentions (crediting the same real person for
reporting bugs fixed in an early release) are pre-existing historical
release notes, not a citation of this process. The two release-note
files are each "drawn verbatim" from `CHANGELOG.md`'s own matching
section, by their own stated convention -- the identical credit, not a
second one, so held to the same reasoning. `.gitattributes`'s one
mention records a real historical approval date for a vendored
artifact's own provenance, the same kind of fact a changelog entry
records, not a citation either. Nothing else is on this list: any
other file naming the same person in their capacity as maintainer or
operator stays reported rather than silently allowed."""

_ROLE_NOUN_ALLOWED_PATHS = {
    "onedoor/_vendor/canonical.py",
    "reference/rederivable-manifest/canonical.py",
    "reference/rederivable-manifest/README.md",
    "scripts/verify_memo.py",
    "tests/protocol/test_memo_integrity.py",
}
"""Named allowance for the role_noun patterns: each file here cites a
process vocabulary this repository either has no authority to change,
or that already belongs to the OLDER, unrelated memo-protocol scheme
this module's own top docstring already scopes its id patterns away
from (not this process's own usage):

- the byte-identical, pinned copy of an upstream artifact (a dedicated
  test asserts it never drifts; its own surrounding files say it is
  not ours to edit) -- its role-word citations are the UPSTREAM
  source's own process, not this repository's.
- that same upstream artifact's reference copy, fenced identically,
  never hand-edited -- the same citations, for the same reason.
- the older memo-protocol scheme's own dedicated tool and test
  (already named in this module's own top docstring) -- their
  role-word is that OLDER scheme's own, a separate, already-audited
  concern with its own test, not a citation of this process.

No other file is on this list."""


def _is_allowed_role_noun(path: str, line_text: str) -> bool:
    clean_path = path.split("!", 1)[1] if "!" in path else path
    return clean_path in _ROLE_NOUN_ALLOWED_PATHS


_DRAFT_NAME_RE = re.compile(rf"draft-{_PERSON_SURNAME.lower()}-aadp")
_GITHUB_URL_RE = re.compile(rf"github\.com/{_PERSON_HANDLE}\b")
"""Named allowance, found empirically running the surname/handle
patterns over the real tree, not assumed from a short list: the
surname also appears as part of this project's own AADP Internet-Draft
formal name (IETF drafts are conventionally named after an author, the
same way a well-known TLS draft is named after its own authors), and
the handle appears inside a real project URL on the host this
repository's own remote lives on. Neither is a citation of this
process; both are scoped to the exact literal context (immediately
part of the draft name, or inside that exact URL host+path), never a
bare path or a shape broad enough to swallow an unrelated mention."""


_PATCH_FILE_RE = re.compile(r"^patches/[^/]+\.patch$")
"""Named allowance: an exported `git format-patch` file is a byte-exact
diff, never ours to edit. Its own `From:` header is real authorship, by
definition -- the person who actually wrote that commit -- and a
patch's own quoted-printable-encoded `Subject:` line can spell the
short code's own shape purely by MIME encoding accident (a literal
space, encoded, reads as two letters following two digits). Scoped to
the exact `patches/*.patch` glob, no other file."""


def _is_patch_file(path: str) -> bool:
    clean_path = path.split("!", 1)[1] if "!" in path else path
    return bool(_PATCH_FILE_RE.match(clean_path))


def _is_allowed_person_name(path: str, text: str, start: int, end: int) -> bool:
    clean_path = path.split("!", 1)[1] if "!" in path else path
    name = clean_path.rsplit("/", 1)[-1]
    if name in _PERSON_NAME_ALLOWED_PATHS or name.endswith(("METADATA", "/METADATA")):
        return True
    if _is_patch_file(path):
        return True
    window = text[max(0, start - 24) : end + 24]
    return bool(_DRAFT_NAME_RE.search(window) or _GITHUB_URL_RE.search(window))


# --- what ships ---------------------------------------------------------

SHIPS_WHEEL_ROOT_FILES = frozenset(
    {"LICENSE", "README.md", "CHANGELOG.md", "CONFORMANCE.md", "pyproject.toml", "setup.cfg"}
)
"""Named allowance for the CLASSIFIER, not a content allowance: these root
files ship via the sdist (three by setuptools' own default rule, two
more because `MANIFEST.in` names them) and are read as the project's own
front matter -- a hit here is a hard failure, same as a hit under
`onedoor/`."""

_SDIST_TOP_LEVEL_TEST_RE = re.compile(r"^tests/test[^/]*\.py$")
"""Named allowance for the CLASSIFIER: the sdist is shipped in full,
`tests/` included -- the same rule as the wheel, since anyone can
download it from a package index. It is built by plain
`setuptools.build_meta`, with no SCM plugin and no
`recursive-include tests` line in `MANIFEST.in`. Empirically confirmed by
building a real sdist and listing its members directly: distutils' own
legacy `sdist.add_defaults()` glob-includes `tests/test*.py` -- direct
children of `tests/` only, never a subdirectory. Everything under a
`tests/` subdirectory does NOT currently reach the sdist at all.
`test_the_ships_classifier_agrees_with_a_real_built_sdist` guards this
boundary against a future setuptools version changing the default."""


def ships(path: str) -> bool:
    """Whether `path` (a tracked-file path, repo-root-relative, forward
    slashes) is part of what an installed user actually gets (the wheel)
    or reaches the sdist -- the named root files, or a top-level
    `tests/test*.py` file (see `_SDIST_TOP_LEVEL_TEST_RE`). The sdist is
    shipped in full, so this function's job is to classify what the
    sdist ACTUALLY carries today, empirically -- not what a reader might
    assume `tests/` means."""
    if path.startswith("onedoor/"):
        return True
    if path in SHIPS_WHEEL_ROOT_FILES:
        return True
    return bool(_SDIST_TOP_LEVEL_TEST_RE.match(path))


# --- collecting what to scan -------------------------------------------


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / line for line in out.stdout.splitlines() if line]


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None  # binary or unreadable -- nothing this check can read as text


def scan_tree() -> list[Hit]:
    """Every tracked file, with no exception by path -- this module's own
    source is scanned exactly like any other file now; its own regexes
    are built from separately-declared fragments precisely so that this
    reads zero regardless."""
    hits: list[Hit] = []
    for path in tracked_files():
        text = _read_text(path)
        if text is None:
            continue
        rel = path.relative_to(ROOT).as_posix()
        hits.extend(scan_text(text, path=rel))
    return hits


def scan_wheel(wheel_path: Path) -> list[Hit]:
    hits: list[Hit] = []
    with zipfile.ZipFile(wheel_path) as z:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            try:
                text = z.read(name).decode("utf-8")
            except UnicodeDecodeError:
                continue
            hits.extend(scan_text(text, path=f"{wheel_path.name}!{name}"))
    return hits


def scan_sdist(sdist_path: Path) -> list[Hit]:
    hits: list[Hit] = []
    with tarfile.open(sdist_path) as t:
        for member in t.getmembers():
            if not member.isfile():
                continue
            f = t.extractfile(member)
            if f is None:
                continue
            try:
                text = f.read().decode("utf-8")
            except UnicodeDecodeError:
                continue
            # Strip the sdist's own "<name>-<version>/" prefix so the path
            # reads the same as a tracked-file path (ships() needs that).
            name = member.name.split("/", 1)[1] if "/" in member.name else member.name
            hits.extend(scan_text(text, path=f"{sdist_path.name}!{name}"))
    return hits


def ships_path(hit_path: str) -> bool:
    """`ships()` for a hit's own recorded path, which may carry a
    wheel/sdist member prefix (`name.whl!onedoor/x.py`) -- strips that
    prefix first, since `ships()` itself only knows tracked-file paths."""
    if "!" in hit_path:
        hit_path = hit_path.split("!", 1)[1]
    return ships(hit_path)


def build_and_scan_artifacts() -> list[Hit]:
    """Builds a fresh wheel and sdist into a throwaway directory (never
    the repo's own `dist/`, so this never interferes with the gate's own
    convention of clearing `dist/`/`build/` before and after a build
    check) and scans both."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(tmp_path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        hits: list[Hit] = []
        for wheel in tmp_path.glob("*.whl"):
            hits.extend(scan_wheel(wheel))
        for sdist in tmp_path.glob("*.tar.gz"):
            hits.extend(scan_sdist(sdist))
        return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.check_shipped_text",
        description=(
            "Scan every tracked file, and the built wheel/sdist, for internal-process "
            "text -- citation ids, numbered labels, role titles, and the project "
            "owner's own name -- with no file exempted by path."
        ),
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="scan tracked files only; skip building and scanning the wheel/sdist",
    )
    args = parser.parse_args(argv)

    hits = scan_tree()
    if not args.skip_build:
        hits.extend(build_and_scan_artifacts())

    print(
        f"scanned: {len(tracked_files())} tracked file(s)"
        + (" + the built wheel/sdist" if not args.skip_build else "")
    )
    print(f"hit(s): {len(hits)}")
    for h in sorted(hits, key=lambda h: (h.path, h.line)):
        ship_tag = "SHIP" if ships_path(h.path) else "    "
        print(f"  {ship_tag}  {h}")

    if hits:
        print(f"CHECK FAILED: {len(hits)} hit(s) of internal-process text in the tree")
        return 1
    print("CHECK OK: no internal-process text anywhere in the tracked tree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
