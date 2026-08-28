"""V1 — the shell: what it states, and what it refuses to imply.

Most of these are about the second thing. A shell is mostly chrome, and chrome is where
overclaims hide: a tab that looks clickable, a cursor that promises a copy, a blank
where a fact should be. Each test below names the false impression it forbids.
"""

from __future__ import annotations

import re

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


def test_no_copy_cursor_is_promised_while_nothing_can_copy() -> None:
    """V8(f) one layer down. This app runs no JavaScript, so a `cursor:copy` over a
    digest would be an affordance that cannot act — an overclaim rendered in CSS.

    When a working copy control lands, this test changes in the same commit as the
    cursor. Until then it holds the line.
    """
    css = shell.css()
    for rule in css.split("}"):
        if "cursor:copy" in rule:
            raise AssertionError(f"a copy cursor is promised by `{rule.split('{')[0]}`")


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


def test_the_shell_runs_no_javascript() -> None:
    html = _page()
    assert "<script" not in html.lower()
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
