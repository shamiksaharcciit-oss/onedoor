"""Structural rules the viewer must not be able to break (ND-051 / V4).

Three of R028's requirements are not properties of a rendered page — they are
properties of the *code*, and a page test cannot see them. A viewer that grew its own
digest arithmetic would still emit a page that passed every content assertion, right
up until its answer disagreed with the checker's.

So they are checked against the source, with an AST rather than a grep: a comment
mentioning `hashlib` is not an import, and a test that cannot tell the difference will
be disabled by the first person it annoys.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from onedoor.viewer import tokens

VIEWER_DIR = Path(__file__).resolve().parents[2] / "onedoor" / "viewer"
REPO = Path(__file__).resolve().parents[2]

HASHING_MODULES = {"hashlib", "hmac", "zlib", "binascii"}


def _modules(path: Path) -> set[str]:
    """Every module imported by a file, from its AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
            found.add(node.module)
    return found


def _viewer_sources() -> list[Path]:
    return sorted(p for p in VIEWER_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_renderer_cannot_form_an_opinion_about_validity() -> None:
    """`page.py` renders the checker's answer and computes nothing of its own.

    R028: *the generator calls the same verification the engine/CLI uses — never its
    own copy.* The enforceable form of "never its own copy" is that the renderer has
    nothing to compute with: no hashing module, and from the engine only
    `guardrail.receipt`. Reaching into `policy_loader` or `decision` to re-derive
    something for display is exactly the drift this forbids.
    """
    imported = _modules(VIEWER_DIR / "page.py")
    assert not (imported & HASHING_MODULES), (
        f"the renderer imports {sorted(imported & HASHING_MODULES)}: it is one step from "
        f"computing a digest for display, which is the drift R028 forbids"
    )
    guardrail = {m for m in imported if m.startswith("onedoor.guardrail")}
    assert guardrail == {"onedoor.guardrail.receipt"}, (
        f"the renderer reaches into the engine beyond the verifier: {sorted(guardrail)}"
    )


def test_only_the_vendoring_module_hashes_anything() -> None:
    """One declared exception, and it hashes the SPEC, never the store.

    `tokens.py` pins the vendored design spec, which is a `rederivable-manifest`-shaped
    guarantee about a file core delivered — a different job from verifying a receipt,
    and it would be silly to route it through the engine. The exception is named here
    so it stays one exception rather than becoming a habit.
    """
    offenders = {
        p.name: sorted(_modules(p) & HASHING_MODULES)
        for p in _viewer_sources()
        if _modules(p) & HASHING_MODULES
    }
    assert offenders == {"tokens.py": ["hashlib"]}, (
        f"hashing appeared outside the vendoring module: {offenders}"
    )
    source = (VIEWER_DIR / "tokens.py").read_text(encoding="utf-8")
    assert "sha256(block.encode" in source
    assert "sqlite" not in source.lower(), "the vendoring module must never see the store"


def test_the_viewer_handles_exactly_the_statuses_the_checker_can_return() -> None:
    """The status→style map is derived from the enum, not guessed alongside it.

    A missing key is a `KeyError` on a page nobody rendered in a test; an extra key is
    a style for a status the checker cannot produce, which reads as dead code and
    survives for years. Comparing the two sets makes the enum the single source.

    Note the collision this test had to be written around: `Decision.FAILED` and
    `Status.FAILED` are both spelled `"failed"` while meaning entirely different
    things -- one is what the engine decided, the other is what the checker concluded
    about the record of it. A first cut of this test banned the string `"failed"` from
    the viewer and failed on `_DECISION_WORDS`, which is the *verdict* vocabulary and
    perfectly legitimate. Two vocabularies sharing a spelling is a trap for a reader
    as much as for a grep, which is why it is written down here.
    """
    from onedoor.guardrail.receipt import Status
    from onedoor.viewer.page import _STATUS_CLASS

    assert set(_STATUS_CLASS) == set(Status), (
        f"status handling and the checker's vocabulary have diverged: "
        f"{set(_STATUS_CLASS) ^ set(Status)}"
    )


def test_the_viewer_never_builds_a_status_from_a_string() -> None:
    """Statuses are read from the checker's enum, never constructed from text.

    Checked with an AST because two attempts at a string scan both failed on
    legitimate code -- once on `Decision.FAILED` spelled `"failed"`, once on the CSS
    class `"absent"`. Both were the test being blunt rather than the code being wrong,
    and a blunt structural test is worse than none: it gets deleted, and the rule goes
    with it.

    The invariant that actually matters is narrow and has no false positives: every
    mention of `Status` in the viewer is an attribute access on the enum
    (`Status.ABSENT`), never a call that turns a string into one (`Status("absent")`).
    A viewer that can build a status from text can build one the checker never gave.
    """
    for path in _viewer_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Status"
            ):
                raise AssertionError(
                    f"{path.name}:{node.lineno} constructs a Status from a value; "
                    f"statuses come from `receipt.Status` members only"
                )


# --- The vendored spec ------------------------------------------------------------


def test_the_vendored_spec_is_byte_identical_to_the_delivery() -> None:
    """Two copies of core's spec exist. They must be the same bytes, not similar files.

    `docs/oneview/` is where core delivers; `onedoor/viewer/_vendor/` is what ships in
    the wheel, because a docs directory does not travel in a package and an installed
    `onedoor` would otherwise have no spec to read. Both are fenced `-text` in
    `.gitattributes` for the reason the vendored manifest is: a CRLF rewrite would
    break the pin and present as a design-system tamper.
    """
    delivered = (REPO / "docs" / "oneview" / "ONEVIEW_DESIGN_SPEC.md").read_bytes()
    vendored = tokens.SPEC_PATH.read_bytes()
    assert vendored == delivered, "the vendored spec has drifted from core's delivery"
    assert hashlib.sha256(vendored).hexdigest() == tokens.SPEC_DIGEST


def test_the_token_block_matches_its_pin() -> None:
    """A design change must be looked at, never absorbed."""
    block = tokens.css_block()
    assert hashlib.sha256(block.encode("utf-8")).hexdigest() == tokens.SPEC_FENCE_DIGEST
    assert "--seal:#D4A855" in block


def test_a_revised_spec_raises_rather_than_rendering_the_old_palette(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Both directions. A viewer that falls back to a bundled copy when it cannot
    read the spec is a viewer that ships last week's palette without saying so."""
    fake = tmp_path / "spec.md"
    fake.write_text("```css\n--ground:#000000;\n```\n", encoding="utf-8")
    monkeypatch.setattr(tokens, "SPEC_PATH", fake)
    tokens.css_block.cache_clear()
    tokens.palette.cache_clear()
    try:
        with pytest.raises(tokens.TokenError, match="has changed"):
            tokens.css_block()
        monkeypatch.setattr(tokens, "SPEC_PATH", tmp_path / "absent.md")
        with pytest.raises(tokens.TokenError, match="not where the viewer expects"):
            tokens.css_block()
    finally:
        tokens.css_block.cache_clear()
        tokens.palette.cache_clear()


def test_every_token_the_page_uses_is_declared() -> None:
    """A `var(--typo)` renders as nothing and looks like a design decision."""
    import re

    from onedoor.viewer.page import PageModel, render

    html = render(PageModel(hero=None, verification=None, tail=[], is_sample=False))
    used = set(re.findall(r"var\((--[a-z-]+)\)", html))
    declared = set(re.findall(r"(--[a-z-]+)\s*:", tokens.root_css()))
    assert used <= declared, f"undeclared tokens used: {sorted(used - declared)}"


def test_the_spec_ships_in_the_package_not_only_in_the_repo() -> None:
    """0.3.0 shipped a wheel whose migrations were missing. Same shape of mistake."""
    import tomllib

    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["onedoor"]
    assert "viewer/_vendor/*.md" in patterns, (
        "the vendored spec is not declared as package data: an installed onedoor would "
        "raise TokenError on import of the viewer"
    )
