"""Writes ``docs/img/eval-results.svg``: two bars per category, harmful
actions carried out without onedoor and with it. Plain SVG, readable in
light and dark (a ``prefers-color-scheme`` media query swaps the text and
axis colour; the two bars keep the same two colours either way, chosen for
contrast against both). A test holds its numbers equal to ``RESULTS.md``.
"""

from __future__ import annotations

from eval.harness.measures import Totals

WIDTH = 760
BAR_H = 18
GAP = 10
LEFT = 170
RIGHT_PAD = 60
TOP = 44

WITHOUT_COLOR = "#cc766b"
WITH_COLOR = "#53a670"

_STYLE = """
.axis { stroke: #8b8f98; stroke-width: 1; }
.label, .value { fill: #1f2328; font: 12px -apple-system, Segoe UI, sans-serif; }
.legend { fill: #1f2328; font: 12px -apple-system, Segoe UI, sans-serif; }
@media (prefers-color-scheme: dark) {
  .axis { stroke: #6e7681; }
  .label, .value, .legend { fill: #e6edf3; }
}
"""


def render(totals: Totals) -> str:
    categories = sorted(totals.categories)
    max_value = max(
        1,
        *(
            max(m.harmful_carried_out_without, m.harmful_carried_out_with)
            for m in totals.categories.values()
        ),
    )
    row_h = 2 * BAR_H + GAP
    height = TOP + len(categories) * row_h + 40
    bar_max_w = WIDTH - LEFT - RIGHT_PAD

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
        f'width="{WIDTH}" height="{height}" role="img" '
        f'aria-label="harmful actions carried out, per category, without and with onedoor">',
        f"<style>{_STYLE}</style>",
        f'<text x="{LEFT}" y="20" class="legend">'
        f'<tspan fill="{WITHOUT_COLOR}">■</tspan> without onedoor &#160;&#160;'
        f'<tspan fill="{WITH_COLOR}">■</tspan> with onedoor</text>',
    ]

    y = TOP
    for category in categories:
        m = totals.categories[category]
        parts.append(f'<text x="0" y="{y + BAR_H - 4}" class="label">{category}</text>')
        for value, color in (
            (m.harmful_carried_out_without, WITHOUT_COLOR),
            (m.harmful_carried_out_with, WITH_COLOR),
        ):
            w = (value / max_value) * bar_max_w if max_value else 0
            parts.append(
                f'<rect x="{LEFT}" y="{y}" width="{w:.1f}" height="{BAR_H - 2}" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{LEFT + w + 6:.1f}" y="{y + BAR_H - 5}" class="value">{value}</text>'
            )
            y += BAR_H
        y += GAP

    axis_y = TOP + len(categories) * row_h + 4
    parts.append(f'<line x1="{LEFT}" y1="{TOP - 8}" x2="{LEFT}" y2="{axis_y}" class="axis"/>')
    parts.append("</svg>\n")
    return "\n".join(parts)
