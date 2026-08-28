"""V1 — the Studio shell: header, version banner, tabs, footer.

The chrome every Studio screen sits inside. Built from the mockup R055 §0 names as
binding design authority; the tokens come from `studio.tokens`, never from this file.

## Three decisions this module makes, and why each is not a deviation

**No design-study banner.** The mockup carries `design study · … · not the shipped
product` across its top. The design note asks for it *"on every mockup frame until
built"* — this is the built thing, so carrying the banner into it would be the page
lying about itself in the one line whose whole job is to say what the page is.

**Tabs are links, not buttons.** The mockup switches tabs in JavaScript because it is
one static file. R055's V1 asks for the F-A regression to be rerun *"against every new
route"* — routes, plural, server-side — and the Studio has held a no-JavaScript line
since F-G, where a `<form>` was chosen over `fetch` so the page works with scripting
off. Same design, delivered by the transport this app actually has.

**A tab whose screen is not built does not render as a link.** V8(f) states the rule —
*a control that cannot act must not render enabled* — and there is no reason to wait
for V8 to start obeying it. An unbuilt tab renders as text with the stage that will
build it named, so an operator meets the truth rather than a dead link. `TABS` is the
single place that knowledge lives; a screen becomes reachable by flipping one flag,
which is why the flag is not duplicated into a template.

## The digest affordance, and the thing it deliberately does not claim

The design note asks for digests rendered `first-8…last-4`, *"with copy-on-click, full
on hover."* Two of those three are free: the truncation is arithmetic and the full
value goes in `title`. **Copy-on-click needs JavaScript, and this app does not run
any** — so the `cursor:copy` the mockup declares is not emitted here.

That is V8(f) again, one layer down. A cursor that says *copy* over an element that
cannot copy is an overclaim rendered in CSS: it costs one character to write and it
teaches the operator that clicking does something, which it does not. The full digest
is on hover and selectable, and when a copy control that works arrives, the cursor
arrives with it. *An affordance is a promise; do not render the promise before the
thing.*
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from onedoor.studio import tokens

WORDMARK = "ONEDOOR"
SUBMARK = "POLICY STUDIO"

LOOPBACK_LINE = "loopback only — nothing leaves this machine"
"""The mockup's wording, kept verbatim.

The design note makes this a selling line rather than a caveat (*"your policies never
leave your machine" — local-first vs veto's cloud*), and it is a claim the code
actually enforces: `server.require_loopback` refuses a non-loopback bind before a
socket is opened. A promise in the header that the binder did not keep would be worse
than no promise at all, which is why the two live one import apart.
"""

NOTHING_IN_FORCE = "no version in force"
"""What the banner says when the enforcer store has never been ratified.

Absent is a state to render, not a blank to leave. *A blank is a promise that someone
will remember* — and the operator who meets an empty banner will read it as a loading
failure, which is the wrong worry.
"""

NEVER_RATIFIED = "never ratified"

RATIFIED_ELSEWHERE = "not ratified through this Studio"
"""The third outcome, and the one a two-state banner would get wrong.

The version in force is read from the enforcer store; the ratification date is read
from the Studio's own log. They can disagree — a store edited by another Studio, a
restore from backup, an operator who applied policy by hand — and when they do, the
honest sentence is not a date and not "never ratified". It is *this Studio does not
know when that happened*, which is a different fact with a different remedy.

Absent, unverifiable, failed. A banner that printed the latest ratification's date
beside a version that ratification did not produce would be **wrong in the most
expensive direction**: confidently, and in the field an auditor reads first.
"""


@dataclass(frozen=True)
class Tab:
    """One entry in the Studio's top navigation.

    `built` is the whole point: it is the difference between a link and a sentence.
    """

    key: str
    label: str
    path: str
    built: bool
    stage: str
    """The V-stage that builds this screen, named in the page when it is not built yet."""


TABS: tuple[Tab, ...] = (
    Tab("policies", "Policies", "/policies", False, "V2"),
    Tab("drafts", "Drafts", "/", True, "V1"),
    Tab("history", "History", "/history", False, "V3"),
    Tab("state", "Live state", "/state", False, "V4"),
    Tab("verify", "Verify", "/verify", False, "V8"),
)
"""The five tabs of the design note's six screens — S2 (the editor) lives inside a
draft rather than beside it, which is fence-post one restated in navigation: there is
no route from the top bar to anything that edits live rules."""


@dataclass(frozen=True)
class Banner:
    """What the version banner states, resolved before rendering rather than during.

    Every field is nullable and every null has a rendered word, because this banner is
    the first thing an operator reads and the three outcomes have to survive it:
    a version in force, no version in force, and — the one a blank would hide — a
    store this Studio could read but that has never been ratified.
    """

    in_force: str | None
    ratified: str | None
    policies: int
    effects: int


def short_digest(digest: str | None) -> str:
    """`first-8…last-4`, the design note's format.

    A digest too short to truncate is returned whole rather than padded: the format
    exists to make a long value scannable, and applying it to a value that is already
    short would invent characters that are not in the digest.
    """
    if not digest:
        return NOTHING_IN_FORCE
    return digest if len(digest) <= 13 else f"{digest[:8]}…{digest[-4:]}"


def digest_html(digest: str | None, *, css_class: str = "digest") -> str:
    """A digest, truncated for reading and complete for checking.

    The full value is in `title` (hover) and in `data-digest` (a copy control's future
    handle, and a test's present one). No `cursor:copy` — see the module docstring.
    """
    if not digest:
        return f'<span class="{css_class} absent">{escape(NOTHING_IN_FORCE)}</span>'
    return (
        f'<span class="{css_class}" title="{escape(digest)}" data-digest="{escape(digest)}">'
        f"{escape(short_digest(digest))}</span>"
    )


def _count(n: int, singular: str, plural: str) -> str:
    """`1 policy` / `0 policies`. Both forms are given rather than derived.

    English does not make plurals by appending `s` often enough for a rule to be worth
    the one time it produces "policys" in the header of a product about precision.
    """
    return f"{n} {singular if n == 1 else plural}"


def banner_html(banner: Banner) -> str:
    """`in force <digest> · ratified <date> · N policies · M effects · loopback only`."""
    ratified = escape(banner.ratified) if banner.ratified else NEVER_RATIFIED
    return (
        '<div class="vbanner">'
        f"in force {digest_html(banner.in_force)} · ratified {ratified} · "
        f"{_count(banner.policies, 'policy', 'policies')} · "
        f"{_count(banner.effects, 'effect', 'effects')} · {escape(LOOPBACK_LINE)}"
        "</div>"
    )


def nav_html(active: str) -> str:
    """The five tabs. Built ones are links; the rest say which stage builds them."""
    out = ['<nav aria-label="Studio sections">']
    for tab in TABS:
        on = " on" if tab.key == active else ""
        if tab.built:
            aria = ' aria-current="page"' if on else ""
            out.append(
                f'<a class="tab{on}" href="{escape(tab.path)}" data-tab="{tab.key}"{aria}>'
                f"{escape(tab.label)}</a>"
            )
        else:
            out.append(
                f'<span class="tab unbuilt" data-tab="{tab.key}" '
                f'title="not built yet — {escape(tab.stage)}" aria-disabled="true">'
                f"{escape(tab.label)}</span>"
            )
    out.append("</nav>")
    return "".join(out)


def header_html(banner: Banner) -> str:
    return (
        "<header>"
        f'<div class="wordmark">{escape(WORDMARK)}<small>{escape(SUBMARK)}</small></div>'
        f"{banner_html(banner)}"
        "</header>"
    )


def unbuilt_html(tab: Tab) -> str:
    """The body of a route whose screen is not built.

    A route that exists so the shell has somewhere to point must say so plainly. It is
    not a 404 — the section is real and is coming — and it is not an empty page, which
    would read as a failure.
    """
    return (
        f'<h2>{escape(tab.label)}</h2><div class="rulebar"></div>'
        f'<div class="empty">This section is not built yet — it lands in {escape(tab.stage)}. '
        f"Nothing is hidden here; there is nothing here yet.</div>"
    )


# Colours the shell emits that are not tokens, each with the reason it is not one.
# Declared rather than inlined so `tests/studio/test_tokens.py` can assert that the
# emitted page contains no colour outside this set plus the palette -- the check that
# stops a hand-picked hex from drifting in one screen at a time.
ALLOWED_NON_TOKEN_COLOURS = {
    "#171310": "the mockup's inset well, one step below --ground, used for code and fields",
}

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:14.5px;
  line-height:1.55;min-height:100vh}
header{display:flex;align-items:baseline;gap:1.4rem;padding:1.3rem 2rem .9rem;
  border-bottom:1px solid var(--line);flex-wrap:wrap}
.wordmark{font-family:var(--sans);font-weight:600;letter-spacing:.24em;color:var(--gold);
  font-size:1.02rem}
.wordmark small{display:block;letter-spacing:.34em;font-size:.6rem;color:var(--gold-dim);
  margin-top:.1rem}
.vbanner{margin-left:auto;font-family:var(--mono);font-size:.78rem;color:var(--dim)}
.vbanner .digest{color:var(--ink);font-weight:500}
.vbanner .absent{font-style:italic}
nav{display:flex;gap:.25rem;padding:0 2rem;border-bottom:1px solid var(--line);overflow-x:auto}
.tab{color:var(--dim);font-family:var(--sans);font-weight:500;font-size:.92rem;
  padding:.85rem 1.05rem;border-bottom:2px solid transparent;white-space:nowrap;
  text-decoration:none;display:inline-block}
a.tab:hover{color:var(--ink)}
.tab.on{color:var(--ink);border-bottom-color:var(--gold)}
.tab.unbuilt{color:var(--faint);cursor:default}
main{max-width:1200px;margin:0 auto;padding:1.6rem 2rem 4rem}
h2{font-family:var(--serif);font-weight:400;font-size:1.5rem;margin:.2rem 0 1rem}
h3{font-family:var(--serif);font-weight:400;font-size:1.12rem;margin:0 0 .6rem}
.rulebar{height:1px;background:linear-gradient(90deg,var(--gold-dim),transparent);
  margin:.4rem 0 1rem}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:1.1rem 1.25rem;margin-bottom:1.15rem}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.digest{font-family:var(--mono);font-size:.82rem;color:var(--dim)}
.empty{border:1px dashed var(--line);border-radius:8px;padding:1rem 1.2rem;
  color:var(--faint);font-size:.88rem;font-style:italic}
footer{border-top:1px solid var(--line);margin-top:2.5rem;padding:1.1rem 2rem;
  font-size:.75rem;color:var(--faint);text-align:center}
"""

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Libre+Caslon+Text:ital,wght@0,400;0,700;1,400&family=Archivo:wght@400;500;600"
    '&family=IBM+Plex+Mono:wght@400;500&display=swap">'
)
"""Deliberately NOT emitted. Kept as a named constant so the omission is legible.

The mockup loads three families from Google Fonts. The Studio binds loopback and says
in its own header that nothing leaves this machine — a stylesheet fetched from a third
party on every page load would make that sentence false, and would tell that third
party when an operator opens their policy console. The token stacks name real
fallbacks (`Georgia`, `system-ui`, `Consolas`), so the page renders in the intended
shapes without asking anyone's permission. `test_studio_pages_reference_no_external_
origin` fails if this ever gets emitted.
"""


def css() -> str:
    """The full stylesheet: pinned tokens, then the shell's own rules."""
    return tokens.root_css() + _CSS


def render(
    *,
    body: str,
    banner: Banner,
    active: str,
    title: str = "onedoor policy studio",
) -> str:
    """A complete Studio page. `body` is already-escaped HTML from a screen module."""
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{css()}</style></head><body>"
        f"{header_html(banner)}{nav_html(active)}"
        f"<main>{body}</main>"
        f"<footer>{escape(LOOPBACK_LINE)}</footer>"
        "</body></html>"
    )
