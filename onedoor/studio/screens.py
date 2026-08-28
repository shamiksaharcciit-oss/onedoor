"""The Studio's screens, rendered into the V1 shell.

Markup only. Everything shown here is resolved by a read model first — `library.build`
for S1 — so this module never touches a database and never decides what a policy means.
That split is why the sentences on the detail page can be tested without a server and
why this file has no opinion to get wrong.
"""

from __future__ import annotations

from html import escape
from typing import Any

from onedoor.guardrail.models import Policy
from onedoor.studio import coverage as coverage_model
from onedoor.studio import history, library, shell

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


# --- V3 / S4: the execution ledger ------------------------------------------------------


def _filter_form(choices: dict[str, tuple[str, ...]], filters: history.Filters) -> str:
    """A GET form. No JavaScript, and the query string is the state.

    Filters in the URL mean an auditor can paste the address of what they were looking
    at into a report and have it mean the same thing tomorrow. A filter held in memory
    is a view nobody else can reach.
    """
    selects = []
    for name, label in (
        ("action", "Action"),
        ("verdict", "Verdict"),
        ("version", "Policy version"),
        ("source", "Request origin"),
    ):
        options = [f'<option value="">{escape(label)}: any</option>']
        current = getattr(filters, name)
        available = choices.get(name, ())
        if current and current not in available:
            # The page IS filtered by this value, so the form must say so. A bookmarked
            # filter whose rows have aged out would otherwise render as "any" over an
            # empty register — the control claiming no filter is applied while one is,
            # so the emptiness reads as "no such decisions ever" instead of "none match".
            # **A form that does not echo what it filtered on is a page lying quietly.**
            shown = shell.short_digest(current) if name == "version" else current
            options.append(
                f'<option value="{escape(current)}" selected>'
                f"{escape(shown)} — not in this ledger</option>"
            )
        for value in available:
            shown = shell.short_digest(value) if name == "version" else value
            selected = " selected" if value == current else ""
            options.append(f'<option value="{escape(value)}"{selected}>{escape(shown)}</option>')
        selects.append(f'<select name="{name}">{"".join(options)}</select>')
    return (
        '<form class="filters" method="get" action="/history">'
        + "".join(selects)
        + f'<input type="date" name="since" value="{escape(filters.since)}" '
        'aria-label="From date">'
        + f'<input type="date" name="until" value="{escape(filters.until)}" '
        'aria-label="To date">'
        '<button type="submit">Filter</button>'
        '<a class="clear" href="/history">Clear</a>'
        "</form>"
        f'<p class="note">{escape(history.MISSING_ACTOR_FILTER)}</p>'
    )


def history_body(page: history.Page, choices: dict[str, tuple[str, ...]]) -> str:
    """S4: the register."""
    head = '<h2>History</h2><div class="rulebar"></div>' + _filter_form(choices, page.filters)

    if not page.entries:
        asked = page.filters.active()
        why = (
            "No decision in this ledger matches those filters."
            if asked
            else "This ledger holds no decisions yet. Run one through the engine and it "
            "will appear here."
        )
        return head + f'<div class="empty">{escape(why)}</div>'

    rows = []
    for e in page.entries:
        rows.append(
            "<tr>"
            f'<td class="mono num">{escape(e.number)}</td>'
            f'<td class="mono">{escape(e.created_at)}</td>'
            f'<td><a href="/history/{e.row_id}">{escape(e.action_type)}</a></td>'
            f"<td>{shell.chip(e.state, e.decision)}</td>"
            f'<td class="mono">{escape(e.reason_code)}</td>'
            f"<td>{shell.digest_html(e.policy_version)}</td>"
            f'<td class="tier">{escape(e.source)}</td>'
            "</tr>"
        )
    shown = (
        f"Showing the {len(page.entries)} most recent of <strong>{page.total}</strong> "
        f"matching decisions."
        if page.truncated
        else f"<strong>{page.total}</strong> matching decision" + ("s." if page.total != 1 else ".")
    )
    return head + (
        f'<p class="note">{shown}</p>'
        '<div class="panel"><table><thead><tr>'
        "<th>Entry</th><th>When</th><th>Action</th><th>Verdict</th>"
        "<th>Rule path</th><th>Policy version</th><th>Origin</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def entry_body(row: Any) -> str:
    """One decision in full: what was asked, what decided, and what sealed it."""
    seq = row["seq"]
    number = f"#{seq}" if seq is not None else "unchained"
    decision = str(row["decision"] or "")
    state = history.DECISION_STATE.get(decision, "review")

    facts = [
        ("Entry", escape(number)),
        ("When", escape(str(row["created_at"] or ""))),
        ("Action", escape(str(row["action_type"] or ""))),
        ("Verdict", shell.chip(state, decision)),
        ("Rule path", escape(str(row["reason_code"] or ""))),
        ("Detail", escape(str(row["detail"] or "")) or "—"),
        ("Policy version", shell.digest_html(row["policy_version"])),
        ("Request origin", escape(str(row["source"] or ""))),
        ("Request id", escape(str(row["request_id"] or ""))),
    ]
    outcome = row["outcome"]
    facts.append(
        # ND-039/A4b: the PEP's report is a SEPARATE vocabulary from the PDP's verdict,
        # and `not_attempted` is a real outcome. Absent means the enforcement point has
        # not reported yet -- which is not the same as nothing having happened.
        ("Reported outcome", escape(str(outcome)) if outcome else "not reported")
    )
    kv = "".join(f"<dt>{escape(k)}</dt><dd>{v}</dd>" for k, v in facts)

    digests = "".join(
        f'<dt title="{escape(why)}">{escape(label)}</dt><dd>{shell.digest_html(row[column])}</dd>'
        for column, label, why in history.DIGEST_LABELS
    )
    chain = "".join(
        f"<dt>{escape(label)}</dt><dd>"
        + (
            escape(str(row[column]))
            if column == "seq" and row[column] is not None
            else shell.digest_html(row[column])
        )
        + "</dd>"
        for column, label in history.CHAIN_LABELS
    )

    params = str(row["params_json"] or "")
    provenance = row["params_provenance"]
    return (
        f'<h2>{escape(str(row["action_type"] or ""))} <span class="num">{escape(number)}</span></h2>'
        '<div class="rulebar"></div>'
        f'<div class="panel"><h3>The decision</h3><dl class="kv">{kv}</dl></div>'
        '<div class="cols">'
        f'<div class="panel"><h3>What was asked</h3><pre>{escape(params)}</pre>'
        f'<p class="note">Frozen as received'
        + (f", provenance <code>{escape(str(provenance))}</code>" if provenance else "")
        + ". These are the caller's bytes and are shown without normalisation.</p></div>"
        f'<div class="panel"><h3>Digests</h3><dl class="kv">{digests}</dl>'
        f'<h3>Chain</h3><dl class="kv">{chain}</dl></div>'
        "</div>"
        '<p class="note">This page shows what was recorded. It does not re-verify the '
        "chain — that is what the Verify page will do, against the receipt rather than "
        "against this rendering.</p>"
    )
