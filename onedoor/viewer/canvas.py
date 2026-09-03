"""The canvas's Oneview skin (ND-052 / S3-T6).

Renders `studio.canvas.CanvasView` and computes nothing — the same split that keeps
`page.py` from growing a second opinion about whether a receipt is sound.

Which parts of Oneview apply, and which do not
------------------------------------------------
Oneview §3 is a hard fence — *static HTML, read-only, no backend* — and a canvas that
edits policy violates every clause of it. **It does not apply here, and the spec says
so itself**: §1's status line puts *"Product GUIs (onedoor ND-018/ND-020 and
successors)"* explicitly out of its scope. Checked against the vendored bytes rather
than remembered, which is why it dissolved instead of becoming an escalation.

What the canvas inherits is what R046 §3's fence post named: **§4's tokens, §5's
anatomy, §2's law**. The visual language, not the delivery fence. And it inherits
`tokens.css_block()`'s behaviour with them — that function **raises** rather than
falling back to a bundled palette, which is X-6's shape: the design system is a hard
requirement of this surface, never a default it degrades past.

The two-zone colour rule (S3 §3)
----------------------------------
**State colours are verdicts' alone**, and a policy diff is not a verdict.
Green-for-added is the single most automatic choice a diff UI makes, and making it
would spend `--ok`/`--bad` — the pair that distinguishes ALLOW from DENY across three
products — on *"this line is new."*

So this module has two zones with different colour rights:

- `DIFF_ZONE` — the editor, the diff, the pin state, the problem list. **No `--ok`, no
  `--bad`.** Additions and modifications separate by `--seal`, weight and rule.
- `VERDICT_ZONE` — the backtest panel, whose counts *are* verdicts (allowed, sent to
  approval, denied). The semantic pair is exactly right there.

`tests/viewer/test_canvas.py` holds the boundary by parsing what each zone emits,
beside the two token rules `test_tokens.py` already enforces. A rule that lives in a
test is a rule; a rule that lives in a docstring is a hope.
"""

from __future__ import annotations

from html import escape

from onedoor.studio import backtest as backtest_module
from onedoor.studio import canvas as canvas_module
from onedoor.studio import store as store_module
from onedoor.studio import validate
from onedoor.viewer.tokens import root_css

STATE_COLOUR_VARS = ("--ok", "--bad", "--ok-bg", "--bad-bg", "--ok-bd", "--bad-bd")
"""The semantic pair and its surfaces. Forbidden in the diff zone, permitted in the verdict zone."""

DIFF_ZONE = "diff-zone"
VERDICT_ZONE = "verdict-zone"
"""The two zones, as CSS class names, so the test can find them in the output.

Named in the markup rather than inferred from context: a boundary a test has to guess
at is a boundary that moves the first time the markup is restructured.
"""


def _e(value: object) -> str:
    """Escape for HTML. Policy text is operator-authored and reaches this page verbatim."""
    return escape("" if value is None else str(value), quote=True)


def _hash(value: str | None) -> str:
    """A digest, full and never truncated (§5's chain-block rule), or the absent words."""
    if value is None:
        return '<span class="absent">no recorded version</span>'
    return f'<span class="mono">{_e(value)}</span>'


def _pin_block(view: canvas_module.CanvasView) -> str:
    """The moved-beneath state, naming **both** hashes.

    R047 §3: a warning that names no versions is a mood, not a fact. The sentence comes
    from `canvas.Pin`, which is where the comparison happened — this module does not
    decide whether the world moved, it renders the answer.
    """
    pin = view.pin
    classes = "pin moved" if pin.has_moved else "pin current"
    rows = (
        f"<div class='pin-hashes'>from {_hash(pin.base_version)} "
        f"to {_hash(pin.active_version)}</div>"
        if pin.has_moved
        else ""
    )
    return f"<div class='{classes}'><p>{_e(pin.sentence())}</p>{rows}</div>"


def _problems_block(view: canvas_module.CanvasView) -> str:
    """The problem list, and the notice that it is not a complete one.

    The notice renders **including when the list is empty**: "no problems found" and
    "nothing is wrong" are different claims, and only the first one is ours to make.
    """
    items = "".join(
        f"<li><span class='rule'>{_e(p.action_type)}</span> {_e(p.message)}</li>"
        for p in view.problems
    )
    listing = f"<ul class='problems'>{items}</ul>" if items else ""
    return (
        f"<section class='{DIFF_ZONE} problems-block'>"
        f"<h3>{_e(view.problems_summary)}</h3>"
        f"{listing}"
        f"<p class='notice'>{_e(validate.INCOMPLETE_NOTICE)}</p>"
        "</section>"
    )


def _changes_block(panels: canvas_module.Panels) -> str:
    """Added and modified rules. **No state colours** — this zone has no verdicts in it."""
    changes = panels.preview.changes

    def rules(kind: str, names: list[str]) -> str:
        if not names:
            return ""
        cells = "".join(f"<li class='rule'>{_e(n)}</li>" for n in sorted(names))
        return f"<div class='change {kind}'><h4>{_e(kind)}</h4><ul>{cells}</ul></div>"

    return (
        f"<section class='{DIFF_ZONE} changes-block'>"
        f"<div class='preview-hash'><span class='label'>would become</span>"
        f"{_hash(panels.preview.to_version)}</div>"
        f"<div class='preview-base'><span class='label'>computed from</span>"
        f"{_hash(panels.computed_from)}</div>"
        f"{rules('added', changes.added)}{rules('modified', changes.modified)}"
        f"{'<p>no rule changed</p>' if changes.is_empty else ''}"
        "</section>"
    )


def _divergence_block(panels: canvas_module.Panels) -> str:
    """The backtest panel — **the one zone where the semantic pair belongs**.

    Three outcomes, and none of them renders as an empty table: not requested, refused
    (in the engine's own words), ran. A canvas showing all three as "0 divergences"
    would be reporting a measurement it never took.
    """
    div = panels.divergence
    if div.state == canvas_module.BACKTEST_NOT_REQUESTED:
        return (
            f"<section class='{VERDICT_ZONE} divergence-block'>"
            "<p class='absent'>No backtest was run for this draft.</p></section>"
        )
    if div.state == canvas_module.BACKTEST_REFUSED:
        return (
            f"<section class='{VERDICT_ZONE} divergence-block'>"
            f"<p class='refused'>{_e(div.refusal)}</p></section>"
        )
    receipt = div.receipt
    assert receipt is not None  # BACKTEST_RAN carries one; the dataclass is built here
    d = receipt.divergence
    label = (
        "against the shipped demonstration ledger"
        if receipt.ledger_provenance == backtest_module.FIXTURE
        else "against this deployment's ledger"
    )
    return (
        f"<section class='{VERDICT_ZONE} divergence-block'>"
        f"<p class='provenance'>{_e(receipt.ledger_provenance)} — {_e(label)}</p>"
        f"<ul class='counts'>"
        f"<li class='ok'>allowed <b>{d.allowed}</b></li>"
        f"<li class='warn'>to approval <b>{d.to_approval}</b></li>"
        f"<li class='bad'>denied <b>{d.denied}</b></li>"
        f"</ul>"
        f"<p class='replayed'>{receipt.replayed} replayed</p>"
        "</section>"
    )


STORE_EMPTY = "This store has never seen the engine: it holds no policies at all. "
"""The observation, and the only part of the warning that is measured rather than
inferred. Both messages below open with it, so the sentence a reader must believe is
the same sentence in either case."""

STORE_WARNING_DEFAULTED = (
    STORE_EMPTY + "Did you point --db at the service's database? The decision service "
    "defaults to `onedoor-service.db` and this Studio's --db defaults to `onedoor.db`, "
    "so the two disagree unless you name one explicitly. A draft ratified here would "
    "apply to a store nothing enforces."
)
"""When `--db` was **defaulted**. Only then can the defaults mismatch be the cause, and
only then is asking about it worth the operator's attention."""

STORE_WARNING_NAMED = (
    STORE_EMPTY + "You named this store on the command line, so it is the file you "
    "meant — it is simply empty. Policies enter a store through the engine's loader, "
    "never through this Studio: run the decision service against it, or load a policy "
    "file with `policy_loader.load_file`. Until something loads rules, a draft ratified "
    "here would apply to a store nothing enforces."
)
"""When `--db` was **named**. Finding 3, R086 §2D: the old single message asked *"Did
you point --db at the service's database?"* of an operator who had just answered that
question in their own argv, and offered a defaults mismatch that their command line had
already excluded. **One condition, at least two causes, and the message named the one
that was ruled out.** The Studio cannot know which file you meant; it *can* know whether
you told it, and a message that ignores what the process already knows spends the
operator's attention on the wrong search."""

STORE_WARNING = STORE_WARNING_DEFAULTED
"""The defaulted wording, kept under its old name for callers that do not know which it
was. Retained rather than removed because a caller that cannot tell should get the
message with the extra hypothesis in it, not silence."""


def store_warning(*, db_defaulted: bool) -> str:
    """Which of the two warnings this deployment has standing to print.

    `db_defaulted` is knowledge the CLI has and no one else does, so it is threaded from
    argparse rather than guessed from the path: a path that happens to equal the default
    string was still *named*, and the operator who typed it deserves the message that
    does not doubt them.
    """
    return STORE_WARNING_DEFAULTED if db_defaulted else STORE_WARNING_NAMED


def _store_warning(active_policies: int | None, *, db_defaulted: bool = True) -> str:
    """Rendered only when the enforcer store is provably empty.

    `None` means the count was not taken, which is not the same as zero and must not
    render as a warning — absent and measured-zero are different facts.
    """
    if active_policies is None or active_policies > 0:
        return ""
    text = store_warning(db_defaulted=db_defaulted)
    return f"<section class='{DIFF_ZONE} store-warning'><p>{_e(text)}</p></section>"


def _create_form() -> str:
    """F-G. The empty state's next move, and a plain form so it needs no JavaScript.

    Posts `application/x-www-form-urlencoded` — what a browser sends — which the route
    parses with the standard library. `python-multipart` would be needed for
    `request.form()` even on urlencoded bodies, and a dependency for one field is a
    dependency the extra does not need.

    The command line sits beside it because an operator who is automating should not have
    to read the HTML to learn the route.
    """
    return (
        f"<section class='{DIFF_ZONE} create-block'>"
        "<h2>start a draft</h2>"
        "<form method='post' action='/draft'>"
        "<input name='title' placeholder='what this draft changes' "
        "aria-label='draft title' required>"
        "<button type='submit'>create draft</button>"
        "</form>"
        "<p class='cli'>or, from a terminal:</p>"
        "<pre class='cli'>curl -X POST 'http://127.0.0.1:8787/draft' "
        "--data-urlencode 'title=what this draft changes'</pre>"
        "</section>"
    )


def _draft_list(drafts: list[store_module.Draft], current: str | None) -> str:
    items = "".join(
        f"<li class='{'on' if d.draft_id == current else ''}'>"
        f"<a href='/draft/{_e(d.draft_id)}'>{_e(d.title)}</a></li>"
        for d in drafts
    )
    return f"<nav class='{DIFF_ZONE} drafts'><ul>{items or '<li>no drafts</li>'}</ul></nav>"


_PAGE_CSS = """
body{background:var(--ground);color:var(--ink);font-family:'Archivo',system-ui,sans-serif;
margin:0;padding:2rem;}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace;font-variant-numeric:tabular-nums;
word-break:break-all;}
h1,h2,h3,h4{font-weight:600;}
h1{color:var(--seal);font-size:1.1rem;letter-spacing:.08em;text-transform:uppercase;}
section{background:var(--card);border:1px solid var(--border);border-radius:6px;
padding:1rem 1.25rem;margin:1rem 0;}
.label{color:var(--faint);text-transform:uppercase;font-size:.7rem;letter-spacing:.08em;
display:block;}
.absent{color:var(--muted);font-style:italic;}
.notice{color:var(--muted);font-size:.8rem;border-top:1px solid var(--border-soft);
padding-top:.6rem;margin-top:.8rem;}
.rule{font-family:'IBM Plex Mono',ui-monospace,monospace;}
/* The diff zone separates added from modified by SEAL, weight and rule -- never by the
   semantic pair. State colours are verdicts' alone (Oneview section 4). */
.change{border-left:2px solid var(--border);padding-left:.8rem;margin:.6rem 0;}
.change.added{border-left-color:var(--seal);}
.change.modified{border-left-color:var(--seal);border-left-style:dashed;}
.change h4{color:var(--faint);text-transform:uppercase;font-size:.7rem;letter-spacing:.08em;}
.pin.moved{border-left:2px solid var(--seal);padding-left:.8rem;}
.pin-hashes{color:var(--muted);font-size:.8rem;margin-top:.4rem;}
/* The verdict zone, and the only place the semantic pair appears. */
.__VERDICT__ .counts{list-style:none;padding:0;display:flex;gap:1.5rem;}
.__VERDICT__ .counts .ok b{color:var(--ok);}
.__VERDICT__ .counts .bad b{color:var(--bad);}
.__VERDICT__ .counts .warn b{color:var(--seal);}
.drafts ul{list-style:none;padding:0;display:flex;gap:1rem;}
.drafts a{color:var(--muted);text-decoration:none;}
.drafts .on a{color:var(--ink);}
/* F-G. A next move, plainly. */
.create-block form{display:flex;gap:.6rem;align-items:center;margin:.6rem 0;}
.create-block input{background:var(--surface);color:var(--ink);border:1px solid var(--border);
border-radius:4px;padding:.5rem .7rem;font-family:inherit;font-size:.9rem;flex:1;max-width:28rem;}
.create-block button{background:var(--card-hi);color:var(--ink);border:1px solid var(--seal);
border-radius:4px;padding:.5rem 1rem;font-family:inherit;font-size:.85rem;cursor:pointer;}
.create-block .cli{color:var(--faint);font-size:.75rem;margin:.4rem 0 0;}
.create-block pre.cli{white-space:pre-wrap;word-break:break-all;}
/* F-H. Configuration advice, not a verdict: seal and rule, never the semantic pair. */
.store-warning{border-left:3px solid var(--seal);background:var(--card-hi);}
.store-warning p{margin:0;font-size:.85rem;}
"""


def render_page(
    view: canvas_module.CanvasView | None,
    *,
    drafts: list[store_module.Draft],
    active_policies: int | None = None,
) -> str:
    """The whole canvas as one HTML document.

    `root_css()` raises when the vendored spec is missing or has drifted, and this page
    does not catch it. A canvas that silently used last week's palette is the same
    failure as an instrument that drifts quietly.
    """
    # The zone class is interpolated rather than typed into the stylesheet: the CSS
    # selector and the markup's class must be the same fact, and R045 §1 ruled on what
    # happens to two names for one fact.
    css = root_css() + _PAGE_CSS.replace("__VERDICT__", VERDICT_ZONE)
    warning = _store_warning(active_policies)
    if view is None:
        body = f"<h1>onedoor policy studio</h1>{warning}{_draft_list(drafts, None)}{_create_form()}"
    else:
        panels = (
            f"{_changes_block(view.panels)}{_divergence_block(view.panels)}"
            if view.panels is not None
            else (
                f"<section class='{DIFF_ZONE} stale-block'><p>Every number on this canvas "
                "was computed against a version that is no longer in force, so none is "
                "shown. Re-pin this draft to recompute them together.</p></section>"
            )
        )
        body = (
            f"<h1>onedoor policy studio</h1>{warning}"
            f"{_draft_list(drafts, view.draft.draft_id)}"
            f"<h2>{_e(view.draft.title)}</h2>"
            f"{_pin_block(view)}{_problems_block(view)}{panels}"
            f"{_create_form()}"
        )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>onedoor policy studio</title>"
        f"<style>{css}</style></head><body>{body}</body></html>"
    )
