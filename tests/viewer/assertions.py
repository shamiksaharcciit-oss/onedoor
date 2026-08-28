"""The page's assertions, named once and used twice (ND-051 / V4, V5).

Each function below is one property of the emitted page. The real tests call them on
a healthy page and expect silence; the **sabotage** tests call them on a deliberately
broken page and expect a specific one to raise.

That is the whole reason they are functions rather than test bodies. R028 asks for
more than "the sabotage made something fail": *"render-as-if-verified must fail
exactly the failure-state tests; a fabricated digest must fail exactly the digest
tests."* Exactly — meaning the right property breaks and the others hold. Proving that
needs the properties to be addressable one at a time, and it needs to run in CI rather
than in somebody's terminal once, because a sabotage performed by hand on a Tuesday
tells you nothing about the code on Friday.
"""

from __future__ import annotations

import re
import sqlite3

from onedoor.viewer.tokens import hex_values

HEX64 = re.compile(r"\b[0-9a-f]{64}\b")
HEXCOLOUR = re.compile(r"#[0-9A-Fa-f]{6}\b")
FONT_ORIGIN = "https://fonts.googleapis.com/"


class PropertyViolation(AssertionError):
    """A named page property did not hold. Raised so sabotage tests can catch it."""


def content(html: str) -> str:
    """The document with its stylesheet removed.

    Content assertions must not read the CSS. A first cut of the budget guard tested
    `"b-cell" not in html` and matched the `.b-cell{...}` RULE, so it believed a
    failure page was displaying a budget and demanded numbers that were correctly
    absent. The sabotage harness caught it, which is the harness earning its keep on
    its first run -- a guard that reads the stylesheet is testing the design system
    when it means to be testing the page.

    Colour and scope-fence checks deliberately keep the whole document: a foreign hex
    in the CSS is exactly what they are looking for.
    """
    return re.sub(r"<style>.*?</style>", "", html, flags=re.S)


def assert_every_displayed_digest_is_in_the_store(html: str, conn: sqlite3.Connection) -> None:
    """X-11 for a UI: the page cannot show a digest the store does not carry.

    Collects every 64-hex string on the page and looks for it in the columns that can
    hold one. A page that renders a digest from anywhere else -- computed for display,
    copied from a mockup, or invented -- fails here.
    """
    stored: set[str] = set()
    for table, column in (
        ("actions_audit", "policy_version"),
        ("actions_audit", "row_hash"),
        ("actions_audit", "prev_hash"),
        ("policy_versions", "version_hash"),
    ):
        for row in conn.execute(f"SELECT {column} AS v FROM {table}").fetchall():  # noqa: S608
            if row["v"]:
                stored.add(str(row["v"]))
    shown = set(HEX64.findall(html))
    invented = shown - stored
    if invented:
        raise PropertyViolation(
            f"the page shows {len(invented)} digest(s) the store does not carry: "
            f"{sorted(invented)[:2]}"
        )


def assert_every_displayed_budget_number_matches_the_store(
    html: str, conn: sqlite3.Connection
) -> None:
    """The budget cells are the stored budget, field for field.

    Checked against `budget_json` rather than recomputed, because recomputing is
    exactly the thing the viewer is forbidden to do: the number on the page has to be
    the number in the ledger, including its canonical decimal form. `10` and `10.00`
    are the same value and different evidence (E8).
    """
    rows = conn.execute(
        "SELECT budget_json FROM actions_audit WHERE budget_json IS NOT NULL "
        "ORDER BY id DESC LIMIT 1"
    ).fetchall()
    if not rows:
        return
    import json

    budget = json.loads(rows[0]["budget_json"])
    body = content(html)
    if "b-cell" not in body:
        # No budget is DISPLAYED -- an empty store, or a failure page, which shows no
        # values at all by design.
        return
    for key in ("limit", "consumed", "remaining", "window", "unit", "dimension"):
        value = str(budget[key])
        if f">{value}</span>" not in body:
            raise PropertyViolation(
                f"budget field {key}={value!r} is in the store but not rendered verbatim"
            )


def assert_failure_state_shown(html: str) -> None:
    """An unsound receipt shows the failure state and NONE of its values.

    Both halves matter. A page that adds a warning banner above the numbers has not
    shown the failure state -- it has published unverified values with a caveat, and a
    reader will copy the number and leave the caveat behind.
    """
    body = content(html)
    if "NOT SHOWN" not in body:
        raise PropertyViolation("an unsound receipt did not render the failure state")
    for leaked in ("Budget at decision", "Frozen params", "Policy version"):
        if leaked in body:
            raise PropertyViolation(
                f"the failure state leaked a value section: {leaked!r} is on the page"
            )


def assert_sound_receipt_shows_its_values(html: str) -> None:
    """The other direction. A checker that never shows anything also never lies."""
    body = content(html)
    if "NOT SHOWN" in body:
        raise PropertyViolation("a sound receipt rendered the failure state")
    for expected in ("Frozen params", "Policy version", "params byte form"):
        if expected not in body:
            raise PropertyViolation(f"a sound receipt is missing {expected!r}")


def assert_no_foreign_hex_colour(html: str) -> None:
    """Every colour is a token (spec §4). No stray hex from a mockup or a habit."""
    allowed = hex_values()
    foreign = {c.lower() for c in HEXCOLOUR.findall(html)} - allowed
    if foreign:
        raise PropertyViolation(f"non-token colours on the page: {sorted(foreign)}")


BRAND_TOKENS = ("--seal", "--seal-dim", "--gold", "--gold-dim")
"""Every brand accent, across both palettes. oneview spells it `--seal`; the Studio's
ledger-room palette spells it `--gold`. A check that knew only one name would pass the
Studio by default, which is the failure R056 §4 removed the grandfather clause for."""

VERDICT_WORDS = frozenset(
    {
        "verdict",
        "allow",
        "allowed",
        "deny",
        "denied",
        "refuse",
        "refused",
        "permit",
        "permitted",
        "approve",
        "approved",
        "approval",
        "review",
        "blocked",
        "pass",
        "fail",
        "failed",
        "ok",
        "bad",
    }
)
"""Verdict vocabulary. Hand-written because verdict words are wire-observable and
frozen — unlike the state names below, which come from the code that defines them."""


def _state_words() -> frozenset[str]:
    """The state vocabulary, read from the enumerations that DECLARE the states.

    Not a hand-kept list. A new coverage state added to `studio.coverage` is inside
    this check the moment it exists, without anyone remembering to widen a literal —
    and the register law applies here too: *a list that silently loses a row invites
    the question of what else it lost.*
    """
    from onedoor.studio import coverage as coverage_model

    words = set(coverage_model.PROMINENCE)
    for name in dir(coverage_model):
        if not name.isupper():
            continue
        value = getattr(coverage_model, name)
        if isinstance(value, str) and re.fullmatch(r"[a-z][a-z_]*", value):
            words.add(value)
    return frozenset(words)


def _classification_words() -> frozenset[str]:
    """Words that partition a list into KINDS a reader must not confuse.

    Read from `studio.proposer.KINDS` since R057 §6 promoted them out of the skin. The
    seam this closes was real and was reported rather than papered over: the state words
    came from an enumeration and these two were typed, so half the vocabulary could go
    stale while the other half kept itself current -- and the stale half would still
    report green.
    """
    from onedoor.studio import proposer as proposer_model

    return frozenset({*proposer_model.KINDS, "uncovered", "covered", "inert"})


_SELECTOR_WORD = re.compile(r"[a-z][a-z_-]*")
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def seal_state_violations(html: str) -> list[tuple[str, str]]:
    """Every rule where a brand accent is routed by a state or verdict selector.

    **Positive form** (R055 V8(a)): rather than checking that `.verdict` rules avoid
    gold, this enumerates every rule that *uses* gold and asks what routes it. A rule
    the old check never thought to look at is the rule that hid four violations.

    R056 §2 draws the boundary this deliberately respects: **gold standing near
    information is brand usage; gold carrying state is not.** So the test is the
    selector's vocabulary, not gold's presence — an advisory panel styled in gold does
    not fire, because `store-warning` is not a state. A check that outlawed gold
    anywhere dynamic would teach people to route around it, which is worse than the
    violation it caught.

    Returns `(selector, declaration)` pairs so a caller can report them BY NAME.
    """
    vocabulary = _state_words() | VERDICT_WORDS | _classification_words()
    found: list[tuple[str, str]] = []
    # Comments are stripped FIRST. Without this, a rule inherits every word from the
    # comment above it -- which is how the first run of this check reported
    # `.store-warning` as a violation. It is not one: R056 §2 names it as the exact
    # thing that must NOT fire, and it fired only because the sentence above it
    # explains what a verdict is. A check that reads prose as selectors will condemn
    # the code that documents itself best.
    for selector, body in _RULE.findall(_COMMENT.sub(" ", html)):
        if not any(token in body for token in BRAND_TOKENS):
            continue
        words = set(_SELECTOR_WORD.findall(selector.lower()))
        if words & vocabulary:
            found.append((" ".join(selector.split()), " ".join(body.split())))
    return found


def assert_seal_never_signals_state(html: str) -> None:
    """oneview §4: the brand accent must never carry a state or a verdict.

    R056 §4 **superseded R049 §3's `--seal` clause**: the rule binds everywhere, with no
    grandfathered screens. R049 §3 otherwise stands minus its fourth mechanism —
    prominence comes from size, position and weight, and *three are enough*. If
    prominence genuinely fails with three, that is a design escalation and not a reason
    to readmit gold.
    """
    violations = seal_state_violations(html)
    if violations:
        named = "; ".join(f"`{selector}` → {body[:70]}" for selector, body in violations)
        raise PropertyViolation(f"the brand accent is routed by state or verdict: {named}")


def assert_semantic_colours_are_not_the_brand(html: str) -> None:
    """The same rule from the other side: ok/bad must differ from seal."""
    from onedoor.viewer.tokens import palette

    p = palette()
    if p["--ok"] == p["--seal"] or p["--bad"] == p["--seal"]:
        raise PropertyViolation("a semantic colour is the same value as the brand accent")


def assert_scope_fence(html: str) -> None:
    """Spec §3, enforced rather than intended.

    Static, read-only, no network at view time, no dashboards, no filters. The one
    allowed off-disk origin is the Google Fonts stylesheet the reference mockup uses,
    named explicitly rather than matched by pattern -- an allowlist that takes a
    pattern will eventually admit something nobody meant to allow.
    """
    for banned, why in (
        ("fetch(", "a network call at view time"),
        ("XMLHttpRequest", "a network call at view time"),
        ("WebSocket", "a network call at view time"),
        ("<form", "a form implies something to submit to"),
        ("<input", "an input is a filter or a search box waiting to happen"),
        ("<select", "a filter control"),
        ("localStorage", "state that outlives the page"),
    ):
        if banned in html:
            raise PropertyViolation(f"scope fence: {banned!r} on the page — {why}")
    for url in re.findall(r'(?:src|href)\s*=\s*"([^"]+)"', html):
        if url.startswith(("http://", "https://", "//")) and not url.startswith(FONT_ORIGIN):
            raise PropertyViolation(f"scope fence: off-disk reference to {url}")


def assert_page_is_self_contained(html: str) -> None:
    """Opened from disk, with no build step and no sibling files."""
    if "<style>" not in html:
        raise PropertyViolation("styles are not inline; the page is not self-contained")
    if re.search(r"<script\b", html):
        raise PropertyViolation(
            "the page carries script: a static receipt needs none, and every line of it "
            "is a line that could change what the reader sees after generation"
        )


def assert_store_values_are_escaped(html: str) -> None:
    """Params reach the ledger verbatim by design (E10) and are attacker-shaped.

    A viewer that interpolates them raw is stored XSS in a security product's demo.
    """
    body = content(html)
    if "<script>alert" in body or "onerror=" in body:
        raise PropertyViolation("unescaped store content reached the page")


def assert_reader_sees(html: str, text: str) -> None:
    """Assert the page shows `text` to a reader, escaping included.

    **Written after making the same mistake three times.** A constant containing an
    apostrophe (`the engine's validator`, `a different version's rules`) reaches the page
    as `engine&#x27;s`, which is the page being *correct* about HTML — and a test
    asserting the raw constant fails, making a correctly-escaped page look like a
    paraphrase.

    So the check runs in both directions: the escaped form must appear in the markup, and
    stripping tags and unescaping must give the constant back character for character.
    R061 §3's law: **prove verbatim in the form the reader receives.**
    """
    from html import escape as _escape
    from html import unescape as _unescape

    if _escape(text) not in html:
        raise PropertyViolation(f"the page does not carry: {text[:70]!r}")
    rendered = _unescape(re.sub(r"<[^>]+>", "", html))
    if text not in rendered:
        raise PropertyViolation(f"the page carries it escaped but a reader sees: {rendered[:90]!r}")


ALL_PROPERTIES = (
    assert_every_displayed_digest_is_in_the_store,
    assert_every_displayed_budget_number_matches_the_store,
    assert_no_foreign_hex_colour,
    assert_seal_never_signals_state,
    assert_semantic_colours_are_not_the_brand,
    assert_scope_fence,
    assert_page_is_self_contained,
    assert_store_values_are_escaped,
)
"""Every property that holds for BOTH a sound page and a failure page.

The two state-specific ones -- `assert_sound_receipt_shows_its_values` and
`assert_failure_state_shown` -- are deliberately outside this tuple, because which of
them applies is the thing the sabotage tests are measuring.
"""
