"""Colour measurement, in one place, so every claim about the palette is the same claim.

Lives beside the viewer assertions because both skins are measured with it, and because
a second implementation of "what is the contrast ratio" is a second answer waiting to
disagree with the first.

Nothing here is a policy. The thresholds live with the tests that assert them, and the
numbers live in the CI output — R057 §6: *a passing check whose numbers nobody sees
cannot be audited.*
"""

from __future__ import annotations

import colorsys
import math

__all__ = [
    "SIMULATIONS",
    "contrast_ratio",
    "delta_e",
    "hsl",
    "relative_luminance",
    "simulate",
]


def _channels(hex_colour: str) -> tuple[float, float, float]:
    h = hex_colour.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #rrggbb, got {hex_colour!r}")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _linear(hex_colour: str) -> tuple[float, float, float]:
    """sRGB → linear light. The gamma step everyone forgets, which is why it is here."""
    return tuple(  # type: ignore[return-value]
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in _channels(hex_colour)
    )


def _to_hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in (r, g, b))


def hsl(hex_colour: str) -> tuple[float, float, float]:
    """`(hue in degrees, lightness 0-1, saturation 0-1)`."""
    r, g, b = _channels(hex_colour)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    return (hue * 360, lightness, saturation)


def relative_luminance(hex_colour: str) -> float:
    """WCAG 2.x relative luminance."""
    r, g, b = _linear(hex_colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio, 1.0 to 21.0. Order-independent."""
    la, lb = relative_luminance(a), relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _lab(hex_colour: str) -> tuple[float, float, float]:
    r, g, b = _linear(hex_colour)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (841 / 108) * t + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(a: str, b: str) -> float:
    """CIE76 colour difference. Coarse, and coarse is right for a floor."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b), strict=True)))


#: Viénot, Brettel & Mollon (1999), the sRGB-space dichromat matrices. Named rather than
#: inlined so a reader can check them against the paper instead of trusting them.
SIMULATIONS: dict[str, tuple[tuple[float, float, float], ...]] = {
    "protanopia": (
        (0.11238, 0.88762, 0.0),
        (0.11238, 0.88762, 0.0),
        (0.00401, -0.00401, 1.0),
    ),
    "deuteranopia": (
        (0.29275, 0.70725, 0.0),
        (0.29275, 0.70725, 0.0),
        (-0.02234, 0.02234, 1.0),
    ),
    "tritanopia": (
        (1.0, 0.14461, -0.14461),
        (0.0, 0.85653, 0.14347),
        (0.0, 0.85653, 0.14347),
    ),
}


def simulate(hex_colour: str, kind: str) -> str:
    """`hex_colour` as a dichromat of `kind` sees it."""
    linear = _linear(hex_colour)
    out = []
    for row in SIMULATIONS[kind]:
        v = max(0.0, min(1.0, sum(row[c] * linear[c] for c in range(3))))
        out.append(v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)
    return _to_hex(*out)
