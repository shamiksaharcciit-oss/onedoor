"""P0 — Shamik's F-G and F-H, from the 0.6.1 Studio hands-on (R055 §2).

Both are reached **through the served app**, because both are things an operator meets in
a browser and neither would have been visible from a library call. That is the F-A lesson
applied before the fact rather than after it.

**F-G — the empty state is a dead end.** Measured before the fix: the index with no drafts
emitted 0 forms, 0 buttons, 0 inputs, 0 links; its entire body text was
*"onedoor policy studio no drafts"*. **A state with no next move is a wall, not a state.**

**F-H — the silent db-name trap.** The service defaults to `onedoor-service.db` and the
Studio's `--db` to `onedoor.db`, so pointing the Studio at the wrong file yields a working
UI over an empty store with nothing to say about it. **A wrong default that cannot be
noticed is a defect twice.**
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi", reason="the Studio server needs onedoor[studio]")
from fastapi.testclient import TestClient  # noqa: E402

from onedoor.guardrail import policy_loader  # noqa: E402
from onedoor.guardrail.models import Bounds, Policy, Tier  # noqa: E402
from onedoor.studio import server  # noqa: E402


def _policy(action: str = "demo.restore") -> Policy:
    return Policy(
        action_type=action,
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="demo.restore",
        bounds=Bounds(strict_params=False),
    )


@pytest.fixture
def empty_client(tmp_path: Path) -> TestClient:
    """A Studio over an enforcer store the engine has never touched — F-H's trap."""
    state = server.open_state(str(tmp_path / "wrong.db"), str(tmp_path / "studio.db"))
    with TestClient(server.create_app(state)) as client:
        yield client
    state.close()


@pytest.fixture
def seeded_client(tmp_path: Path) -> TestClient:
    """A Studio over a store with policies in force — the correct pairing."""
    state = server.open_state(str(tmp_path / "right.db"), str(tmp_path / "studio.db"))
    policy_loader.upsert(state.enforcer, _policy())
    with TestClient(server.create_app(state)) as client:
        yield client
    state.close()


# --- F-G: the empty state offers a next move --------------------------------------


def test_the_empty_index_offers_a_way_to_create_a_draft(seeded_client: TestClient) -> None:
    """The defect verbatim: 0 forms, 0 inputs, 0 buttons is a wall."""
    html = seeded_client.get("/").text
    assert "no drafts" in html.lower(), "this test is about the EMPTY state"
    assert "<form" in html, "the empty state offers no form"
    assert re.search(r"name=['\"]title['\"]", html), "no title field to name a draft"
    assert "<button" in html, "no control to submit"
    # Attribute-shaped rather than spelling-shaped: this repo's markup uses single
    # quotes, and an assertion pinned to double quotes tests the renderer's punctuation
    # instead of its behaviour.
    assert re.search(r"action=['\"]/draft['\"]", html), "the form posts nowhere useful"
    assert re.search(r"method=['\"]post['\"]", html, re.I), "the form is not a POST"


def test_the_form_actually_creates_a_draft_the_way_a_browser_posts_it(
    seeded_client: TestClient,
) -> None:
    """**The test that matters.** A form that renders and does not work is worse than none.

    Posted as `application/x-www-form-urlencoded`, which is what a browser sends — not as
    the query parameter the JSON API uses. Rendering a form whose body the server ignores
    would produce a draft silently titled "untitled draft", which looks like success.
    """
    response = seeded_client.post(
        "/draft", data={"title": "quarterly refund limits"}, follow_redirects=False
    )
    assert response.status_code in (200, 303), response.text

    listing = seeded_client.get("/").text
    assert "quarterly refund limits" in listing, (
        "the form submitted but its title was ignored — the body was not read"
    )


def test_a_browser_form_lands_on_the_draft_it_created(seeded_client: TestClient) -> None:
    """A create that dumps JSON at a browser is another dead end."""
    response = seeded_client.post("/draft", data={"title": "landed"}, follow_redirects=False)
    assert response.status_code == 303, "a form submission should redirect, not return JSON"
    assert response.headers["location"].startswith("/draft/")


def test_the_json_api_is_unchanged(seeded_client: TestClient) -> None:
    """Additive, not breaking: the query-parameter API still returns JSON.

    The browser told us which caller it was by its content type; the API path is
    untouched, which is what makes this shippable inside the freeze.
    """
    response = seeded_client.post("/draft", params={"title": "via api"})
    assert response.status_code == 200
    assert "draft_id" in response.json()


def test_the_empty_state_also_gives_the_command_line(seeded_client: TestClient) -> None:
    """R055 §2: the equivalent one-liner, for the automation-minded."""
    html = seeded_client.get("/").text
    assert "curl" in html
    assert "/draft" in html


def test_a_populated_index_still_offers_the_create_affordance(
    seeded_client: TestClient,
) -> None:
    """Both directions: fixing the empty state must not make it empty-state-only."""
    seeded_client.post("/draft", data={"title": "first"}, follow_redirects=False)
    html = seeded_client.get("/").text
    assert "first" in html
    assert "<form" in html, "the create affordance vanished once a draft existed"


# --- F-H: the wrong database says so ----------------------------------------------


def test_a_store_the_engine_never_touched_says_so(empty_client: TestClient) -> None:
    """*A wrong default that cannot be noticed is a defect twice.*

    The Studio cannot know which file you meant. It can know that the one it opened has
    never held a policy, which is the observation that makes the mistake findable.
    """
    html = empty_client.get("/").text
    assert "never seen the engine" in html, "the empty enforcer store is not surfaced"
    assert "--db" in html, "the warning does not name the flag that is probably wrong"


def test_the_warning_names_both_defaults_so_the_trap_is_legible(
    empty_client: TestClient,
) -> None:
    """Naming the two filenames is what turns a warning into a diagnosis."""
    html = empty_client.get("/").text
    assert "onedoor-service.db" in html
    assert "onedoor.db" in html


def test_a_store_with_policies_carries_no_warning(seeded_client: TestClient) -> None:
    """Both directions. A warning that is always on is furniture, not a signal."""
    html = seeded_client.get("/").text
    assert "never seen the engine" not in html


def test_the_warning_is_not_a_verdict_colour(empty_client: TestClient) -> None:
    """oneview §4 binds every surface: state colours belong to verdicts.

    This is configuration advice, not a verdict about an action, so it may not borrow
    `--ok`/`--bad`.
    """
    html = empty_client.get("/").text
    styles = html.split("<style>")[1].split("</style>")[0]
    warning_rules = [r for r in styles.split("}") if ".store-warning" in r]
    assert warning_rules, "the warning has no style of its own"
    for rule in warning_rules:
        for var in ("var(--ok)", "var(--bad)"):
            assert var not in rule, f"the store warning uses {var}, which belongs to verdicts"


# --- Applies to every page this build emits ---------------------------------------


@pytest.mark.parametrize("path", ["/"])
def test_studio_pages_reference_no_external_origin(seeded_client: TestClient, path: str) -> None:
    """R055 §3: loopback-only is a product claim, so pages fetch nothing from anywhere.

    *"Nothing leaves this machine"* is false the moment a page pulls a font from a CDN,
    and it is false in a way the operator cannot see.
    """
    html = seeded_client.get(path).text
    external = re.findall(r"""(?:href|src)\s*=\s*["'](https?:)?//[^"']+""", html)
    assert not external, f"{path} references external origins: {external}"
    for banned in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn."):
        assert banned not in html
