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

## The digest affordance, and how the promise stays tied to the capability

The design note asks for digests rendered `first-8…last-4`, *"with copy-on-click, full
on hover."* Truncation is arithmetic and the full value goes in `title`; copy-on-click
needs JavaScript.

V1 first dropped the feature to keep the page script-free. **That was stricter than the
ruling and cost a mandated affordance** — R055 §3 permits *"minimal inline JS, matching
the current architecture"*, and R057 §2 restored copy-on-click as **progressive
enhancement**.

The shape is the point. `cursor:copy` lives on `.digest.copyable`, and **nothing in the
served HTML carries that class**: the inline script adds it in the same statement that
attaches the click handler, and only after checking the clipboard API is actually
there. So the cursor and the capability arrive in the same instant or not at all, and
V8(f) is satisfied *structurally* rather than by anyone remembering. With scripting off,
the page is exactly what V1 shipped — a digest, truncated, complete on hover.

*An affordance is a promise; the promise and the thing must be one act.*

The clipboard API needs a secure context, and `http://127.0.0.1` is one — localhost is
potentially-trustworthy by specification. The guard is still checked rather than assumed,
because an operator who reaches the Studio through a tunnel under some other origin
would otherwise get a cursor over a function that throws.
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

NOT_RECORDED = "not recorded"
"""What a digest slot says when it is null for a legitimate reason that is NOT the
absence of a policy version — R089 F-H1. The history detail page's receipt/chain digests
are null because ND-017 (content-addressed receipts, anchoring) is unimplemented, and
`NOTHING_IN_FORCE` would tell the reader something false and beside the point: a version
IS in force, shown elsewhere on the same page, and these are digest slots, not version
slots. Pass this as `digest_html`'s `absent_label` for any digest that is not a policy
version."""

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
    Tab("policies", "Policies", "/policies", True, "V2"),
    Tab("drafts", "Drafts", "/drafts", True, "V5"),
    Tab("history", "History", "/history", True, "V3"),
    Tab("state", "Live state", "/state", True, "V4"),
    Tab("verify", "Verify", "/verify", True, "V8"),
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


def digest_html(
    digest: str | None, *, css_class: str = "digest", absent_label: str = NOTHING_IN_FORCE
) -> str:
    """A digest, truncated for reading and complete for checking.

    The full value is in `title` (hover) and in `data-digest`, which is both the copy
    handler's handle and the test's. The `copyable` class is **not** emitted here — see
    the module docstring: the script that can copy is the thing that grants the cursor.

    `absent_label` defaults to `NOTHING_IN_FORCE`, which is correct for the policy-
    version digests this function was written for — every caller that renders one keeps
    that wording unchanged. It is a parameter and not a constant because **a label
    composed for one state leaks into another the moment a second caller reuses the
    function for a digest that is not a policy version** (R089 F-H1, fix C's banner
    finding again): the history detail page's Digests/Chain panels called this on
    receipt and chain-anchor digests — genuinely null because ND-017 is unimplemented —
    and every null slot read *"no version in force"*, a sentence about a version, over
    eight fields that are not about one. A version demonstrably WAS in force, shown two
    lines above on the same page. Those callers pass their own words.
    """
    if not digest:
        return f'<span class="{css_class} absent">{escape(absent_label)}</span>'
    return (
        f'<span class="{css_class}" title="{escape(digest)}" data-digest="{escape(digest)}">'
        f"{escape(short_digest(digest))}</span>"
    )


#: The verdict words, which are what actually makes a state readable to someone who
#: cannot distinguish the colours. See `chip`.
STATE_WORDS = {"allow": "allowed", "review": "review", "refuse": "refused"}


def chip(state: str, label: str | None = None) -> str:
    """A state chip: a colour **and** a word, never a colour alone.

    This is the design system's answer to what the contrast correction cost. Lightening
    `--refuse` far enough to be readable (R057 §5) pushed it toward `--review` under
    tritanopia and toward `--allow` under deuteranopia — measured, disclosed, and not
    fixable by any choice of hex, because the darkness that separated it *was* the
    thing that failed the contrast requirement.

    Colour therefore carries no state on its own anywhere in this Studio. It is
    redundant coding over a word, which is what WCAG 1.4.1 asks for and what a
    delta-E floor was only ever a proxy for. `test_no_state_is_signalled_by_colour_alone`
    holds it as a property, so the guarantee does not depend on the palette staying
    lucky.
    """
    if state not in STATE_WORDS:
        raise ValueError(f"{state!r} is not one of {sorted(STATE_WORDS)}")
    return f'<span class="chip c-{state}">{escape(label or STATE_WORDS[state])}</span>'


def _count(n: int, singular: str, plural: str) -> str:
    """`1 policy` / `0 policies`. Both forms are given rather than derived.

    English does not make plurals by appending `s` often enough for a rule to be worth
    the one time it produces "policys" in the header of a product about precision.
    """
    return f"{n} {singular if n == 1 else plural}"


def ratified_phrase(ratified: str | None) -> str:
    """The banner's ratification clause, **label and value composed together**.

    The label used to be emitted unconditionally in front of whichever constant the
    branch chose, which reads correctly for a date and absurdly for the other two:
    *"ratified never ratified"*, and *"ratified not ratified through this Studio"* —
    an affirmative verb bolted to the front of a sentence written to deny it. An
    operator saw the second one.

    The three constants are correct and untouched; only the composition was wrong.
    **A label that is true of one branch is not a prefix for all of them** — the value
    decides whether a label applies, so the value carries it.

    Two of the three values are already complete sentences and take no label. Only a
    date needs one, and it is the only branch that gets one. Testing truthiness was
    what produced the defect: `RATIFIED_ELSEWHERE` is a non-empty string, so a
    truthiness test cannot tell it from a date. **The branch is chosen by which value
    it is, not by whether there is one.**
    """
    if ratified is None:
        return NEVER_RATIFIED
    if ratified == RATIFIED_ELSEWHERE:
        return escape(RATIFIED_ELSEWHERE)
    return f"ratified {escape(ratified)}"


def banner_html(banner: Banner) -> str:
    """`in force <digest> · ratified <date> · N policies · M effects · loopback only`."""
    ratified = ratified_phrase(banner.ratified)
    return (
        '<div class="vbanner">'
        f"in force {digest_html(banner.in_force)} · {ratified} · "
        f"{_count(banner.policies, 'policy', 'policies')} · "
        f"{_count(banner.effects, 'effect', 'effects')} · {escape(LOOPBACK_LINE)}"
        "</div>"
    )


def nav_html(active: str, tabs: tuple[Tab, ...] | None = None) -> str:
    """The five tabs. Built ones are links; the rest say which stage builds them.

    `tabs` exists so the unbuilt rendering stays testable now that every real tab is
    built. **A guard has to survive the day it has nothing real to guard**, or it
    quietly stops guarding whoever adds the next screen.
    """
    out = ['<nav aria-label="Studio sections">']
    for tab in tabs or TABS:
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
/* The one colour that is not in the pinned block, declared as a named token so
   screens can use a name and the exception stays in exactly one place. */
:root{--well:#171310}
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
.chip{display:inline-block;padding:.13rem .55rem;border-radius:999px;font-size:.72rem;
  font-weight:600;letter-spacing:.05em}
.c-allow{background:var(--allow-bg);color:var(--allow)}
.c-review{background:var(--review-bg);color:var(--review)}
.c-refuse{background:var(--refuse-bg);color:var(--refuse)}
/* The cursor is granted by the script, never by the server. Nothing the server emits
   carries `copyable`, so a page with scripting off promises nothing it cannot do. */
.digest.copyable{cursor:copy}
.digest.copied{color:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);
  font-weight:600;text-align:left;padding:.45rem .7rem;border-bottom:1px solid var(--line)}
td{padding:.6rem .7rem;border-bottom:1px solid var(--line);vertical-align:top}
td a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--line)}
td a:hover{border-bottom-color:var(--gold)}
.badge{font-size:.7rem;color:var(--dim);white-space:nowrap}
.tier{font-family:var(--mono);font-size:.78rem;color:var(--dim)}
.lede{color:var(--dim);font-size:.9rem;margin:0 0 1rem;max-width:62ch}
.plain p{margin:.45rem 0;font-size:.92rem}
.plain code{font-family:var(--mono);font-size:.85rem;color:var(--ink)}
.plain strong{color:var(--ink)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:1.15rem}
@media(max-width:900px){.cols{grid-template-columns:1fr}}
pre{font-family:var(--mono);font-size:.8rem;line-height:1.6;background:var(--well);
  border:1px solid var(--line);border-radius:6px;padding:.9rem 1rem;overflow-x:auto;
  color:var(--dim)}
.kv{display:grid;grid-template-columns:170px 1fr;gap:.3rem .8rem;font-size:.88rem}
.kv dt{color:var(--faint)}
.kv dd{color:var(--ink);margin:0}
.filters{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:0 0 .8rem}
.filters select,.filters input,.filters button{background:var(--well);color:var(--ink);
  border:1px solid var(--line);border-radius:5px;font-family:var(--sans);
  font-size:.85rem;padding:.4rem .7rem}
.filters button{cursor:pointer;border-color:var(--gold-dim);color:var(--gold)}
.filters .clear{color:var(--dim);font-size:.85rem;text-decoration:none;padding:.4rem}
.filters .clear:hover{color:var(--ink)}
.note{font-size:.8rem;color:var(--faint);margin:.6rem 0}
.note code{font-family:var(--mono)}
td.num,.num{color:var(--dim);font-family:var(--mono)}
h2 .num{font-size:1rem}
.bar-row{margin:0 0 1rem}
.barhead{display:flex;gap:.6rem;align-items:baseline;margin-bottom:.15rem}
.figures{font-size:.8rem;color:var(--dim);margin-bottom:.3rem}
.figures b{color:var(--ink);font-weight:500}
.bar{height:14px;background:var(--well);border:1px solid var(--line);border-radius:4px;
  overflow:hidden;display:flex}
.bar i{display:block;height:100%}
.b-used{background:var(--dim)}
.b-res{background:var(--review)}
.legend{font-size:.75rem;color:var(--faint);display:flex;gap:1.1rem;margin-bottom:.9rem;
  align-items:center}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:.3rem;
  border:1px solid var(--line)}
.kswitch p{margin:.4rem 0}
.diff{border-left:3px solid var(--line);padding:.5rem .9rem;margin:.5rem 0}
.diff .was{color:var(--dim);font-size:.88rem}
.diff .becomes{color:var(--ink);font-size:.88rem}
.diff b{color:var(--faint);font-weight:600;font-size:.72rem;text-transform:uppercase;
  letter-spacing:.1em;margin-right:.4rem}
.problems{list-style:none;padding:0;font-size:.9rem}
.problems li{padding:.35rem 0;border-bottom:1px solid var(--line)}
.honesty{font-style:italic}
.flips{list-style:none;padding:0;margin:.5rem 0}
.flips li{padding:.25rem 0;display:flex;gap:.6rem;align-items:center}
.bigdigest{font-family:var(--mono);font-size:1.05rem;letter-spacing:.02em;color:var(--ink);
  word-break:break-all;background:var(--well);border:1px solid var(--gold-dim);
  border-radius:6px;padding:.8rem 1rem;margin:.6rem 0}
.sealbtn{display:inline-flex;align-items:center;gap:.6rem;background:none;
  border:1px solid var(--gold);color:var(--gold);font-family:var(--serif);font-size:1rem;
  padding:.65rem 1.6rem;border-radius:4px;cursor:pointer;letter-spacing:.06em;
  text-decoration:none}
.sealbtn:hover{background:rgba(201,162,39,.08)}
.create-block input{background:var(--well);color:var(--ink);border:1px solid var(--line);
  border-radius:5px;font-family:var(--sans);font-size:.9rem;padding:.45rem .7rem;
  min-width:22rem;max-width:100%}
.create-block button,.panel form button{background:var(--well);color:var(--ink);
  border:1px solid var(--gold-dim);border-radius:5px;font-family:var(--sans);
  font-size:.9rem;padding:.45rem 1rem;cursor:pointer;margin-left:.4rem}
.panel form input{background:var(--well);color:var(--ink);border:1px solid var(--line);
  border-radius:5px;font-family:var(--sans);font-size:.9rem;padding:.45rem .7rem;
  min-width:22rem;max-width:100%}
.voice blockquote{margin:.5rem 0;padding:.6rem 1rem;border-left:3px solid var(--dim);
  background:var(--well);font-family:var(--serif);font-size:1rem;color:var(--ink)}
.then-now{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin-top:.8rem}
@media(max-width:900px){.then-now{grid-template-columns:1fr}}
.then-now .cell{background:var(--well);border:1px solid var(--line);border-radius:6px;
  padding:.7rem .9rem}
.cell h5{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);
  margin-bottom:.4rem;font-weight:600}
.cell p{margin:.25rem 0}
.field{margin:0 0 .8rem}
.field label{display:block;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--faint);margin-bottom:.25rem}
.field input[type=text],.field select{background:var(--well);color:var(--ink);
  border:1px solid var(--line);border-radius:5px;font-family:var(--sans);font-size:.9rem;
  padding:.4rem .7rem;width:100%;max-width:100%}
.field input[type=checkbox]{width:auto}
.field .note{margin:.25rem 0 0}
textarea{background:var(--well);color:var(--ink);border:1px solid var(--line);
  border-radius:6px;font-family:var(--mono);font-size:.82rem;line-height:1.6;
  padding:.8rem 1rem;width:100%;resize:vertical}
/* F-H's empty-store advice. Configuration advice, NOT a verdict: it gets its own
   weight from a border and a surface, never from the semantic triple -- and never from
   the brand accent either (R056 §4). It must look different from an ordinary empty
   state, because it is telling the operator something is wrong with their setup. */
.store-warning{border-left:3px solid var(--ink);background:var(--panel2);
  color:var(--ink);font-style:normal}
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


COPY_SCRIPT = (
    "(function(){"
    "if(!navigator.clipboard)return;"
    "for(const el of document.querySelectorAll('[data-digest]')){"
    "el.classList.add('copyable');"
    "el.addEventListener('click',function(){"
    "navigator.clipboard.writeText(el.dataset.digest).then(function(){"
    "el.classList.add('copied');"
    "setTimeout(function(){el.classList.remove('copied')},1200)"
    "})"
    "})"
    "}"
    "})();"
)
"""Copy-on-click, as progressive enhancement (R057 §2).

Inline, tiny, and it touches nothing but elements the server already marked with
`data-digest`. Two properties are load-bearing and are tested rather than trusted:

1. **`copyable` is added in the same loop that attaches the handler**, so the cursor
   cannot appear over an element that will not copy.
2. **The whole thing returns early without a clipboard API**, so no cursor appears in a
   context where the call would throw.

It fetches nothing, stores nothing, and reads nothing but its own page — the header
promises that nothing leaves this machine, and a script is the most obvious way to
break that promise, so this one is short enough to read in full.
"""


LIVE_VALIDATE_SCRIPT = (
    "(function(){"
    "var box=document.getElementById('raw-pane');"
    "var out=document.getElementById('validation');"
    "if(!box||!out||!window.fetch)return;"
    "var url=box.dataset.validate;"
    "if(!url)return;"
    "var timer=null;"
    "box.addEventListener('input',function(){"
    "clearTimeout(timer);"
    "timer=setTimeout(function(){"
    "fetch(url,{method:'POST',"
    "headers:{'Content-Type':'application/x-www-form-urlencoded'},"
    "body:'raw='+encodeURIComponent(box.value)})"
    ".then(function(r){return r.text()})"
    ".then(function(html){out.innerHTML=html})"
    ".catch(function(){})"
    "},400)"
    "})"
    "})();"
)
"""Live validation, as progressive enhancement (ND-056/T1).

**It parses nothing.** It reads a textarea, posts the text, and replaces a container with
HTML the server rendered. Every judgement in that HTML was made by the engine's own
loader on the server, which is the whole design: R063 §1 syncs the panes through the
server *because the server owns the only parser*, and a browser-side mirror of that
parser would be a second implementation in a second language, disagreeing first on
exactly the inputs this engine is careful about — decimal strings, unicode, key order,
`null` against absent.

`tests/studio/test_no_parser_in_the_browser.py` holds that structurally: this script may
not contain YAML vocabulary or policy field names.

With scripting off, the page is exactly what V7 shipped — the round trip on save is the
fallback, and it renders the same fragment from the same function. The failure branch is
deliberately silent: a validation panel that could not refresh must keep showing the last
answer the SERVER gave, never a client-side guess about why the fetch failed.
"""


DECLARED_SCRIPTS = (COPY_SCRIPT, LIVE_VALIDATE_SCRIPT)
"""Every script the Studio serves, declared in one place.

The allow-list tests read this rather than naming scripts one at a time — a vocabulary
half-derived and half-typed drifts from both ends (R057 §6). Adding a script without
adding it here fails the law tests, which is the point: the list is the declaration, and
a script nobody declared is a script nobody read.
"""

PAGE_SCRIPT = "".join(DECLARED_SCRIPTS)
"""What actually lands in the single `<script>` tag."""


def css() -> str:
    """The full stylesheet: pinned tokens, then the shell's own rules."""
    return tokens.root_css() + _CSS


PROPOSE_TAB = Tab("propose", "Propose", "/propose", True, "T3")
"""ND-056/T3's tab, and it is NOT in `TABS`.

Wall 4: with no model endpoint configured the feature is **absent from the UI, not
broken in it**. So the tab is added to the bar only when a proposer exists, and every
page computes its own bar from the state it was rendered with. A tab that rendered
always and 404'd when clicked would be the right-typed lie as navigation.
"""


def tabs_with_propose(configured: bool) -> tuple[Tab, ...]:
    """The tab bar for this deployment. One place, so no page can disagree with another."""
    return (*TABS, PROPOSE_TAB) if configured else TABS


def render(
    *,
    body: str,
    banner: Banner,
    active: str,
    title: str = "onedoor policy studio",
    tabs: tuple[Tab, ...] | None = None,
) -> str:
    """A complete Studio page. `body` is already-escaped HTML from a screen module."""
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{css()}</style></head><body>"
        f"{header_html(banner)}{nav_html(active, tabs)}"
        f"<main>{body}</main>"
        f"<footer>{escape(LOOPBACK_LINE)}</footer>"
        f"<script>{PAGE_SCRIPT}</script>"
        "</body></html>"
    )
