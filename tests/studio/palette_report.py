"""The palette's measurements, rendered for the run's report rather than by a test.

R057 §5 and §6 require these numbers **printed in CI where a reader sees them** — a
passing check whose numbers nobody sees cannot be audited. Until R062 they were printed
from inside test bodies with `capsys.disabled()`.

**R062 §4 approved moving them here, on design grounds and explicitly not as a fix.**
The matrices are *disclosure*, not assertion: nothing here can fail a build, and the
thresholds that can are still asserted in `test_tokens.py`. Reporting belongs in the
reporting phase, and `capsys.disabled()` mid-test was always borrowing the capture
machinery against its grain.

The separation matters for reading the register too: **a test that both measures and
announces hides which half failed.** Now the assertions fail loudly and the numbers are
printed once, in one place, at the end of the run.
"""

from __future__ import annotations

from onedoor.studio import tokens
from tests.viewer import colour

WCAG_AA_NORMAL_TEXT = 4.5
"""R057 §5's token law: state text at chip size clears 4.5:1, measured in CI."""

MINIMUM_DELTA_E_NORMAL = 24.0
"""The floor that still binds after the contrast correction; measured minimum floored."""


def _state_contrast() -> list[str]:
    palette = tokens.palette()
    mockup = tokens.mockup_declarations()
    rows = ["state text on its chip (WCAG AA needs 4.5:1 at this size):"]
    for token in tokens.STATE_TOKENS:
        fg, bg = palette[token], palette[f"{token}-bg"]
        rows.append(
            f"  {token:<9} {fg} on {bg}  {colour.contrast_ratio(fg, bg):5.2f}:1"
            f"   (mockup was {colour.contrast_ratio(mockup[token], bg):4.2f}:1)"
        )
    return rows


def _chrome_contrast() -> list[str]:
    palette = tokens.palette()
    ground = palette["--ground"]
    rows = ["chrome text on the page ground:"]
    for token in ("--ink", "--dim", "--gold", "--faint"):
        rows.append(
            f"  {token:<9} on --ground  {colour.contrast_ratio(palette[token], ground):5.2f}:1"
        )
    return rows


def _normal_separation() -> list[str]:
    palette = tokens.palette()
    names = ["--gold", *tokens.STATE_TOKENS]
    rows = ["separation under normal vision:"]
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            rows.append(f"  {a} / {b:<9} dE {colour.delta_e(palette[a], palette[b]):5.1f}")
    return rows


def _dichromat_separation() -> list[str]:
    """R057 §6's binding condition: the full matrix beside the mockup's own numbers.

    A shrunk baseline nobody sees cannot be audited, and the contrast correction shrank
    two of these badly — see `test_tokens.test_no_state_is_signalled_by_colour_alone`
    for the property that replaced the floor.
    """
    palette = tokens.palette()
    mockup = tokens.mockup_declarations()
    names = ["--gold", *tokens.STATE_TOKENS]
    rows = [
        "separation under dichromatic vision - dE now [mockup]:",
        f"  {'pair':<24}" + "".join(f"{k:>18}" for k in colour.SIMULATIONS),
    ]
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
            rows.append(f"  {a + ' / ' + b:<24}" + "".join(f"{c:>18}" for c in cells))
    rows.append("  no floor binds here: colour is redundant coding, the chip carries its word")
    return rows


def lines() -> list[str]:
    """Every measurement, in the order a reader wants them."""
    out: list[str] = []
    for section in (
        _state_contrast,
        _chrome_contrast,
        _normal_separation,
        _dichromat_separation,
    ):
        out.extend(section())
        out.append("")
    return out
