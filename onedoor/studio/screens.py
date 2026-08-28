"""The Studio's screens, rendered into the V1 shell.

Markup only. Everything shown here is resolved by a read model first — `library.build`
for S1 — so this module never touches a database and never decides what a policy means.
That split is why the sentences on the detail page can be tested without a server and
why this file has no opinion to get wrong.
"""

from __future__ import annotations

from html import escape

from onedoor.guardrail.models import Policy
from onedoor.studio import coverage as coverage_model
from onedoor.studio import library, shell

COVERAGE_WORDS = {
    coverage_model.COVERED: ("covered", "the ledger has seen this action"),
    coverage_model.DECLARED_INERT: (
        "declared, inert",
        "declared here and never reached — a rule its author believes is governing",
    ),
    coverage_model.UNCOVERED_OBSERVED: (
        "seen, undeclared",
        "the ledger has seen this action and no rule declares it; it is being refused",
    ),
    coverage_model.UNREACHED: ("unreached", "declared and not yet seen in the ledger"),
}
"""Coverage state as a word and a reason, never as a colour.

The badge follows the same law the chips do — see `shell.chip`. `declared_inert` is
first in `coverage.PROMINENCE` because it *sounds* fine and *behaves* dangerously, and a
badge that only carried a hue would lose exactly that.
"""


def css() -> str:
    """The Studio's one stylesheet.

    Screens do not carry their own. A per-screen sheet has to be *remembered* by every
    route that renders that screen, and the failure mode when it is forgotten is a page
    that renders unstyled rather than one that errors — a silent break, discovered by a
    human looking at it. `shell.render` emits this and there is nothing else to pass.
    """
    return shell.css()


def _inline(text: str) -> str:
    """Escape first, then allow the two marks the sentences use.

    Order is the whole security property: escaping after substitution would let a
    policy's own `action_type` close a tag. Action types come from a store the Studio
    opens by filename, so they are attacker-shaped by the same argument as params.
    """
    out = escape(text)
    for mark, tag in (("`", "code"), ("**", "strong")):
        parts = out.split(mark)
        out = "".join(
            part if i % 2 == 0 else f"<{tag}>{part}</{tag}>" for i, part in enumerate(parts)
        )
    return out


def _badge(state: str) -> str:
    word, why = COVERAGE_WORDS.get(state, (state, ""))
    return f'<span class="badge" title="{escape(why)}">{escape(word)}</span>'


def library_body(model: library.Library) -> str:
    """S1: the library page."""
    head = f'<h2>Policies</h2><div class="rulebar"></div><p class="lede">{escape(library.ABSENCE_IS_DENIAL)}</p>'

    if model.version is None:
        return head + f'<div class="empty">{escape(library.NO_VERSION)}</div>'
    if not model.retrievable:
        return head + (
            '<div class="empty">A version is in force and its snapshot is not '
            "retrievable from this store, so the rules behind it cannot be shown. "
            "<strong>This is not an empty policy set</strong> — the engine is deciding "
            "against rules this page cannot read.</div>"
        )
    if not model.rows:
        return head + (
            '<div class="empty">This version is in force and declares no policies. '
            "Every action meets the default, and the default is denial.</div>"
        )

    rows = []
    for row in model.rows:
        href = f"/policies/{row.action_type}"
        rows.append(
            "<tr>"
            f'<td><a href="{escape(href)}">{escape(row.action_type)}</a></td>'
            f"<td>{shell.chip(row.state)}</td>"
            f'<td class="tier">{escape(row.tier.name)}</td>'
            f'<td class="mono">{escape(row.caps) or "—"}</td>'
            f"<td>{escape(row.bounds) or '—'}</td>"
            f"<td>{escape(', '.join(row.effects)) or '—'}</td>"
            f"<td>{_badge(row.coverage)}</td>"
            "</tr>"
        )
    return head + (
        '<div class="panel"><table><thead><tr>'
        "<th>Action</th><th>Decision</th><th>Tier</th><th>Caps</th>"
        "<th>Bounds</th><th>Effects</th><th>Coverage</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def policy_body(policy: Policy, model: library.Library) -> str:
    """S1 detail: what the rule does, beside what it says.

    Two panes, labelled as **different kinds of claim**. The left is derived from the
    policy by `library.sentences`; the right is the rule itself. Neither is a
    description an operator wrote — those are S6's, frozen as received bytes, and
    presenting one as the other is the conflation the asserted/measured split exists to
    prevent.
    """
    said = "".join(f"<p>{_inline(s)}</p>" for s in library.sentences(policy))
    return (
        f'<h2>{escape(policy.action_type)}</h2><div class="rulebar"></div>'
        f'<p class="lede">Part of the version in force, '
        f"{shell.digest_html(model.version)}.</p>"
        '<div class="cols">'
        f'<div class="panel"><h3>What this rule does</h3>'
        f'<div class="plain">{said}</div></div>'
        f'<div class="panel"><h3>The rule</h3><pre>{escape(library.yaml_text(policy))}</pre>'
        "</div>"
        "</div>"
        f'<p class="lede">{escape(library.ABSENCE_IS_DENIAL)}</p>'
    )


def not_found_body(action_type: str) -> str:
    """A named absence, not a bare 404 — the version in force may simply not have it."""
    return (
        f'<h2>{escape(action_type)}</h2><div class="rulebar"></div>'
        f'<div class="empty">No policy for <code>{escape(action_type)}</code> exists in '
        "the version currently in force, so this action is denied. It may have existed "
        "in an earlier version; this page shows only what is deployed now.</div>"
    )
