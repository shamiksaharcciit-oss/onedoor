"""V1 — the shell: what it states, and what it refuses to imply.

Most of these are about the second thing. A shell is mostly chrome, and chrome is where
overclaims hide: a tab that looks clickable, a cursor that promises a copy, a blank
where a fact should be. Each test below names the false impression it forbids.
"""

from __future__ import annotations

import re

import pytest

from onedoor.studio import shell

FULL = "29e85d2cbb9f4a1c7e0d3a55f61b2c8d90a4e7f3b6c1d2e5a8f9b0c3d4e5f5166"


def _banner(**kw) -> shell.Banner:
    base = dict(in_force=FULL, ratified="2026-08-27", policies=6, effects=2)
    base.update(kw)
    return shell.Banner(**base)  # type: ignore[arg-type]


def _page(**kw) -> str:
    return shell.render(body="<p>x</p>", banner=_banner(**kw), active="drafts")


# --- The version banner ---------------------------------------------------------------


def test_the_banner_states_every_field_r055_asks_for() -> None:
    html = _page()
    assert "in force" in html
    assert "ratified 2026-08-27" in html
    assert "6 policies" in html
    assert "2 effects" in html
    assert shell.LOOPBACK_LINE in html


def test_the_digest_renders_first_eight_then_last_four() -> None:
    """The design note's format, and the reason it is a format: it must be scannable
    at a glance and complete on demand."""
    assert shell.short_digest(FULL) == "29e85d2c…5166"
    html = _page()
    assert "29e85d2c…5166" in html
    assert FULL not in re.sub(r'(title|data-digest)="[^"]*"', "", html), (
        "the truncated form is what the reader sees; the full digest belongs in "
        "attributes, not in the running text"
    )


def test_the_full_digest_is_available_on_hover_and_to_a_copy_control() -> None:
    html = _page()
    assert f'title="{FULL}"' in html
    assert f'data-digest="{FULL}"' in html


def test_the_copy_cursor_is_granted_by_the_script_and_never_by_the_server() -> None:
    """R057 §2: copy-on-click returns as progressive enhancement.

    The structural guarantee V8(f) actually needs — the cursor lives on
    `.digest.copyable`, and nothing the server emits carries `copyable`. With scripting
    off there is no cursor, because there is no copy.
    """
    css = shell.css()
    cursor_rules = [r for r in css.split("}") if "cursor:copy" in r]
    assert cursor_rules, "copy-on-click is mandated by the design note; the cursor is missing"
    for rule in cursor_rules:
        selector = rule.split("{")[0]
        assert "copyable" in selector, (
            f"`{selector.strip()}` promises a copy cursor without requiring the class the "
            "script grants; a page with scripting off would show it"
        )
    classes = re.findall(r'class="([^"]*)"', _page())
    assert not [c for c in classes if "copyable" in c], (
        "the server emitted the class that grants the cursor; only the script may add it"
    )


def test_the_handler_and_the_cursor_are_granted_in_the_same_act() -> None:
    """The two must not drift apart: a class added anywhere the handler is not attached
    is the overclaim returning by a different route."""
    script = shell.COPY_SCRIPT
    grant = script.index("classList.add('copyable')")
    attach = script.index("addEventListener('click'")
    loop = script.index("for(const el of document.querySelectorAll('[data-digest]'))")
    assert loop < grant < attach, "the grant and the handler are not in one loop body"


def test_no_cursor_is_granted_where_the_clipboard_does_not_exist() -> None:
    """The capability is checked, not assumed. 127.0.0.1 is a secure context by spec,
    but an operator reaching the Studio through a tunnel under some other origin would
    otherwise get a cursor over a call that throws."""
    script = shell.COPY_SCRIPT
    assert "if(!navigator.clipboard)return;" in script
    assert script.index("navigator.clipboard)return") < script.index("copyable")


def test_the_only_script_on_the_page_is_the_one_this_module_declares() -> None:
    """A page that promises nothing leaves the machine must not run code nobody read."""
    import re as _re

    html = _page()
    scripts = _re.findall(r"<script[^>]*>(.*?)</script>", html, _re.S)
    assert scripts == [shell.COPY_SCRIPT]
    assert "src=" not in html.split("<script")[1].split(">")[0]
    for reaching_out in ("fetch(", "XMLHttpRequest", "WebSocket", "import(", "localStorage"):
        assert reaching_out not in shell.COPY_SCRIPT


# --- Redundant coding: what the contrast correction cost, made safe --------------------


def test_no_state_is_signalled_by_colour_alone() -> None:
    """**The property that replaces the delta-E floor** (R057 §5/§6).

    Lightening `--refuse` to clear WCAG AA pushed it toward `--review` under tritanopia
    (ΔE 15.1 → 2.5) and toward `--allow` under deuteranopia (18.0 → 6.5). No hex avoids
    that: the darkness that separated refuse *was* what failed the contrast requirement.

    So the guarantee moves off the number and onto the markup. Every chip carries its
    verdict as a word, which is what WCAG 1.4.1 requires and what a ΔE floor was only
    ever a proxy for. A chip rendered with a colour and no text fails here.
    """
    for state, word in shell.STATE_WORDS.items():
        markup = shell.chip(state)
        assert f"c-{state}" in markup, f"{state} carries no state class"
        text = re.sub(r"<[^>]+>", "", markup).strip()
        assert text == word, f"{state} renders as {text!r}; a colour alone is not a verdict"
        assert len(text) > 2


def test_a_chip_cannot_be_rendered_for_a_state_that_is_not_one() -> None:
    """A typo must not produce an unstyled, unlabelled span that looks like a bug."""
    with pytest.raises(ValueError, match="not one of"):
        shell.chip("allowed")


def test_every_state_token_has_a_chip_and_every_chip_has_a_token() -> None:
    """Two lists that must agree, so they are checked rather than maintained (X-14)."""
    from onedoor.studio import tokens

    assert {f"--{s}" for s in shell.STATE_WORDS} == set(tokens.STATE_TOKENS)
    css = shell.css()
    for state in shell.STATE_WORDS:
        assert f".c-{state}{{background:var(--{state}-bg);color:var(--{state})}}" in css


def test_an_unratified_store_says_so_rather_than_rendering_a_blank() -> None:
    """Three outcomes: in force, no version in force, never ratified. A blank collapses
    the second and third into "the page failed to load"."""
    html = _page(in_force=None, ratified=None, policies=0, effects=0)
    assert shell.NOTHING_IN_FORCE in html
    assert shell.NEVER_RATIFIED in html
    assert "0 policies" in html
    assert "0 effects" in html


def test_one_of_a_thing_is_not_called_one_policys() -> None:
    html = _page(policies=1, effects=1)
    assert "1 policy ·" in html
    assert "1 effect ·" in html
    assert "policys" not in html


# --- Navigation -----------------------------------------------------------------------


def test_every_screen_the_design_note_names_appears_in_the_tab_bar() -> None:
    html = shell.nav_html("drafts")
    for label in ("Policies", "Drafts", "History", "Live state", "Verify"):
        assert f">{label}<" in html


def test_a_tab_whose_screen_is_not_built_is_not_a_link() -> None:
    """V8(f): a control that cannot act must not render enabled.

    The failure this prevents is small and corrosive — an operator clicks History, gets
    a 404, and stops trusting the rest of the bar.
    """
    html = shell.nav_html("drafts")
    for tab in shell.TABS:
        if tab.built:
            continue
        assert f'href="{tab.path}"' not in html, f"{tab.label} is unbuilt and rendered as a link"
        assert f'data-tab="{tab.key}"' in html, f"{tab.label} is missing from the bar entirely"


def test_an_unbuilt_tab_names_the_stage_that_builds_it() -> None:
    """Greying something out says "not for you". Naming the stage says "not yet"."""
    html = shell.nav_html("drafts")
    assert 'title="not built yet — V3"' in html
    assert "aria-disabled" in html


def test_the_active_tab_is_marked_for_a_screen_reader_too() -> None:
    assert 'aria-current="page"' in shell.nav_html("drafts")


def test_the_top_bar_offers_no_route_to_editing_live_rules() -> None:
    """Fence-post one, restated in navigation. S2 is reachable only inside a draft."""
    assert not any(tab.key == "editor" for tab in shell.TABS)
    assert "/policies/edit" not in shell.nav_html("policies")


# --- What the page must not carry ------------------------------------------------------


def test_the_shipped_studio_carries_no_design_study_banner() -> None:
    """The mockup says "not the shipped product". This is the shipped product."""
    html = _page()
    assert "design study" not in html.lower()
    assert "not the shipped product" not in html.lower()


def test_the_page_fetches_nothing_from_anywhere() -> None:
    """The header promises nothing leaves this machine. A webfont request would make
    that sentence false in the same document that makes it."""
    html = _page()
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html)


def test_the_shell_carries_no_inline_event_handlers() -> None:
    """V1 asserted the page ran NO JavaScript. R057 §2 overruled that — R055 §3 permits
    minimal inline JS and copy-on-click is mandated — so what survives is the narrower
    rule that still holds: behaviour is attached by the one declared script, never
    sprinkled through the markup as `onclick=` attributes nobody audits as a whole.
    """
    html = _page()
    assert not re.findall(r"\son[a-z]+\s*=", html), "an inline event handler is JavaScript"


def test_the_loopback_promise_in_the_header_is_one_the_binder_keeps() -> None:
    """A claim in the chrome, checked against the code that has to make it true."""
    from onedoor.studio import server

    assert "loopback" in shell.LOOPBACK_LINE
    assert callable(server.require_loopback)
    try:
        server.require_loopback("0.0.0.0")
    except server.BindRefused:
        pass
    else:
        raise AssertionError("the header promises loopback-only and the binder allows 0.0.0.0")


def test_an_unbuilt_section_body_says_nothing_is_hidden() -> None:
    tab = next(t for t in shell.TABS if not t.built)
    body = shell.unbuilt_html(tab)
    assert "not built yet" in body
    assert tab.stage in body
    assert "nothing here yet" in body


def test_operator_supplied_text_cannot_reach_the_page_as_markup() -> None:
    """The banner's date and digest come from a store, and a store is not a trusted
    author — the Studio opens whatever file `--db` names."""
    html = shell.render(
        body="<p>x</p>",
        banner=_banner(ratified="<script>alert(1)</script>", in_force="<img onerror=x>"),
        active="drafts",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
