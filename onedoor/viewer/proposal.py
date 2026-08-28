"""The proposal surface (ND-052 / S6-T5): one page, two sections, never one table.

R053 §3. The coverage map's rows are **measurements** — facts about the engine and the
ledger. The proposal's mentioned-but-unruled rows are **a model's reading of a sentence**.
Both belong in front of the operator; neither belongs in the other's table.

Merging them would not produce one honest list. It would produce one dishonest list,
because **a list is honest only if every row carries the same kind of warrant.** So the
two-places-to-look cost that principle 4 rightly worries about is paid in *rendering* —
one surface, scroll once — rather than in schema.

The second section states its warrant on its face, and every row in it **cites the
coverage state it was checked against**, with the map's citation carried alongside. A
claim that says which measurement it was checked against is a claim a reader can go and
check; one that does not is a claim asking to be believed.
"""

from __future__ import annotations

from html import escape
from typing import Any

from onedoor.studio import coverage as coverage_model
from onedoor.studio import proposer as proposer_model
from onedoor.viewer.coverage import STATE_COLOUR_VARS, STATE_LABEL
from onedoor.viewer.tokens import root_css

MEASURED_WARRANT = (
    "Measured: computed from the policy set and the ledger over the cited range. "
    "These rows are facts about what is declared and what arrived."
)

ASSERTED_WARRANT = (
    "A model's reading of the description — NOT a measurement. These rows say what a "
    "proposer thought the description referred to. Each cites the coverage state it was "
    "checked against, so the claim can be checked rather than believed."
)

__all__ = ["ASSERTED_WARRANT", "MEASURED_WARRANT", "STATE_COLOUR_VARS", "render_page"]


def _e(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _measured(m: coverage_model.CoverageMap) -> str:
    rows = "".join(
        f"<li class='row {_e(row.state)}'>"
        f"<span class='state'>{_e(STATE_LABEL[row.state])}</span>"
        f"<span class='name'>{_e(row.name)}</span></li>"
        for row in m.ranked(m.effects)
    )
    return (
        "<section class='" + proposer_model.MEASURED + "'>"
        "<h2>coverage — measured</h2>"
        f"<p class='warrant'>{_e(MEASURED_WARRANT)}</p>"
        f"<p class='citation'>{_e(m.cited.sentence())}</p>"
        f"<ul>{rows or '<li class=row>nothing declared</li>'}</ul>"
        "</section>"
    )


def _asserted(mentions: list[proposer_model.Mention], citation: dict[str, Any]) -> str:
    """The dark-surface list. Every row cites what it was checked against."""
    rows = []
    for mention in mentions:
        state = mention.covered_by
        checked = (
            f"covered by <span class='name'>{_e(state)}</span>"
            if state
            else "<span class='uncovered'>no rule covers it</span>"
        )
        rows.append(
            f"<li class='row {proposer_model.ASSERTED}'>"
            f"<span class='state'>MENTIONED · {_e(mention.kind)}</span>"
            f"<span class='name'>{_e(mention.subject)}</span>"
            f"<p class='quote'>&ldquo;{_e(mention.quote)}&rdquo;</p>"
            f"<p class='checked'>{checked}</p></li>"
        )
    return (
        "<section class='" + proposer_model.ASSERTED + "'>"
        "<h2>mentioned in the description — asserted</h2>"
        f"<p class='warrant'>{_e(ASSERTED_WARRANT)}</p>"
        f"<p class='citation'>checked against coverage citation "
        f"{_e(citation.get('version_hash'))} · range "
        f"{_e((citation.get('range') or {}).get('row_hash_at_last_seq'))}</p>"
        f"<ul>{''.join(rows) or '<li class=row>the description mentioned nothing recognised</li>'}</ul>"
        "</section>"
    )


def _record(sealed: dict[str, Any]) -> str:
    """The derivation record's face — both sentences, always."""
    instrument = sealed.get("instrument", {})
    lines = "".join(
        f"<dt>{_e(k)}</dt><dd class='mono'>{_e(v)}</dd>" for k, v in sorted(instrument.items())
    )
    return (
        "<section class='record'>"
        "<h2>derivation record</h2>"
        f"<p class='provenance'>proposer_provenance: "
        f"<b>{_e(sealed.get('proposer_provenance'))}</b></p>"
        f"<dl class='instrument'>{lines}</dl>"
        f"<p class='face'>{_e(proposer_model.NOT_REDERIVABLE)}</p>"
        f"<p class='face'>{_e(proposer_model.AUTHORITY_FROM_CHECKS)}</p>"
        f"<p class='mono digest'>{_e(sealed.get('record_digest'))}</p>"
        "</section>"
    )


_PAGE_CSS = """
body{background:var(--ground);color:var(--ink);font-family:'Archivo',system-ui,sans-serif;
margin:0;padding:2rem;}
h1{color:var(--seal);font-size:1.1rem;letter-spacing:.08em;text-transform:uppercase;}
h2{font-size:.85rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}
section{background:var(--card);border:1px solid var(--border);border-radius:6px;
padding:1rem 1.25rem;margin:1rem 0;}
/* The two sections are visibly different KINDS, not two lists that happen to be apart:
   the asserted one is inset and marked, so a reader cannot mistake a claim for a
   measurement by scrolling past a heading. Marked by POSITION and SURFACE, not by the
   brand accent (R056 §4): asserted-vs-measured is a classification a reader must not
   confuse, which is precisely the job gold must not be given. */
section.asserted{border-left:3px solid var(--ink);background:var(--surface);}
.warrant{color:var(--muted);font-size:.8rem;border-bottom:1px solid var(--border-soft);
padding-bottom:.6rem;}
.citation,.digest{color:var(--faint);font-size:.75rem;word-break:break-all;}
.mono,.name{font-family:'IBM Plex Mono',ui-monospace,monospace;}
ul{list-style:none;padding:0;}
.row{border-left:2px solid var(--border-soft);padding:.5rem .8rem;margin:.4rem 0;}
.row .state{display:block;font-size:.65rem;letter-spacing:.1em;color:var(--faint);}
.row.declared_inert{border-left:3px solid var(--ink);background:var(--card-hi);}
.row.declared_inert .name{font-weight:700;}
.row.unreached{opacity:.75;}
.row.unreached .name{font-style:italic;color:var(--muted);}
.row.covered{opacity:.55;}
.quote{color:var(--muted);font-size:.8rem;font-style:italic;margin:.3rem 0 0;}
.checked{font-size:.75rem;color:var(--faint);margin:.2rem 0 0;}
.uncovered{color:var(--ink);font-weight:600;}
.face{color:var(--muted);font-size:.8rem;border-top:1px solid var(--border-soft);
padding-top:.6rem;}
.instrument dt{color:var(--faint);font-size:.7rem;text-transform:uppercase;}
.instrument dd{margin:0 0 .4rem;font-size:.8rem;word-break:break-all;}
.provenance b{color:var(--seal);}
"""


def render_page(
    m: coverage_model.CoverageMap,
    mentions: list[proposer_model.Mention],
    sealed_record: dict[str, Any],
) -> str:
    """One surface: the derivation's face, the measured rows, then the asserted rows.

    No `--ok`/`--bad` anywhere — this page carries no verdicts, and the pair is spent
    everywhere or nowhere (R049 §3).
    """
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>onedoor policy proposal</title>"
        f"<style>{root_css()}{_PAGE_CSS}</style></head><body>"
        "<h1>policy proposal</h1>"
        f"{_record(sealed_record)}"
        f"{_measured(m)}"
        f"{_asserted(mentions, m.citation())}"
        "</body></html>"
    )
