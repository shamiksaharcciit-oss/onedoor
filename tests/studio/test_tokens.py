"""The Studio's palette: pinned to its source, and measured rather than trusted.

Two kinds of check live here.

**Provenance** — the block is the mockup's bytes, the digest is generated, and a
changed block fails loudly instead of being absorbed. Same shape as
`tests/viewer/test_tokens.py` because it is the same discipline: *a design system that
drifts quietly is the same failure mode as an instrument that drifts quietly.*

**Separation** — oneview §4 says seal gold never signals state, and the design note
says the state colours are "muted, colorblind-checked". Neither is a claim a stylesheet
can make; both are claims about *perception*, so they are measured. The floors below
are the **measured values rounded down**, not thresholds picked to pass: a floor
invented above what the palette achieves is a test that fails on arrival, and one
invented far below it is a test that would not notice the palette going wrong.
"""

from __future__ import annotations

import hashlib
import math
import re

import pytest

from onedoor.studio import shell, tokens

# --- Provenance ---------------------------------------------------------------------


def test_the_vendored_block_hashes_to_what_this_build_pinned() -> None:
    raw = tokens.BLOCK_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == tokens.BLOCK_DIGEST


def test_a_changed_block_is_refused_rather_than_absorbed(monkeypatch) -> None:
    """The direction that matters: silence on change is the failure being prevented."""
    tokens.css_block.cache_clear()
    monkeypatch.setattr(tokens, "BLOCK_DIGEST", "0" * 64)
    with pytest.raises(tokens.TokenError, match="has changed"):
        tokens.css_block()
    tokens.css_block.cache_clear()
    monkeypatch.undo()
    tokens.css_block.cache_clear()


def test_a_missing_block_raises_rather_than_falling_back(monkeypatch, tmp_path) -> None:
    """No silent default palette. A Studio that cannot find its tokens says so."""
    tokens.css_block.cache_clear()
    monkeypatch.setattr(tokens, "BLOCK_PATH", tmp_path / "gone.css")
    with pytest.raises(tokens.TokenError, match="not where it is expected"):
        tokens.css_block()
    monkeypatch.undo()
    tokens.css_block.cache_clear()


def test_the_ledger_room_ground_is_warm_and_not_oneviews() -> None:
    """The divergence is specified, so it is asserted — not left to look like a bug.

    The design note: *"Ground: warm charcoal/umber (#1c1713 family), never blue-black."*
    If someone ever "fixes" the Studio by pointing it at `viewer.tokens`, this fails.
    """
    from onedoor.viewer import tokens as oneview

    ground = tokens.palette()["--ground"]
    assert ground == "#1c1713"
    assert ground != oneview.palette()["--ground"]
    r, g, b = (int(ground[i : i + 2], 16) for i in (1, 3, 5))
    assert r > b, "warm means red above blue; this ground is blue-black"


def test_every_state_and_brand_token_the_shell_relies_on_exists() -> None:
    """A token referenced in CSS but absent from the block renders as nothing at all."""
    declared = tokens.declarations()
    for name in (*tokens.STATE_TOKENS, *tokens.BRAND_TOKENS):
        assert name in declared, f"{name} is used by the design language and is not declared"


def test_the_emitted_css_carries_every_declaration() -> None:
    css = tokens.root_css()
    for name, value in tokens.declarations().items():
        assert f"{name}:{value};" in css


# --- Separation, measured -------------------------------------------------------------


def _linear(hex_colour: str) -> tuple[float, float, float]:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)


def _lab(hex_colour: str) -> tuple[float, float, float]:
    r, g, b = _linear(hex_colour)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(a: str, b: str) -> float:
    """CIE76. Coarse, and coarse is the right instrument for a floor."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b), strict=True)))


# Vienot/Brettel/Mollon 1999, the sRGB-space dichromat matrices.
_SIMULATIONS = {
    "protanopia": ((0.11238, 0.88762, 0.0), (0.11238, 0.88762, 0.0), (0.00401, -0.00401, 1.0)),
    "deuteranopia": ((0.29275, 0.70725, 0.0), (0.29275, 0.70725, 0.0), (-0.02234, 0.02234, 1.0)),
    "tritanopia": ((1.0, 0.14461, -0.14461), (0.0, 0.85653, 0.14347), (0.0, 0.85653, 0.14347)),
}


def _simulate(hex_colour: str, kind: str) -> str:
    lin = _linear(hex_colour)
    matrix = _SIMULATIONS[kind]
    out = []
    for row in matrix:
        v = max(0.0, min(1.0, sum(row[c] * lin[c] for c in range(3))))
        srgb = v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        out.append(f"{round(srgb * 255):02x}")
    return "#" + "".join(out)


#: Measured on the pinned palette, floored to the next whole number below. The tightest
#: pair in the whole set is brand-vs-state under deuteranopia (--gold / --review, 15.6),
#: which is exactly the boundary oneview §4 draws -- so it is the one under a floor.
MINIMUM_DELTA_E = 15.0


@pytest.mark.parametrize("kind", [None, *_SIMULATIONS])
def test_no_two_signalling_colours_collapse_into_each_other(kind: str | None) -> None:
    """Brand and the three states stay apart, for normal and dichromatic vision.

    The design note asks for state colours that are "colorblind-checked". This is that
    check, run rather than asserted, and run over the brand token too: a review-amber a
    reader could mistake for the wordmark would break §4 from the other side, without a
    single line of CSS being wrong.
    """
    palette = tokens.palette()
    names = [*tokens.BRAND_TOKENS[:1], *tokens.STATE_TOKENS]
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            ca, cb = palette[a], palette[b]
            if kind is not None:
                ca, cb = _simulate(ca, kind), _simulate(cb, kind)
            delta = _delta_e(ca, cb)
            assert delta >= MINIMUM_DELTA_E, (
                f"{a} and {b} are {delta:.1f} apart under "
                f"{kind or 'normal vision'}; the palette must keep them "
                f"at least {MINIMUM_DELTA_E} apart or a verdict is unreadable"
            )


def test_the_separation_check_can_actually_fail() -> None:
    """A measurement that cannot come out low is not a measurement.

    Two colours one step apart must land far under the floor; otherwise the parametrised
    test above is passing because the metric is flat, not because the palette is good.
    """
    assert _delta_e("#c9a227", "#c9a228") < 1.0
    assert _delta_e("#1c1713", "#e8ddcc") > MINIMUM_DELTA_E


# --- The rule oneview §4 states, applied to the shell ----------------------------------

_HEX_IN_CSS = re.compile(r"#[0-9a-fA-F]{6}")


def test_the_shell_emits_no_colour_that_is_not_a_token_or_a_declared_exception() -> None:
    """One hand-picked hex per screen is how a design system dies."""
    stray = {
        h.lower()
        for h in _HEX_IN_CSS.findall(shell.css())
        if h.lower() not in tokens.hex_values() and h.lower() not in shell.ALLOWED_NON_TOKEN_COLOURS
    }
    assert not stray, f"colours outside the palette and undeclared: {sorted(stray)}"


def test_gold_is_never_used_where_a_state_word_is_used() -> None:
    """oneview §4, and R056 §2's boundary: gold may stand near information, never carry
    state. The seal region is hunted for verdict vocabulary rather than for gold itself,
    because a check that outlawed gold anywhere dynamic would teach people to route
    around it."""
    state_words = ("allow", "deny", "denied", "refuse", "refused", "permit", "permitted", "review")
    for rule in shell.css().split("}"):
        if "var(--gold" not in rule:
            continue
        selector = rule.split("{")[0].lower()
        hits = [w for w in state_words if re.search(rf"\b{w}\b", selector)]
        assert not hits, f"gold carries state in `{selector.strip()}`: {hits}"
