"""The Studio's palette: pinned to its source, corrected on the record, measured in CI.

Three kinds of check live here.

**Provenance** — the vendored block is the mockup's bytes and its digest is generated,
so a changed block fails loudly instead of being absorbed. *A design system that drifts
quietly is the same failure mode as an instrument that drifts quietly.*

**Correction** — core's approved mockup carried a measured accessibility defect (R057
§5). The fix is recorded *beside* the received data rather than edited *into* it, so the
palette the Studio renders can still be diffed against the palette core approved.

**Measurement** — "seal gold never signals state" and "muted, colorblind-checked" are
claims about perception, not about a stylesheet, so they are measured and the numbers
are printed. R057 §6: *a passing check whose numbers nobody sees cannot be audited.*
"""

from __future__ import annotations

import hashlib
import re

import pytest

from onedoor.studio import shell, tokens
from tests.viewer import colour

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


# --- The corrections layer (R057 §5) --------------------------------------------------


def test_the_vendored_block_still_holds_the_mockups_own_failing_values() -> None:
    """The correction is recorded beside the received data, never edited into it.

    E10's two-discipline arriving at a design system: **a correction to received data is
    a new artifact that cites it.** Editing the block would have been quicker and would
    have destroyed the only thing that makes the palette auditable — that it can still
    be compared with what core approved.
    """
    mockup = tokens.mockup_declarations()
    assert mockup["--refuse"] == "#c05548"
    assert mockup["--allow"] == "#4f9e6b"
    assert mockup["--review"] == "#d07f3c"
    for token, (corrected, _why) in tokens.CORRECTIONS.items():
        assert mockup[token] != corrected, f"{token} is listed as corrected and is unchanged"


def test_every_correction_says_which_measurement_forced_it() -> None:
    """A value with a story attached is not a provenance; a value with a number is."""
    for token, (_value, why) in tokens.CORRECTIONS.items():
        assert re.search(r"\d\.\d+:1", why), f"{token}'s reason cites no measurement: {why!r}"


def test_corrections_move_lightness_only() -> None:
    """R057 §5 approved lightening with hue preserved.

    Saturation is held too: the correction should be the smallest thing that makes the
    text readable, and a saturation change is a different design decision wearing an
    accessibility hat.
    """
    mockup = tokens.mockup_declarations()
    for token, (corrected, _why) in tokens.CORRECTIONS.items():
        was_h, was_l, was_s = colour.hsl(mockup[token])
        now_h, now_l, now_s = colour.hsl(corrected)
        assert abs(now_h - was_h) < 1.0, f"{token} hue moved {abs(now_h - was_h):.1f} degrees"
        assert abs(now_s - was_s) < 0.02, f"{token} saturation moved"
        assert now_l > was_l, f"{token} did not get lighter"


def test_brand_and_background_tokens_are_untouched() -> None:
    """The correction is surgical. Everything core got right stays exactly as approved."""
    mockup = tokens.mockup_declarations()
    for token, value in tokens.declarations().items():
        if token in tokens.CORRECTIONS:
            continue
        assert value == mockup[token], f"{token} changed and is not a declared correction"


# --- WCAG contrast: core's ruling, measured in CI with its numbers printed -------------

#: R057 §5, recorded as token law: *state text at chip size clears WCAG AA 4.5:1,
#: measured in CI, or the token does not ship.* The chip is .72rem/600 — about 11.5px
#: bold, which is NOT WCAG "large text" (18.66px bold), so 4.5:1 applies and not 3:1.
WCAG_AA_NORMAL_TEXT = 4.5


def test_state_text_clears_wcag_aa_on_its_own_chip(capsys) -> None:
    """The ruling, enforced. The numbers are printed so the check can be audited."""
    palette = tokens.palette()
    mockup = tokens.mockup_declarations()
    rows, failures = [], []
    for token in tokens.STATE_TOKENS:
        fg, bg = palette[token], palette[f"{token}-bg"]
        ratio = colour.contrast_ratio(fg, bg)
        was = colour.contrast_ratio(mockup[token], bg)
        rows.append(f"  {token:<9} {fg} on {bg}  {ratio:5.2f}:1   (mockup was {was:4.2f}:1)")
        if ratio < WCAG_AA_NORMAL_TEXT:
            failures.append(f"{token} is {ratio:.2f}:1, below {WCAG_AA_NORMAL_TEXT}:1")
    with capsys.disabled():
        print("\nstate text on its chip (WCAG AA needs 4.5:1 at this size):")
        print("\n".join(rows))
    assert not failures, "; ".join(failures)


def test_the_contrast_check_can_actually_fail() -> None:
    """A threshold nothing can fall below is a threshold that measures nothing."""
    assert colour.contrast_ratio("#c05548", "#38201d") < WCAG_AA_NORMAL_TEXT
    assert colour.contrast_ratio("#ffffff", "#000000") > WCAG_AA_NORMAL_TEXT


def test_chrome_text_clears_aa_and_the_one_gap_is_named(capsys) -> None:
    """The states are not the only text on the page.

    `--faint` is excluded and **named** rather than quietly skipped: it styles uppercase
    table headers at `.7rem/600` and is the one token that does not clear AA. It is
    reported to core rather than corrected here, because unlike the state chips it was
    not inside Q1's approved scope — **a token quietly widened past its ruling is the
    drift the corrections layer exists to prevent.**

    The assertion runs in the *unexpected* direction on purpose: if `--faint` is ever
    fixed, this test fails and tells whoever fixed it to delete the exception.
    """
    palette = tokens.palette()
    ground = palette["--ground"]
    rows = []
    for token in ("--ink", "--dim", "--gold"):
        ratio = colour.contrast_ratio(palette[token], ground)
        rows.append(f"  {token:<9} on --ground  {ratio:5.2f}:1")
        assert ratio >= WCAG_AA_NORMAL_TEXT, f"{token} is {ratio:.2f}:1 on the page ground"
    faint = colour.contrast_ratio(palette["--faint"], ground)
    with capsys.disabled():
        print("\nchrome text on the page ground:")
        print("\n".join(rows))
        print(f"  --faint   on --ground  {faint:5.2f}:1   KNOWN GAP, reported to core")
    assert faint < WCAG_AA_NORMAL_TEXT, (
        "--faint now clears AA; delete this known-gap branch and assert it like the rest"
    )


# --- Separation: what the contrast fix cost, measured and disclosed --------------------

#: Under NORMAL vision every signalling pair stays far apart. This floor is the measured
#: minimum (27.9, --review / --refuse) rounded down — it is the floor that still binds
#: after the contrast correction.
MINIMUM_DELTA_E_NORMAL = 24.0


def test_no_two_signalling_colours_collapse_for_normal_vision(capsys) -> None:
    palette = tokens.palette()
    names = ["--gold", *tokens.STATE_TOKENS]
    rows, worst = [], (99.0, "")
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            d = colour.delta_e(palette[a], palette[b])
            rows.append(f"  {a} / {b:<9} dE {d:5.1f}")
            worst = min(worst, (d, f"{a}/{b}"))
    with capsys.disabled():
        print("\nseparation under normal vision:")
        print("\n".join(rows))
    assert worst[0] >= MINIMUM_DELTA_E_NORMAL, f"{worst[1]} collapsed to dE {worst[0]:.1f}"


def test_the_dichromat_numbers_are_printed_even_where_no_floor_binds(capsys) -> None:
    """**The disclosure R057 §6 requires, and the honest part of this stage.**

    The 15.0 floor this file carried in V1 does not survive the contrast fix, and no
    choice of hex would have saved it: `--refuse` failed AA *because* it was dark, and
    any red light enough to read converges with `--review` under tritanopia and with
    `--allow` under deuteranopia. Four searches were run — foreground-only, background
    darkening, joint, and saturation-free — and the best any of them reached was 13.8,
    still under the old floor and only by making the refusal chip nearly invisible
    against the page.

    Measured cost at the worst pairs:

    | pair | mockup | corrected |
    |---|---|---|
    | `--review` / `--refuse` under tritanopia | 15.1 | **2.5** |
    | `--allow` / `--refuse` under deuteranopia | 18.0 | **6.5** |

    Contrast was chosen over separation deliberately, and the reasoning is the point.
    Contrast decides whether a person can **read the word**; delta-E decides whether they
    can tell two colours apart *when colour is the only signal*. **Colour is not the only
    signal here** — every chip carries its verdict as text, which is what WCAG 1.4.1
    actually requires, and `test_no_state_is_signalled_by_colour_alone` enforces that as
    a property rather than leaving it to a number that cannot be met.

    So there is no dichromat floor. There is a printed matrix, so a future token change
    that shrinks these further shows up in a CI log rather than passing in silence.
    """
    palette = tokens.palette()
    mockup = tokens.mockup_declarations()
    names = ["--gold", *tokens.STATE_TOKENS]
    with capsys.disabled():
        print("\nseparation under dichromatic vision — dE now [mockup]:")
        print(f"  {'pair':<24}" + "".join(f"{k:>18}" for k in colour.SIMULATIONS))
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                cells = []
                for kind in colour.SIMULATIONS:
                    now = colour.delta_e(
                        colour.simulate(palette[a], kind), colour.simulate(palette[b], kind)
                    )
                    was = colour.delta_e(
                        colour.simulate(mockup[a], kind), colour.simulate(mockup[b], kind)
                    )
                    cells.append(f"{now:6.1f} [{was:5.1f}]")
                print(f"  {a + ' / ' + b:<24}" + "".join(f"{c:>18}" for c in cells))
        print("  no floor binds here: colour is redundant coding, the chip carries its word")
    assert palette["--gold"] == mockup["--gold"], "brand must not have moved"


# --- The rule oneview §4 states, applied to the shell ----------------------------------

_HEX_IN_CSS = re.compile(r"#[0-9a-fA-F]{6}")


def test_no_stylesheet_emits_a_colour_that_is_not_a_token_or_a_declared_exception() -> None:
    """One hand-picked hex per screen is how a design system dies.

    Every stylesheet the Studio can emit is scanned, not just the shell's — the drift
    this prevents arrives one screen at a time, so a check that only ever looked at the
    first screen would report green through all of it.
    """
    from onedoor.studio import screens

    for name, sheet in (("shell", shell.css()), ("screens", screens.css())):
        stray = {
            h.lower()
            for h in _HEX_IN_CSS.findall(sheet)
            if h.lower() not in tokens.hex_values()
            and h.lower() not in shell.ALLOWED_NON_TOKEN_COLOURS
        }
        assert not stray, f"{name}: colours outside the palette and undeclared: {sorted(stray)}"


def test_every_declared_colour_exception_is_actually_used() -> None:
    """An exception nobody uses is a permission left lying around."""
    from onedoor.studio import screens

    sheets = shell.css() + screens.css()
    for hex_colour in shell.ALLOWED_NON_TOKEN_COLOURS:
        assert hex_colour in sheets, f"{hex_colour} is excused and never used; delete it"


def test_gold_is_never_used_where_a_state_word_is_used() -> None:
    """oneview §4, and R056 §2's boundary: gold may stand near information, never carry
    state. The seal region is hunted for verdict vocabulary rather than for gold itself,
    because a check that outlawed gold anywhere dynamic would teach people to route
    around it."""
    from tests.viewer.assertions import seal_state_violations

    assert seal_state_violations(shell.css()) == []
