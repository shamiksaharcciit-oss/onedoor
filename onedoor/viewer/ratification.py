"""Render a ratification receipt (ND-052 / S2-T5).

Like `onedoor.viewer.page`, this module **renders an answer it was given**. It does no
store reads and no digest arithmetic: `studio.ratify.view_model` dereferences the cited
backtest, and `studio.ratify.verify_files` decides whether a receipt checks out. Two
implementations of "is this sound?" eventually disagree, and the one the user sees is
the one that is wrong.

Two disciplines, both from R045 §4, and both held by a test rather than by care
---------------------------------------------------------------------------------
**Absence is rendered, not merely null.** A ratification with no backtest says so on its
face, in every view. Not by omitting a line — an omitted line reads as "nothing to
report", and the whole point is that there *is* something to report.

**A cited backtest surfaces its `ledger_provenance` by dereferencing.** A
fixture-informed ratification is legitimate and must be visible as one; a receipt that
showed only a digest would let a demo-backed decision read as a production-backed one,
which is the overclaim S1's label discipline exists to prevent.

`RENDERERS` closes the set. `tests/viewer/test_ratification.py` asserts that every
public `render_*` in this module is in it, and runs both disciplines against every
member — so a third rendering added later joins the tests at the moment it is written
rather than at the moment someone notices.
"""

from __future__ import annotations

from html import escape

from onedoor.studio.ratify import RatificationView

NO_BACKTEST_SENTENCE = "No backtest informed this ratification."
"""The exact words, referenced by both renderers and by the tests that hold them.

One constant rather than two strings that happen to agree: *a regression must compare
against the fact itself, never against a second name for the fact* (R045 §1), and two
copies of a sentence are exactly two names for one fact.
"""


def _short(version: str | None) -> str:
    return "none — first ratification on this store" if version is None else version


def _change_words(view: RatificationView) -> str:
    parts = []
    if view.changes.added:
        parts.append(f"added {', '.join(sorted(view.changes.added))}")
    if view.changes.modified:
        parts.append(f"modified {', '.join(sorted(view.changes.modified))}")
    return "; ".join(parts) if parts else "no rule changed"


def _backtest_sentence(view: RatificationView) -> str:
    """One sentence covering all three states a citation can be in.

    Absent, unresolvable and resolved are held apart here exactly as they are in the
    ceremony: a citation that does not resolve is **not** rendered as no citation.
    """
    cited = view.backtest
    if cited is None:
        return NO_BACKTEST_SENTENCE
    if cited.provenance is None:
        return (
            f"Backtest {cited.digest[:12]}... is cited but does not resolve in this "
            "store, so its ledger provenance is unknown."
        )
    return (
        f"Backtest {cited.digest[:12]}... informed this ratification, run against a "
        f"{cited.provenance} ledger."
    )


def render_text(view: RatificationView) -> str:
    """Plain text, for a terminal or a log line."""
    lines = [
        f"ratification {view.digest[:12]}...",
        f"  from   {_short(view.from_version)}",
        f"  to     {view.to_version}",
        f"  change {_change_words(view)}",
        f"  session {view.ratified_by_session} (declared, not authenticated)",
        f"  at     {view.ratified_at}",
        f"  kill switch {'ENGAGED' if view.kill_switch_engaged else 'not engaged'} at ratification",
        f"  {_backtest_sentence(view)}",
    ]
    return "\n".join(lines)


def render_html(view: RatificationView) -> str:
    """An HTML fragment, for the viewer page. Every value escaped (stored-XSS, ND-051)."""

    def e(value: object) -> str:
        return escape("" if value is None else str(value), quote=True)

    switch = "ENGAGED" if view.kill_switch_engaged else "not engaged"
    return (
        '<section class="ratification">'
        f"<h2>Ratification {e(view.digest[:12])}…</h2>"
        f'<dl><dt>from</dt><dd class="hash">{e(_short(view.from_version))}</dd>'
        f'<dt>to</dt><dd class="hash">{e(view.to_version)}</dd>'
        f"<dt>change</dt><dd>{e(_change_words(view))}</dd>"
        f"<dt>session</dt><dd>{e(view.ratified_by_session)} "
        "<span>(declared, not authenticated)</span></dd>"
        f"<dt>at</dt><dd>{e(view.ratified_at)}</dd>"
        f"<dt>kill switch</dt><dd>{e(switch)} at ratification</dd></dl>"
        f'<p class="backtest">{e(_backtest_sentence(view))}</p>'
        "</section>"
    )


RENDERERS = (render_text, render_html)
"""Every rendering of a ratification. Held closed by a test, not by convention."""
