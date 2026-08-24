"""The coverage map's Oneview skin (ND-052 / S4-T5).

Renders `studio.coverage.CoverageMap` and computes nothing — the split that keeps every
renderer in this package from growing a second opinion.

No semantic pair, and the reason is not squeamishness (R049 §3)
-----------------------------------------------------------------
`--ok`/`--bad` are **verdicts' alone**, and the argument that nearly overturned that here
is the argument that settles it. *Uncovered genuinely is default-denied* — true. But a
verdict colour on a receipt means **this action was denied**, a fact about one past
event, while the same colour on a coverage cell would mean **actions of this kind would
be denied**, a prediction about a class. Teach an operator that red is a prediction on
one surface and they will read the receipt's red as a prediction too. **A colour that
means two things means neither**, and the pair is spent everywhere or nowhere.

So prominence comes from **size, position, weight and `--seal`**, and the order comes
from `coverage.PROMINENCE`, which ranks by behaviour:

- **`declared_inert` first** — sounds fine, behaves dangerously: a silent permit inside a
  rule its author believes is governing.
- **`uncovered_observed` second** — sounds bad, behaves safely: the engine refuses,
  loudly, and the operator finds out.
- **`unreached` third** — rendered in the **absent** style: never as safe, and never
  as a fault. A declared effect nothing reaches may be dead configuration or a control
  waiting for traffic, and the map does not know which.
- **`covered` quiet.**

*Rank by what a state does at decision time, not by how alarming its name sounds.*
"""

from __future__ import annotations

from html import escape

from onedoor.studio import coverage as model
from onedoor.viewer.tokens import root_css

STATE_COLOUR_VARS = ("--ok", "--bad", "--ok-bg", "--bad-bg", "--ok-bd", "--bad-bd")
"""Forbidden on this surface entirely. A coverage map contains no verdicts."""

STATE_LABEL = {
    model.DECLARED_INERT: "DECLARED, INERT",
    model.UNCOVERED_OBSERVED: "UNCOVERED",
    model.UNREACHED: "UNREACHED",
    model.COVERED: "covered",
}
"""Derived from `PROMINENCE` rather than written beside it — a missing key is a KeyError
in a test, where an independently maintained list would be a silently unlabelled row."""


def _e(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _rows(rows: list[model.Row], m: model.CoverageMap) -> str:
    out = []
    for row in m.ranked(rows):
        detail = f"<p class='detail'>{_e(row.detail)}</p>" if row.detail else ""
        out.append(
            f"<li class='row {_e(row.state)}'>"
            f"<span class='state'>{_e(STATE_LABEL[row.state])}</span>"
            f"<span class='name'>{_e(row.name)}</span>{detail}</li>"
        )
    return "".join(out) or "<li class='row empty'><span class='name'>nothing declared</span></li>"


def _counts(rows: list[model.Row], m: model.CoverageMap) -> str:
    tally = m.counts(rows)
    cells = "".join(
        f"<li class='{_e(state)}'>{_e(STATE_LABEL[state])} <b>{tally[state]}</b></li>"
        for state in model.PROMINENCE
    )
    return f"<ul class='tally'>{cells}</ul>"


_PAGE_CSS = """
body{background:var(--ground);color:var(--ink);font-family:'Archivo',system-ui,sans-serif;
margin:0;padding:2rem;}
h1{color:var(--seal);font-size:1.1rem;letter-spacing:.08em;text-transform:uppercase;}
h2{font-size:.85rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}
section{background:var(--card);border:1px solid var(--border);border-radius:6px;
padding:1rem 1.25rem;margin:1rem 0;}
.mono,.citation{font-family:'IBM Plex Mono',ui-monospace,monospace;
font-variant-numeric:tabular-nums;word-break:break-all;}
ul{list-style:none;padding:0;}
.row{border-left:2px solid var(--border-soft);padding:.5rem .8rem;margin:.4rem 0;}
.row .state{display:block;font-size:.65rem;letter-spacing:.1em;color:var(--faint);}
.row .name{font-family:'IBM Plex Mono',ui-monospace,monospace;}
.row .detail{color:var(--muted);font-size:.8rem;margin:.3rem 0 0;}
/* Prominence by SIZE, WEIGHT, POSITION and SEAL -- never by the semantic pair, which
   belongs to verdicts. A coverage cell is a prediction about a class; a verdict is a
   fact about one event, and one colour cannot mean both. */
.row.declared_inert{border-left:3px solid var(--seal);background:var(--card-hi);
padding:.8rem;}
.row.declared_inert .name{font-size:1.05rem;font-weight:700;}
.row.declared_inert .state{color:var(--seal);font-weight:700;}
.row.uncovered_observed{border-left:3px solid var(--seal);border-left-style:dashed;}
.row.uncovered_observed .name{font-weight:600;}
.row.unreached{opacity:.75;}
.row.unreached .name{font-style:italic;color:var(--muted);}
.row.covered{opacity:.55;}
.tally{display:flex;gap:1.25rem;font-size:.8rem;color:var(--muted);}
.tally .declared_inert b{color:var(--seal);}
.citation{color:var(--muted);font-size:.78rem;}
.notes{color:var(--faint);font-size:.75rem;border-top:1px solid var(--border-soft);
padding-top:.6rem;}
.notes li{margin:.35rem 0;}
"""


def render_page(m: model.CoverageMap) -> str:
    """The whole map as one HTML document. `root_css()` raises rather than falling back."""
    notes = "".join(f"<li>{_e(note)}</li>" for note in m.notes)
    version = m.version_hash or "candidate — not yet a recorded version"
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>onedoor coverage map</title>"
        f"<style>{root_css()}{_PAGE_CSS}</style></head><body>"
        "<h1>coverage map</h1>"
        f"<section class='citation-block'>"
        f"<h2>what this was computed from</h2>"
        f"<p class='citation'>policy version {_e(version)}</p>"
        f"<p class='citation'>{_e(m.cited.sentence())}</p></section>"
        f"<section class='effects-block'><h2>effects</h2>{_counts(m.effects, m)}"
        f"<ul>{_rows(m.effects, m)}</ul></section>"
        f"<section class='actions-block'><h2>action types</h2>{_counts(m.actions, m)}"
        f"<ul>{_rows(m.actions, m)}</ul></section>"
        f"<section class='notes-block'><h2>what this map does not measure</h2>"
        f"<ul class='notes'>{notes}</ul></section>"
        "</body></html>"
    )
