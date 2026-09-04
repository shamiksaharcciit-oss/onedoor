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
from onedoor.studio import (
    canvas,
    drafts,
    editor,
    forecast,
    history,
    library,
    live,
    live_proposer,
    proposer,
    reevaluate,
    shell,
    staging,
    validate,
    verify,
)
from onedoor.studio import coverage as coverage_model
from onedoor.viewer import canvas as canvas_skin

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


def policy_body(
    policy: Policy, model: library.Library, words: library.FrozenWords | None = None
) -> str:
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
        "</div>" + _frozen_voice(words) + f'<p class="lede">{escape(library.ABSENCE_IS_DENIAL)}</p>'
    )


def _frozen_voice(words: library.FrozenWords | None) -> str:
    """The operator's own words, quoted and attributed — never merged (R058 §6).

    A third block rather than a third column, and styled as a quotation, because the
    two are **different kinds of claim**: the panes above say what the rule *does*,
    derived from the policy; this says what someone *said it was for*, frozen as
    received bytes. *The screen's value is exactly the gap between them; the layout must
    make disagreement visible, not smooth.*

    Omitted entirely when nothing links. An empty quotation would read as an operator
    who wrote nothing, which is a different fact from a rule never proposed through the
    Studio.
    """
    if words is None:
        return ""
    if words.quotes:
        body = "".join(f"<blockquote>{escape(q)}</blockquote>" for q in words.quotes)
    else:
        body = (
            '<p class="plain">The description this rule was derived from does not '
            "mention it. The rule came with the proposal; these words did not describe "
            "it.</p>"
        )
    return (
        '<div class="panel voice"><h3>What the operator said it was for</h3>'
        + body
        + '<p class="note">Frozen as written and quoted verbatim — an operator’s '
        "words, not the engine’s. Nothing above is derived from this, and nothing "
        "here is checked against the rule; the two are shown side by side so a reader "
        "can see where they differ. Description "
        + shell.digest_html(words.description_digest)
        + ".</p></div>"
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

    # R089 F-H1: these are receipt/chain digests, never policy versions — a null one
    # here is legitimate (ND-017 is unimplemented) and must not read `NOTHING_IN_FORCE`,
    # which is a sentence about a version, on a page whose header already shows one IS
    # in force. `shell.NOT_RECORDED` is the honest word for this null.
    digests = "".join(
        f'<dt title="{escape(why)}">{escape(label)}</dt>'
        f"<dd>{shell.digest_html(row[column], absent_label=shell.NOT_RECORDED)}</dd>"
        for column, label, why in history.DIGEST_LABELS
    )
    chain = "".join(
        f"<dt>{escape(label)}</dt><dd>"
        + (
            # A present `seq` renders bare (unprefixed, matching this cell's own prior
            # behaviour); a null one is "unchained" -- the same word the heading above
            # already uses for this row, never `shell.NOT_RECORDED`: chaining is
            # opt-in/periodic (F-S2), a real state with a name, not a gap in what
            # ND-017 has built yet. The other three chain fields genuinely are that gap.
            escape(str(row[column]))
            if column == "seq" and row[column] is not None
            else escape(number)
            if column == "seq"
            else shell.digest_html(row[column], absent_label=shell.NOT_RECORDED)
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


# --- V4 / S5: the live room ---------------------------------------------------------


def _bar(bar: live.Bar) -> str:
    """One budget window. Numbers first; the bar is a second reading of them.

    An unbounded window draws no bar at all — a full bar and an empty bar both state a
    proportion, and there is no proportion when nothing declared a limit.
    """
    consumed, reserved, free, limit = bar.texts()
    label = (
        f'<div class="barhead"><span class="mono">{escape(bar.action_type)}</span> '
        f'<span class="tier">{escape(bar.unit)} / {escape(bar.window)}</span></div>'
    )
    figures = (
        f'<div class="figures mono">consumed <b>{escape(consumed)}</b> · '
        f"reserved <b>{escape(reserved)}</b> · free <b>{escape(free)}</b> · "
        f"limit <b>{escape(limit)}</b></div>"
    )
    if bar.unbounded:
        return (
            f'<div class="bar-row">{label}{figures}'
            '<p class="note">No cap is declared for this window, so nothing here is a '
            "proportion of anything. The counter is shown; no bar is drawn.</p></div>"
        )
    used = bar.pct(bar.consumed)
    held = bar.pct(bar.reserved)
    return (
        f'<div class="bar-row">{label}{figures}'
        f'<div class="bar" role="img" aria-label="consumed {escape(consumed)} of '
        f'{escape(limit)}, {escape(reserved)} reserved">'
        f'<i class="b-used" style="width:{used:.2f}%"></i>'
        f'<i class="b-res" style="width:{held:.2f}%"></i>'
        "</div></div>"
    )


def live_body(model: live.LiveState) -> str:
    """S5: budgets, reservations, approvals, and the switch this Studio cannot throw."""
    state = "refuse" if model.engaged else "allow"
    word = "engaged" if model.engaged else "not engaged"
    since = (
        f"Engaged {escape(model.engaged_since or '')}"
        + (f" by {escape(model.engaged_origin or '')}" if model.engaged_origin else "")
        + (
            f", policy version {shell.digest_html(model.version_at_engagement)}"
            if model.version_at_engagement
            else ""
        )
        + "."
        if model.engaged
        else ""
    )
    switch = (
        '<div class="panel kswitch"><h3>Kill switch</h3>'
        f"<p>{shell.chip(state, word)} {since}</p>"
        f'<p class="plain">{escape(live.RANK)}</p>'
        f'<p class="plain">{escape(live.DOES_NOT_STOP)}</p>'
        f'<p class="note">{escape(live.NO_CONTROL)}</p></div>'
    )

    if model.bars:
        bars = "".join(_bar(b) for b in model.bars)
        budgets = (
            '<div class="panel"><h3>Budgets</h3>'
            '<p class="legend"><i class="b-used"></i>consumed '
            '<i class="b-res"></i>reserved, not yet settled '
            "<i></i>free</p>" + bars + "</div>"
        )
    else:
        budgets = (
            '<div class="panel"><h3>Budgets</h3><div class="empty">No policy in force '
            "declares a cap, and no counter has been written. Nothing is being metered."
            "</div></div>"
        )

    if model.reservations:
        rows = []
        for r in model.reservations:
            age = r.age_seconds(model.now)
            overdue = r.overdue(model.now)
            # Three outcomes: within deadline, past it, and unreadable. "Unknown" is not
            # "fine" -- a screen that answers a question it could not evaluate is worse
            # than one that says it could not.
            flag = (
                '<span class="chip c-review">past deadline</span>'
                if overdue is True
                else "held"
                if overdue is False
                else '<span class="chip c-review">deadline unreadable</span>'
            )
            rows.append(
                "<tr>"
                f'<td class="mono">{escape(str(r.intent_audit_id))}</td>'
                f'<td class="mono">{escape(r.request_id)}</td>'
                f'<td class="mono">{"—" if age is None else escape(str(age)) + "s"}</td>'
                f'<td class="mono">{escape(r.deadline)}</td>'
                f"<td>{flag}</td>"
                f'<td class="mono">'
                + escape(", ".join(f"{a} {k} {amount}" for a, k, amount in r.deltas) or "—")
                + "</td></tr>"
            )
        reservations = (
            '<div class="panel"><h3>Open reservations</h3><table><thead><tr>'
            "<th>Intent</th><th>Request</th><th>Age</th><th>Deadline</th>"
            "<th>State</th><th>Holding</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )
    else:
        reservations = (
            '<div class="panel"><h3>Open reservations</h3><div class="empty">Nothing is '
            "held. Every reservation has settled, released or been reclaimed.</div></div>"
        )

    if model.approvals:
        rows = []
        for a in model.approvals:
            chip = {"approved": "allow", "denied": "refuse", "expired": "refuse"}.get(
                a.state, "review"
            )
            rows.append(
                "<tr>"
                f'<td class="mono">{escape(str(a.approval_id))}</td>'
                f'<td class="mono">{escape(a.action_type)}</td>'
                f"<td>{shell.chip(chip, a.state)}</td>"
                f'<td class="mono">{escape(a.created_at)}</td>'
                f'<td class="mono">{escape(a.expires_at or "—")}</td>'
                f'<td class="mono">{escape(a.decided_at or "—")}</td>'
                f'<td class="mono">{escape(a.decided_by_session or "—")}</td>'
                "</tr>"
            )
        approvals = (
            '<div class="panel"><h3>Approval lifecycles</h3><table><thead><tr>'
            "<th>#</th><th>Action</th><th>State</th><th>Raised</th><th>Expires</th>"
            "<th>Decided</th><th>By session</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )
    else:
        approvals = (
            '<div class="panel"><h3>Approval lifecycles</h3><div class="empty">No action '
            "has ever needed a human decision in this store.</div></div>"
        )

    return (
        '<h2>Live state</h2><div class="rulebar"></div>'
        + switch
        + budgets
        + reservations
        + approvals
        + '<p class="note">This page reads the enforcer store and changes nothing in it. '
        "Every number is as of the moment the page was built.</p>"
    )


# --- V5 / S3: drafts, and the ceremony ----------------------------------------------


def _honesty_footnote() -> str:
    """`validate.INCOMPLETE_NOTICE`, VERBATIM (R055 V5).

    Interpolated from the constant rather than retyped, so the page and the validator
    cannot drift apart. The design note calls this a feature: *honest limits are part of
    the brand.*
    """
    return f'<p class="note honesty">{escape(validate.INCOMPLETE_NOTICE)}</p>'


def drafts_body(
    listing: list[Any],
    active_version: str | None,
    active_policies: int | None = None,
    *,
    db_defaulted: bool = True,
) -> str:
    """S3 index: the drafts, and the form that makes one.

    Carries F-H's empty-store warning, which shipped in `0.6.2` on the old `/` page.
    When V5 moved Drafts to `/drafts` the warning stayed behind on a page nothing linked
    to — **a shipped fix quietly stranded by a redesign.** Caught by V8's universal pass;
    it lives here now, on the page the operator actually reaches.

    `db_defaulted` picks which warning has standing (R086 §2D). It defaults to `True`
    because that wording carries the extra hypothesis, and a caller that did not say
    should be offered the possibility rather than have it silently withdrawn.
    """
    head = '<h2>Drafts</h2><div class="rulebar"></div>'
    if active_policies == 0:
        warning = canvas_skin.store_warning(db_defaulted=db_defaulted)
        head += f'<div class="empty store-warning">{escape(warning)}</div>'
    create = (
        '<div class="panel create-block"><h3>New draft</h3>'
        '<form method="post" action="/drafts">'
        '<input name="title" placeholder="what this draft is for" aria-label="Draft title">'
        '<button type="submit">Open a draft</button></form>'
        '<p class="note">A draft is pinned to the version in force when it is opened, '
        "and edits nothing until it is ratified.</p>"
        # F-G shipped this in 0.6.2 and V5 left it behind on the old page, the same way
        # it stranded F-H's warning. An affordance discoverable only by the lost is
        # worth keeping discoverable.
        '<p class="note">or, from a terminal:</p>'
        "<pre>curl -X POST 'http://127.0.0.1:8787/drafts' "
        "--data-urlencode 'title=what this draft changes'</pre></div>"
    ) + upload_block()
    if not listing:
        return (
            head + create + '<div class="empty">No drafts yet. A draft is where rules are written; '
            "the live rules are never edited directly.</div>"
        )
    rows = []
    for d in listing:
        moved = d.base_version != active_version
        pin = (
            '<span class="chip c-review">base moved</span>'
            if moved
            else '<span class="chip c-allow">current</span>'
        )
        rows.append(
            "<tr>"
            f'<td><a href="/drafts/{escape(d.draft_id)}">{escape(d.title)}</a></td>'
            f"<td>{shell.digest_html(d.base_version)}</td>"
            f"<td>{pin}</td>"
            f'<td class="mono">{escape(str(len(d.policies)))}</td>'
            "</tr>"
        )
    table = (
        '<div class="panel"><table><thead><tr><th>Draft</th><th>Pinned base</th>'
        "<th>Pin</th><th>Rules</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )
    return head + create + table


PREVIEW_UNAVAILABLE = (
    "This draft cannot be previewed: it would be refused at load. See the refusals below."
)
"""R088 §1/§2 (F-U1). `ratify.preview` shares `_apply` with real ratification by design
— *"the two cannot diverge in what they apply or in the order they apply it"* — so a
candidate the loader refuses is refused identically by both, and the fix is not making
preview permissive. The Changes panel used to have no way to say that and crashed the
whole page reaching for a hash `_apply` never produced; now it defers to the Validation
panel, which already renders this exact refusal (`validate.problems` runs the same
`validate_policy` check, one rule at a time, and collects rather than raises)."""


def _diff_block(view: drafts.DraftView) -> str:
    refusal = view.preview_refusal
    if refusal is not None:
        return (
            f'<div class="panel"><h3>Changes</h3><div class="empty">'
            f"{escape(PREVIEW_UNAVAILABLE)}</div></div>"
        )
    if not view.diffs:
        return (
            '<div class="panel"><h3>Changes</h3><div class="empty">This draft matches '
            "the version in force. Ratifying it would change nothing.</div></div>"
        )
    rows = []
    for d in view.diffs:
        was = "\u2014" if d.was is None else escape(" ".join(library.sentences(d.was)))
        becomes = "\u2014" if d.becomes is None else escape(" ".join(library.sentences(d.becomes)))
        rows.append(
            f'<div class="diff"><div class="barhead">'
            f'<span class="mono">{escape(d.action_type)}</span>'
            f'<span class="tier">{escape(d.kind)}</span></div>'
            f'<div class="was"><b>was</b> {was}</div>'
            f'<div class="becomes"><b>would become</b> {becomes}</div></div>'
        )
    return '<div class="panel"><h3>Changes</h3>' + "".join(rows) + "</div>"


def _problems_block(view: drafts.DraftView) -> str:
    found = view.problems
    if not found:
        body = '<div class="empty">The validator found no problems in these rules.</div>'
    else:
        items = "".join(
            f'<li><span class="mono">{escape(getattr(p, "action_type", "") or "")}</span> '
            f"{escape(getattr(p, 'message', str(p)))}</li>"
            for p in found
        )
        body = f'<ul class="problems">{items}</ul>'
    return f'<div class="panel"><h3>Validation</h3>{body}{_honesty_footnote()}</div>'


def _backtest_block(view: drafts.DraftView) -> str:
    panels = view.view.panels
    if panels is None:
        return ""
    divergence = panels.divergence
    if divergence.state == canvas.BACKTEST_NOT_REQUESTED:
        return (
            '<div class="panel"><h3>Backtest</h3><div class="empty">Not run. '
            '<a href="?backtest=1">Replay this ledger against the draft</a>.</div>'
            f'<p class="note">{escape(drafts.BACKTEST_IS_ABOUT_THE_PAST)}</p></div>'
        )
    if divergence.state == canvas.BACKTEST_REFUSED:
        return (
            '<div class="panel"><h3>Backtest</h3>'
            f'<div class="empty">The replay refused: '
            f"{escape(str(divergence.refusal or ''))}. No numbers are shown, because "
            "there are none to show.</div></div>"
        )
    receipt = divergence.receipt
    if receipt is None:
        # The state says the replay ran and no receipt came back. mypy found this
        # fourth case; it is not "no divergence" and it is not a refusal, so it gets
        # its own words. **Unverifiable and malformed are failures to surface, never
        # skips** -- and a backtest panel that rendered zeroes here would report a
        # clean replay that never happened.
        return (
            '<div class="panel"><h3>Backtest</h3><div class="empty">The replay reports '
            "that it ran and carries no receipt. No numbers are shown: this is a "
            "malformed result, not a clean one.</div></div>"
        )
    counts = receipt.divergence
    flips = []
    for key, count in sorted(counts.flips.items()):
        sentence, widening = drafts.flip_sentence(key)
        chip = shell.chip("review" if widening else "allow", sentence)
        flips.append(f'<li>{chip} <span class="mono">{escape(str(count))}</span></li>')
    flip_list = (
        f'<ul class="flips">{"".join(flips)}</ul>'
        if flips
        else '<p class="plain">No recorded decision changes verdict under these rules.</p>'
    )
    skipped = (
        f' <span class="tier">{escape(str(len(receipt.skipped)))} skipped</span>'
        if receipt.skipped
        else ""
    )
    return (
        '<div class="panel"><h3>Backtest</h3>'
        f'<p class="plain"><b>{escape(str(receipt.replayed))}</b> decisions replayed, '
        f"<b>{escape(str(sum(counts.flips.values())))}</b> changed verdict.{skipped}</p>"
        + flip_list
        + f'<p class="note">{escape(drafts.BACKTEST_IS_ABOUT_THE_PAST)}</p>'
        f'<p class="note">Receipt {shell.digest_html(receipt.policy_digest)}</p></div>'
    )


def draft_body(
    view: drafts.DraftView,
    derivation: dict[str, Any] | None = None,
    *,
    upload: staging.StagedResult | None = None,
) -> str:
    """S3 detail: the pin, the diff, the problems, the backtest, and the way to ratify.

    `derivation` is ND-056/T3's record, when a model drafted this. It is rendered as
    provenance BESIDE the rules, never as an endorsement of them: what the reader
    approves is the parsed rules, and the record says what produced them and what it
    does not attest.
    """
    pin = view.view.pin
    head = (
        f'<h2>{escape(view.draft.title)}</h2><div class="rulebar"></div>'
        f'<p class="lede">Pinned to {shell.digest_html(pin.base_version)}; '
        f"in force now {shell.digest_html(pin.active_version)}.</p>"
    )
    if view.stale:
        return head + (
            f'<div class="empty">{escape(drafts.STALE_BASE)}</div>'
            f'<form method="post" action="/drafts/{escape(view.draft.draft_id)}/repin">'
            '<button type="submit">Re-pin to the version in force</button></form>'
        )
    ceremony = (
        '<div class="panel"><h3>Ratify</h3>'
        f'<p class="plain">{escape(drafts.IRREVERSIBLE)}</p>'
        f'<p><a class="sealbtn" href="/drafts/{escape(view.draft.draft_id)}/ratify">'
        "Review and ratify</a></p></div>"
    )
    # Always rendered. `None` means "written by hand", which is a FACT about the draft
    # and not a reason to omit the panel -- omitting it would let a reader supply
    # whichever origin they expected.
    origin = derivation_block(derivation)
    return (
        head
        + _upload_block(upload)
        + origin
        + _rules_block(view)
        + _diff_block(view)
        + _problems_block(view)
        + _backtest_block(view)
        + ceremony
    )


UPLOAD_REFUSED_LEDE = (
    "This draft was created from an uploaded file, and the engine's loader would refuse "
    "it. Nothing was repaired and nothing was guessed: the draft holds whatever parsed, "
    "which is why it may be empty."
)

UPLOAD_CLEAN_LEDE = (
    "This draft was created from an uploaded file, and the loader accepted every stage it ran."
)


def _upload_block(result: staging.StagedResult | None) -> str:
    """What the loader made of an uploaded file, shown on the draft it produced.

    Rendered only when the page was reached from an upload, because a draft that was
    typed has no file to report on and an empty panel would invite the reader to
    conclude something about one.

    The refusals are re-staged from the frozen bytes at render time rather than carried
    across the redirect, so what is shown is derived from what the operator actually
    sent. Before this, every staged refusal was computed at upload time and discarded,
    and a file refused at stage 1 or 2 produced a page that said the rules were fine.
    """
    if result is None:
        return ""
    lede = UPLOAD_CLEAN_LEDE if result.loads else UPLOAD_REFUSED_LEDE
    return (
        f'<div class="panel"><h3>From the uploaded file</h3>'
        f'<p class="plain">{escape(lede)}</p></div>' + refusals_block(result)
    )


RULES_NONE = (
    "This draft holds no rules. Nothing is being proposed, so ratifying it would "
    "remove every rule currently in force."
)
"""What an empty draft says, because **absent is a state to render, never a blank.**

The sentence states the consequence rather than the count, because an operator reading
"0 rules" has been told a number and not what it means. An empty draft is a real and
occasionally correct thing to have; it is also the shape an upload takes when the
loader refused the file, and either way the reader should know what ratifying it does.
"""


def _rules_block(view: drafts.DraftView) -> str:
    """The draft's rules, each a link into the editor (R086 §2A, finding 6).

    **The editor had no door.** `GET /drafts/{id}/edit/{action_type}` was complete —
    both panes, live validation wired — and the only two `/edit/` references in the
    Studio were the form actions on the editor page itself. Nothing linked in, so the
    authoring surface was reachable only by typing a URL a stranger would have to read
    the source to construct. An operator walking the pass could not reach it, and no
    test noticed because every editor test addressed the route directly.

    Sorted by action type so the same draft renders the same list twice — a list that
    reshuffles between loads is a list nobody can cite a position in.
    """
    rules = sorted(view.draft.policies, key=lambda p: p.action_type)
    if not rules:
        return (
            '<div class="panel"><h3>Rules in this draft</h3>'
            f'<div class="empty">{escape(RULES_NONE)}</div></div>'
        )
    rows = "".join(
        "<tr>"
        f'<td><a href="/drafts/{escape(view.draft.draft_id)}/edit/'
        f'{escape(p.action_type)}">{escape(p.action_type)}</a></td>'
        f'<td class="tier">{escape(p.tier.name)}</td>'
        f"<td>{escape(', '.join(p.effects)) or '—'}</td>"
        "</tr>"
        for p in rules
    )
    return (
        '<div class="panel"><h3>Rules in this draft</h3>'
        f'<p class="note">{len(rules)} '
        f"{'rule' if len(rules) == 1 else 'rules'}. Open one to edit it; the rules in "
        "force are not touched by anything here.</p>"
        "<table><thead><tr><th>Action</th><th>Tier</th><th>Effects</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def ceremony_body(view: drafts.DraftView) -> str:
    """The ratify page: three true things and one deliberate confirm.

    Its gravity comes from the digest, the diff and the irreversibility stated — R060
    §5. Nothing here dramatizes beyond what the engine does: no countdown, no warning
    the engine cannot back, and no claim that the change is irreversible in a stronger
    sense than *the way back is forward*.
    """
    panels = view.view.panels
    if panels is None:
        return (
            '<h2>Ratify</h2><div class="rulebar"></div>'
            f'<div class="empty">{escape(drafts.STALE_BASE)}</div>'
        )
    preview = panels.preview
    if preview.refusal is not None:
        # Same fact `_diff_block` renders, on the one page where showing a Ratify
        # button would be worse than a crash: submitting it would still hit
        # `ratify.ratify`'s own `_apply` call, refused for the identical reason
        # (R088 §2 — preview and ratification cannot diverge). No confirm form here,
        # never a button that reads as live and 500s when pressed.
        return (
            f'<h2>Ratify {escape(view.draft.title)}</h2><div class="rulebar"></div>'
            f'<div class="empty">{escape(PREVIEW_UNAVAILABLE)}</div>' + _problems_block(view)
        )
    changed = len(view.diffs)
    # `to_version` is `None` exactly when `refusal` is not (ratify.Preview's own
    # invariant) — the branch above already returned on that case, so this one always
    # has a hash. Asserted rather than left for mypy to infer across two fields.
    assert preview.to_version is not None
    return (
        f'<h2>Ratify {escape(view.draft.title)}</h2><div class="rulebar"></div>'
        '<div class="panel"><h3>What will be in force</h3>'
        f'<div class="bigdigest">{escape(preview.to_version)}</div>'
        '<dl class="kv">'
        f"<dt>Replacing</dt><dd>{shell.digest_html(preview.from_version)}</dd>"
        f"<dt>Candidate</dt><dd>{shell.digest_html(preview.candidate_digest)}</dd>"
        f'<dt>Rules changed</dt><dd class="mono">{escape(str(changed))}</dd>'
        "</dl></div>"
        + _diff_block(view)
        + _problems_block(view)
        + '<div class="panel"><h3>Confirm</h3>'
        + f'<p class="plain">{escape(drafts.IRREVERSIBLE)}</p>'
        + f'<form method="post" action="/drafts/{escape(view.draft.draft_id)}/ratify">'
        + '<input name="session" required aria-label="Session note" '
        + 'placeholder="who is ratifying (recorded on the receipt)">'
        + '<button class="sealbtn" type="submit">Ratify</button></form>'
        + '<p class="note">The name given is recorded as <code>ratified_by_session</code> '
        + "on the receipt. It is what this store knows, not an authenticated identity.</p>"
        + "</div>"
    )


def receipt_body(outcome: Any, draft_id: str) -> str:
    """What came back. A refusal keeps the ceremony's own words (R047 §S2-T5)."""
    if not outcome.ratified:
        return (
            '<h2>Not ratified</h2><div class="rulebar"></div>'
            f'<div class="panel"><p>{shell.chip("refuse", "refused")} '
            f'<span class="mono">{escape(str(outcome.reason or ""))}</span></p>'
            f'<p class="plain">{escape(str(outcome.message or ""))}</p>'
            f'<p class="note"><a href="/drafts/{escape(draft_id)}">Back to the draft</a>. '
            "Nothing was applied.</p></div>"
        )
    receipt = outcome.receipt
    switch = (
        shell.chip("refuse", "engaged")
        if receipt.kill_switch_engaged
        else shell.chip("allow", "not engaged")
    )
    return (
        '<h2>Ratified</h2><div class="rulebar"></div>'
        '<div class="panel"><h3>In force</h3>'
        f'<div class="bigdigest">{escape(receipt.to_version)}</div>'
        '<dl class="kv">'
        f"<dt>Replaced</dt><dd>{shell.digest_html(receipt.from_version)}</dd>"
        f"<dt>Receipt</dt>"
        f"<dd>{shell.digest_html(receipt.sealed()['ratification_digest'])}</dd>"
        f'<dt>Ratified at</dt><dd class="mono">{escape(receipt.ratified_at)}</dd>'
        f'<dt>By session</dt><dd class="mono">{escape(receipt.ratified_by_session)}</dd>'
        f"<dt>Kill switch</dt><dd>{switch}</dd></dl>"
        '<p class="note">Recorded at ratification. The switch does not block ratifying '
        "\u2014 nothing ratified can move while it holds.</p></div>"
    )


# --- V6: re-evaluate under version --------------------------------------------------


def reevaluate_block(
    row: Any,
    versions: tuple[str, ...],
    comparison: Any = None,
) -> str:
    """The flagship, on the History detail page.

    **Both versions are named in the same breath** (R061 §5) — the one that decided
    then and the one replaying now — and the block wears the would-have sentence. A
    counterfactual that does not name its counterfactual-ness on the screen where it
    renders is the backtest panel\u2019s lie one click deeper.

    The dropdown offers only versions `snapshot_for` can actually serve (R056). A
    version this store cannot rebuild is not an option that returns nothing; it is not
    an option.
    """
    decided_under = row["policy_version"]
    options = ['<option value="">Choose a version to replay against</option>']
    for version in versions:
        marker = " \u2014 the version that decided" if version == decided_under else ""
        selected = (
            " selected"
            if comparison is not None and version == getattr(comparison, "against", None)
            else ""
        )
        options.append(
            f'<option value="{escape(version)}"{selected}>'
            f"{escape(shell.short_digest(version))}{escape(marker)}</option>"
        )
    form = (
        f'<form class="filters" method="get" action="/history/{escape(str(row["id"]))}">'
        f'<select name="against">{"".join(options)}</select>'
        '<button type="submit">Re-evaluate</button></form>'
    )

    if comparison is None:
        return (
            '<div class="panel"><h3>Re-evaluate under version</h3>'
            f'<p class="plain">This decision was made under '
            f"{shell.digest_html(decided_under)}. Replay it against another version to "
            "see whether the answer would have been different.</p>"
            + form
            + f'<p class="note">{escape(reevaluate.WOULD_HAVE)}</p></div>'
        )

    then, now = comparison.then, comparison.now
    heading = (
        '<div class="panel"><h3>Re-evaluate under version</h3>'
        f'<p class="plain">Decided under {shell.digest_html(then.version)}; '
        f"replayed under {shell.digest_html(comparison.against)}.</p>" + form
    )

    if now is None:
        # Three outcomes, and neither of these is "no difference". A comparison that
        # could not be made must never render as one that found nothing.
        why = (
            "This store holds no snapshot for that version, so its rules cannot be "
            "rebuilt. No verdict is shown: replaying against an empty policy set would "
            "return a confident refusal that means nothing."
            if comparison.reason == reevaluate.NOT_RETRIEVABLE
            else "This row cannot be rebuilt into a request \u2014 its recorded "
            "parameters are absent or unreadable \u2014 so there is nothing to replay."
        )
        return (
            heading
            + f'<div class="empty"><b>{escape(str(comparison.reason))}.</b> {escape(why)}</div>'
            + f'<p class="note">{escape(reevaluate.WOULD_HAVE)}</p></div>'
        )

    verdict_chip = {
        "allowed": "allow",
        "to_approval": "review",
        "denied": "refuse",
    }
    banner = (
        shell.chip("review", "the answer would have changed")
        if comparison.changed
        else shell.chip("allow", "the answer would have been the same")
    )
    cells = ""
    for label, verdict in (("Decided then", then), ("Would be now", now)):
        chip = shell.chip(verdict_chip.get(verdict.shape, "review"), verdict.decision)
        cells += (
            '<div class="cell"><h5>'
            + escape(label)
            + "</h5>"
            + f"<p>{chip}</p>"
            + f'<p class="note">under {shell.digest_html(verdict.version)}'
            + (
                f', tier <span class="mono">{escape(str(verdict.tier))}</span>'
                if verdict.tier is not None
                else ""
            )
            + "</p></div>"
        )
    return (
        heading
        + f"<p>{banner}</p>"
        + f'<div class="then-now">{cells}</div>'
        + f'<p class="note">{escape(reevaluate.WOULD_HAVE)}</p></div>'
    )


# --- V7 / S2: the editor ------------------------------------------------------------


def _field_html(field: Any) -> str:
    label = f'<label for="f-{escape(field.name)}">{escape(field.label)}</label>'
    if field.kind == "select":
        options = "".join(
            f'<option value="{escape(value)}"'
            + (" selected" if value == field.value else "")
            + f">{escape(text)}</option>"
            for value, text in field.options
        )
        control = (
            f'<select id="f-{escape(field.name)}" name="{escape(field.name)}">{options}</select>'
        )
    elif field.kind == "checkbox":
        checked = " checked" if field.value else ""
        control = (
            f'<input type="checkbox" id="f-{escape(field.name)}" '
            f'name="{escape(field.name)}" value="1"{checked}>'
        )
    else:
        control = (
            f'<input type="text" id="f-{escape(field.name)}" name="{escape(field.name)}" '
            f'value="{escape(field.value)}">'
        )
    note = f'<p class="note">{escape(field.note)}</p>' if field.note else ""
    return f'<div class="field">{label}{control}{note}</div>'


def editor_body(
    draft: Any,
    policy: Any,
    validation: str,
    message: str = "",
    error: str = "",
) -> str:
    """S2: the guided form and the raw rule, rendered from ONE object.

    Both panes come from the same `policy`, so "always in sync" is true by construction
    rather than maintained by two parsers agreeing — see `editor` for why that matters.
    """
    banner = ""
    if error:
        banner = (
            f'<div class="panel"><p>{shell.chip("refuse", "not saved")} '
            f'<span class="plain">{escape(error)}</span></p>'
            '<p class="note">The draft is unchanged. Nothing was written.</p></div>'
        )
    elif message:
        banner = (
            f'<div class="panel"><p>{shell.chip("allow", "saved to the draft")} '
            f'<span class="plain">{escape(message)}</span></p></div>'
        )

    fields = "".join(_field_html(f) for f in editor.fields_for(policy))
    guided = (
        '<div class="panel"><h3>Guided</h3>'
        f'<form method="post" action="/drafts/{escape(draft.draft_id)}/edit/'
        f'{escape(policy.action_type)}">'
        f'<input type="hidden" name="pane" value="form">{fields}'
        '<button type="submit">Save from this pane</button></form>'
        f'<p class="note">This form does not offer '
        + escape(", ".join(editor.NOT_IN_THE_FORM))
        + ". Those are edited in the raw pane, and saving from here leaves them "
        "untouched.</p></div>"
    )
    raw = (
        '<div class="panel"><h3>The rule</h3>'
        f'<form method="post" action="/drafts/{escape(draft.draft_id)}/edit/'
        f'{escape(policy.action_type)}">'
        '<input type="hidden" name="pane" value="raw">'
        f'<textarea name="raw" id="raw-pane" rows="20" spellcheck="false" '
        f'data-validate="/drafts/{escape(draft.draft_id)}/validate">'
        f"{escape(editor.raw_for(policy))}</textarea>"
        '<button type="submit">Save from this pane</button></form>'
        '<p class="note">JSON, which is loadable YAML. Both panes are rendered from the '
        "same parsed rule, so they cannot disagree.</p></div>"
    )

    return (
        f'<h2>{escape(policy.action_type)}</h2><div class="rulebar"></div>'
        f'<p class="lede">Editing inside the draft <a href="/drafts/'
        f'{escape(draft.draft_id)}">{escape(draft.title)}</a>. The rules in force are '
        "not touched by anything on this page.</p>"
        + banner
        + f'<div class="cols">{guided}{raw}</div>'
        + f'<div id="validation">{validation}</div>'
    )


# --- ND-056 / T1: upload -------------------------------------------------------------


UPLOAD_NOTE = (
    "The file is checked by the engine's own loader, one stage at a time, and whatever "
    "it refuses is shown on the draft. Nothing you upload reaches the rules in force: a "
    "draft is not a policy set, and only the ratification ceremony changes what is "
    "enforced."
)


def upload_block() -> str:
    """The upload affordance, on the drafts page beside the two ways that already exist."""
    return (
        '<div class="panel upload-block"><h3>From a file</h3>'
        '<form method="post" action="/drafts/upload" enctype="multipart/form-data">'
        '<input type="file" name="policy_file" accept=".yaml,.yml,.json,text/yaml,'
        'application/x-yaml,application/json" aria-label="Policy file">'
        '<button type="submit">Upload as a draft</button></form>'
        f'<p class="note">{escape(UPLOAD_NOTE)}</p></div>'
    )


def upload_missing_body() -> str:
    """No file arrived. An absence, said as one."""
    return (
        '<h2>Upload a policy file</h2><div class="rulebar"></div>'
        '<div class="empty">No file arrived with that request, so nothing was read and '
        "no draft was created. This is an absence, not a rejected file.</div>"
        '<p class="note"><a href="/drafts">Back to drafts</a></p>'
    )


def upload_undecodable_body(filename: str, detail: str) -> str:
    """Unreadable is its own outcome — not a policy that failed validation.

    Telling an operator their policy is invalid when what is wrong is the file's encoding
    would be the deposition page's error committed at the other end of the product: a
    verdict about content, delivered about a file nothing could read.
    """
    return (
        '<h2>Upload a policy file</h2><div class="rulebar"></div>'
        f'<div class="empty">{escape(filename)} is not UTF-8 text, so the loader was '
        "never asked what it thinks of the rules inside it. <strong>Nothing here says "
        "the policy is invalid</strong> — it says the file could not be read."
        f'<p class="note">{escape(detail)}</p></div>'
        '<p class="note"><a href="/drafts">Back to drafts</a></p>'
    )


def validation_unavailable(draft_id: str) -> str:
    """The fragment's own absence, in the fragment's shape (it is swapped into a page)."""
    return (
        '<div class="panel"><h3>Validation</h3>'
        f'<div class="empty">There is no draft {escape(draft_id)} in this store, so '
        "nothing was validated. Nothing here is a statement about the rule you are "
        "editing.</div></div>"
    )


# --- V8 / S6: the deposition page ---------------------------------------------------


VERIFY_CHIPS = {
    verify.VERIFIED: "allow",
    verify.FAILED: "refuse",
    verify.UNREADABLE: "review",
}
"""Three outcomes, three chips. `unreadable` is **not** a failure — the check never ran,
and telling a stranger their receipt is bad when what is bad is their download would be
the worst error this page could make."""


def verify_index_body(receipts: tuple[Any, ...]) -> str:
    """S6 index: which receipts this store can hand a stranger."""
    head = (
        '<h2>Verify</h2><div class="rulebar"></div>'
        f'<p class="lede">{escape(verify.CANNOT_VERIFY)}</p>'
    )
    if not receipts:
        return head + (
            '<div class="empty">This store holds no ratification receipts yet. '
            "A receipt is sealed when a draft is ratified.</div>"
        )
    rows = "".join(
        "<tr>"
        f'<td><a href="/verify/{escape(digest)}">{shell.digest_html(digest)}</a></td>'
        f'<td class="mono">{escape(at)}</td></tr>'
        for digest, at in receipts
    )
    return head + (
        '<div class="panel"><table><thead><tr><th>Receipt</th><th>Sealed</th>'
        "</tr></thead><tbody>" + rows + "</tbody></table></div>"
    )


DOWNLOAD_NOTE = "Download for the exact bytes rather than copying the text below."
"""R089 F-V1. The pane below is still shown in full — a reader should not have to
download a file to see what is in it — but selecting text out of a `<pre>` block risks
losing or gaining a byte, and a single wrong byte here produces a **false `failed`** on
a receipt that was sound. The route this points at (`server.py`'s
`verify_receipt_download`/`verify_snapshot_download`) serves the identical string this
page renders, with `Content-Disposition: attachment` — the same bytes, not a
re-rendering of them."""


def deposition_body(dep: Any) -> str:
    """One receipt, for a reader who trusts nobody here.

    Ordered for that reader: what to run, then the files to run it on, then what this
    software got when it ran the same command — **in that order on purpose**, so the
    method is read before the answer and the answer is never the first thing offered.
    """
    chip = shell.chip(VERIFY_CHIPS.get(dep.outcome, "review"), dep.outcome)
    return (
        '<h2>Verify a receipt</h2><div class="rulebar"></div>'
        f'<p class="lede">{escape(verify.CANNOT_VERIFY)}</p>'
        '<div class="panel"><h3>Run this</h3>'
        f"<pre>{escape(verify.COMMAND)}</pre>"
        f'<p class="plain">{escape(verify.INDEPENDENCE)}</p>'
        '<dl class="kv">'
        "<dt>verified</dt><dd>exit 0 — the receipt matches its own digest, and the "
        "snapshot hashes to the version the receipt ratified</dd>"
        "<dt>failed</dt><dd>exit 1 — one of those two checks did not hold</dd>"
        "<dt>unreadable</dt><dd>exit 2 — a file could not be read or parsed, so the "
        "check never ran. This is not a failed verification</dd>"
        "</dl></div>"
        '<div class="cols">'
        f'<div class="panel"><h3>receipt.json '
        f'<a class="sealbtn download" href="/verify/{escape(dep.ratification_digest)}'
        f'/receipt.json" download="receipt.json">Download</a></h3>'
        f'<p class="note">{escape(str(dep.receipt_bytes))} bytes. Its SHA-256 over the '
        "body, excluding <code>ratification_digest</code>, is that digest. "
        f"{escape(DOWNLOAD_NOTE)}</p>"
        f"<pre>{escape(dep.receipt_json)}</pre></div>"
        f'<div class="panel"><h3>snapshot.json '
        f'<a class="sealbtn download" href="/verify/{escape(dep.ratification_digest)}'
        f'/snapshot.json" download="snapshot.json">Download</a></h3>'
        f'<p class="note">{escape(str(dep.snapshot_bytes))} bytes, byte-for-byte as '
        "stored. Its SHA-256 <em>is</em> the version this receipt ratified, so "
        f"reformatting it breaks the check it exists for. {escape(DOWNLOAD_NOTE)}</p>"
        f"<pre>{escape(dep.snapshot_text)}</pre></div>"
        "</div>"
        '<div class="panel"><h3>What this software got</h3>'
        f'<p>{chip} <span class="plain">{escape(dep.detail)}</span></p>'
        f'<dl class="kv"><dt>Receipt</dt><dd>{shell.digest_html(dep.ratification_digest)}</dd>'
        f"<dt>Ratified version</dt><dd>{shell.digest_html(dep.to_version)}</dd></dl>"
        '<p class="note">Running the same command over the same two files is what makes '
        "this line worth reading. It is shown so you can check that you got the same "
        "answer, not so you can take it instead of checking.</p></div>"
    )


def deposition_missing_body(digest: str) -> str:
    """Absent, and not a failed verification."""
    return (
        '<h2>Verify a receipt</h2><div class="rulebar"></div>'
        f'<div class="empty">This store holds no receipt '
        f"{shell.digest_html(digest)}. That is an absence, not a failed check — nothing "
        "was verified and nothing was refuted.</div>"
    )


# --- ND-056 / T1: the two validation lists, rendered apart --------------------------


def _refusal_row(refusal: staging.Refusal) -> str:
    where = escape(refusal.position.describe())
    named = refusal.action_type or ""
    rule = f'<span class="mono">{escape(named)}</span> ' if named else ""
    return (
        f'<li>{rule}<span class="plain">{escape(refusal.message)}</span>'
        f'<span class="note pos"> — {where}</span></li>'
    )


def _stopped_notice(result: staging.StagedResult) -> str:
    """Which stages did not run, and that their silence is not a pass.

    The easiest misreading on this page: a reader sees three empty stages and concludes
    the file is three-quarters fine. They did not run.
    """
    if result.stopped_at is None:
        return ""
    remaining = result.stages_not_run
    if not remaining:
        return ""
    names = ", ".join(staging.STAGE_LABELS[s] for s in remaining)
    return (
        f'<p class="note honesty">{escape(staging.STOPPED_NOTICE)} '
        f'<span class="plain">Not run: {escape(names)}.</span></p>'
    )


def refusals_block(result: staging.StagedResult) -> str:
    """What the loader would refuse at boot — and nothing else.

    Kept structurally apart from `forecasts_block` because they answer different
    questions, and a reader who cannot tell them apart learns a schema the engine does
    not have (R066 §3).
    """
    stage = ""
    if result.stopped_at is not None:
        stage = (
            f'<p class="note">Stopped at: {escape(staging.STAGE_LABELS[result.stopped_at])}.</p>'
        )
    if not result.refusals:
        body = (
            '<div class="empty">Nothing here would be refused at boot. That is the '
            "engine's own loader answering, one stage at a time.</div>"
        )
    else:
        body = f'<ul class="problems">{"".join(_refusal_row(r) for r in result.refusals)}</ul>'
    return (
        '<div class="panel"><h3>The loader would refuse this</h3>'
        + stage
        + body
        + _stopped_notice(result)
        + _honesty_footnote()
        + "</div>"
    )


def forecasts_block(items: tuple[forecast.Forecast, ...], *, inert_checked: bool) -> str:
    """How each rule will behave once in force. NOT refusals, and the heading says so."""
    if not items:
        body = '<div class="empty">No decision-time behaviour was predicted for these rules.</div>'
    else:
        rows = "".join(
            f'<li><span class="mono">{escape(f.action_type)}</span> '
            f'<span class="chip c-review">{escape(f.reason_code)}</span> '
            f'<span class="plain">{escape(f.message)}</span></li>'
            for f in items
        )
        body = f'<ul class="problems">{rows}</ul>'
    unknown = (
        "" if inert_checked else f'<p class="note honesty">{escape(forecast.INERT_UNKNOWN)}</p>'
    )
    return (
        '<div class="panel"><h3>Once in force, these rules will</h3>'
        f'<p class="note">{escape(forecast.FORECAST_NOTICE)}</p>'
        + body
        + unknown
        + f'<p class="note honesty">{escape(forecast.FORECASTS_ARE_NOT_COMPLETE)}</p></div>'
    )


def validation_fragment(
    result: staging.StagedResult,
    items: tuple[forecast.Forecast, ...],
    *,
    inert_checked: bool,
) -> str:
    """Both lists, in the order a reader needs them: refusals first, behaviour second.

    Served whole by the editor page and as a fragment by the live-validation route, so
    what a keystroke updates and what a page load renders are the same bytes from the
    same function. A fragment built by a second renderer would be the two-parser defect
    wearing HTML.
    """
    return refusals_block(result) + forecasts_block(items, inert_checked=inert_checked)


# --- ND-056 / T3: natural-language authoring -----------------------------------------


def _instrument_block(instrument: dict[str, Any]) -> str:
    """What produced this, pinned and named (wall 1).

    Rendered from the instrument the proposer declared, never from anything inferred at
    render time. The key is absent because it was never recorded: a credential in a
    record is a credential in a record, and a digest of one is still a function of it.
    """
    rows = "".join(
        f"<dt>{escape(str(k).replace('_', ' '))}</dt><dd>"
        + (
            shell.digest_html(str(v))
            if str(k).endswith("_digest")
            else f'<span class="mono">{escape(str(v))}</span>'
        )
        + "</dd>"
        for k, v in sorted(instrument.items())
    )
    return (
        '<div class="panel"><h3>The instrument</h3>'
        f'<dl class="kv">{rows}</dl>'
        f'<p class="note">{escape(proposer.NOT_REDERIVABLE)}</p>'
        f'<p class="note">{escape(proposer.AUTHORITY_FROM_CHECKS)}</p></div>'
    )


def propose_body(instrument: dict[str, Any], *, error: str = "", unavailable: str = "") -> str:
    """The description form, the instrument, and the capability sentence."""
    banner = ""
    if unavailable:
        # Unavailable is its own outcome, and the page says so in those words: a socket
        # that did not answer is not a judgement about what the operator wrote.
        banner = (
            f'<div class="panel"><p>{shell.chip("review", "no answer")} '
            f'<span class="plain">{escape(unavailable)}</span></p>'
            '<p class="note">Nothing was drafted. This says nothing about your '
            "description.</p></div>"
        )
    elif error:
        banner = (
            f'<div class="panel"><p>{shell.chip("refuse", "nothing drafted")} '
            f'<span class="plain">{escape(error)}</span></p></div>'
        )

    form = (
        '<div class="panel"><h3>Describe what the agent may do</h3>'
        '<form method="post" action="/propose">'
        '<textarea name="description" rows="10" spellcheck="false" '
        'placeholder="Refunds up to 200 euro without asking. Anything larger needs a '
        'human. Never send payouts."></textarea>'
        '<button type="submit">Propose a draft</button></form>'
        f'<p class="note">{escape(PROPOSE_NOTE)}</p></div>'
    )
    return (
        f'<h2>Propose</h2><div class="rulebar"></div>'
        f'<p class="lede">{escape(live_proposer.CAPABILITY)}.</p>'
        + banner
        + form
        + _instrument_block(instrument)
    )


PROPOSE_NOTE = (
    "Your description is frozen exactly as written. What comes back is parsed by the "
    "engine's own loader and becomes a draft — the same kind of draft you would get from "
    "the editor or an upload, and it changes nothing until you ratify it on the ceremony "
    "page."
)


def proposal_refused_body(
    instrument: dict[str, Any], result: staging.StagedResult, text: str
) -> str:
    """The parser refused the generation. Shown with reasons, never repaired (wall 2).

    The model's raw output is shown verbatim beside the refusals, because the operator
    needs to see what was actually produced — and because quietly fixing it and showing
    the fixed version would be this page deciding what the model meant.
    """
    return (
        '<h2>Propose</h2><div class="rulebar"></div>'
        f'<p class="lede">{escape(live_proposer.CAPABILITY)}.</p>'
        f'<div class="panel"><p>{shell.chip("refuse", "not a draft")} '
        '<span class="plain">The loader would refuse what came back, so no draft was '
        "created.</span></p>"
        '<p class="note">Nothing was repaired or rewritten. What the model produced is '
        "shown below exactly as it arrived.</p></div>"
        + refusals_block(result)
        + '<div class="panel"><h3>What the model returned</h3>'
        f"<pre>{escape(text)}</pre>"
        '<p class="note">Shown verbatim. It is the model’s output, not a policy '
        "and not a draft.</p></div>" + _instrument_block(instrument)
    )


def derivation_block(record: dict[str, Any] | None) -> str:
    """ "Drafted via <instrument>" on the draft the model produced (wall 1).

    A draft with no record says so rather than rendering blank: every draft either names
    the instrument that drafted it or was written by a person, and those are different
    facts.
    """
    if record is None:
        return (
            '<div class="panel"><h3>Where this draft came from</h3>'
            '<div class="empty">Written by hand. No model was involved, and no '
            "derivation record exists for it.</div></div>"
        )
    instrument = record.get("instrument") or {}
    named = instrument.get("model") or instrument.get("name") or "an unnamed instrument"
    mentions = record.get("mentions") or []
    return (
        '<div class="panel"><h3>Where this draft came from</h3>'
        f'<p class="plain">Drafted via <span class="mono">{escape(str(named))}</span>, '
        f"then parsed by the engine’s loader before anything below was shown.</p>"
        f'<dl class="kv"><dt>record</dt><dd>{shell.digest_html(record.get("record_digest"))}</dd>'
        f"<dt>description</dt><dd>{shell.digest_html(record.get('description_digest'))}</dd>"
        f'<dt>provenance</dt><dd><span class="mono">'
        f"{escape(str(record.get('proposer_provenance', '')))}</span></dd></dl>"
        f'<p class="note">{escape(proposer.NOT_REDERIVABLE)}</p>'
        f'<p class="note">{escape(proposer.AUTHORITY_FROM_CHECKS)}</p>'
        "</div>" + dark_surface_block(mentions)
    )


DARK_SURFACE_HEADING = "Mentioned, and not covered by any rule"

DARK_SURFACE_EMPTY = (
    "Nothing in the description was recognised as naming an action that got no rule. "
    "That is what this check found, not a guarantee that the description is fully "
    "covered."
)

DARK_SURFACE_NOTE = (
    "Each line quotes the description's own words. Nothing here is the model's summary "
    "of what it did."
)


def dark_surface_block(mentions: list[dict[str, Any]]) -> str:
    """Wall 6 / constitution principle 4: non-coverage is stated, never silent.

    Rendered even when empty, and the empty wording is careful: *what this check found*,
    never *the description is covered*. A policy set that does not declare its gaps is an
    E11 violation in product form, and a gap list that overclaimed completeness would be
    the same defect one layer up.
    """
    uncovered = [m for m in mentions if not m.get("covered_by")]
    if not uncovered:
        body = f'<div class="empty">{escape(DARK_SURFACE_EMPTY)}</div>'
    else:
        rows = "".join(
            f'<li><span class="mono">{escape(str(m.get("subject", "")))}</span> '
            f"<blockquote>{escape(str(m.get('quote', '')))}</blockquote></li>"
            for m in uncovered
        )
        body = f'<ul class="problems">{rows}</ul>'
    return (
        f'<div class="panel"><h3>{escape(DARK_SURFACE_HEADING)}</h3>'
        + body
        + f'<p class="note">{escape(DARK_SURFACE_NOTE)}</p></div>'
    )
