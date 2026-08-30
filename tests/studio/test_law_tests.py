"""V8 — the law tests, applied to EVERY screen at once.

R055 V8 lists six properties this build owes across all screens. Each was enforced
per-screen as it was built; this file asks whether the discipline **generalises** or was
per-screen habit wearing a law's clothes.

R063 §6 set the expectation: *when a law test goes universal and fails on a screen that
"already enforced" it, that failure is a gift.* Anything caught here is recorded
caught-then-cleared, by name, in `TICKETS-ND-055.md`.

Every page is fetched **through the server**, because a served surface is tested through
the server (R058 §4) — and because a law that holds on a rendering function and not on
the bytes a browser receives is a law about the wrong thing.
"""

from __future__ import annotations

import ipaddress
import re
from uuid import uuid4

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    NumericBound,
    Policy,
    Source,
    Tier,
)
from onedoor.store.clock import now_utc
from onedoor.studio import api, server, shell, validate

fastapi = pytest.importorskip("fastapi", reason="the Studio server needs onedoor[studio]")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def populated(tmp_path):
    """A store with something on every screen.

    An empty store would let half these laws pass by rendering nothing, which is the
    shape of a check that reports green because it found no work.
    """
    state = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    policy_loader.upsert(
        state.enforcer,
        Policy(
            action_type="payments.transfer",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="payments.reverse",
            cost_param="amount_eur",
            caps=Caps(eur_day="100.00"),
            bounds=Bounds(
                numeric={"amount_eur": NumericBound(max="500.00")},
                required=["amount_eur"],
                strict_params=True,
            ),
        ),
    )
    request = ActionRequest(
        request_id=uuid4(),
        action_type="payments.transfer",
        params={"amount_eur": "400.00"},
        source=Source.LLM,
        rationale="law tests",
        created_at=now_utc(),
    )
    decide_and_reserve(request, conn=state.enforcer, config=state.config, now=request.created_at)

    draft = server.new_draft(state, title="a draft")
    server.save_draft(
        state,
        draft.draft_id,
        policies=[
            *draft.policies,
            Policy(
                action_type="reports.read",
                tier=Tier.OBSERVE,
                dry_run=False,
                compensating_command="",
                bounds=Bounds(strict_params=False),
            ),
        ],
        effects=list(draft.effects),
    )
    outcome = server.ratify_draft(state, draft.draft_id, session="law tests")
    second = server.new_draft(state, title="an unratified draft")

    row_id = int(
        state.enforcer.execute(
            "SELECT id FROM actions_audit WHERE kind='decision' ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]
    )
    receipt = outcome.receipt.sealed()["ratification_digest"]
    version = policy_loader.current_version(state.enforcer)

    app = server.create_app(state)
    with TestClient(app) as client:
        client.paths = [  # type: ignore[attr-defined]
            "/",
            "/policies",
            "/policies/payments.transfer",
            "/drafts",
            f"/drafts/{second.draft_id}",
            f"/drafts/{second.draft_id}/ratify",
            f"/drafts/{second.draft_id}/edit/payments.transfer",
            "/history",
            f"/history/{row_id}",
            f"/history/{row_id}?against={version}",
            "/state",
            "/verify",
            f"/verify/{receipt}",
        ]
        yield client
    state.close()


def _pages(client) -> dict[str, str]:
    out = {}
    for path in client.paths:
        response = client.get(path)
        assert response.status_code == 200, f"{path} answered {response.status_code}"
        out[path] = response.text
    return out


def test_the_universe_of_this_file_is_the_app_itself(populated) -> None:
    """**A universal test whose universe is incomplete is a per-screen test with ambition.**

    The route table is read from the running app rather than trusted from the list
    above, and that is not pedantry — the first version of this file trusted the list,
    and the list was missing `/docs`, `/redoc` and `/draft/{draft_id}`. Two of those
    served pages that broke the header's own promise; the third served a second design.
    **The laws all passed, because none of them was ever shown the pages that violated
    them.**

    Any GET route added from here on must be covered or explicitly excused by name.
    """
    served = {
        route.path for route in populated.app.routes if "GET" in getattr(route, "methods", set())
    }
    covered = set()
    for path in populated.paths:
        bare = path.split("?")[0]
        for route in served:
            template = route.strip("/").split("/")
            parts = bare.strip("/").split("/")
            if len(template) == len(parts) and all(
                t.startswith("{") or t == p for t, p in zip(template, parts, strict=True)
            ):
                covered.add(route)
    #: Routes deliberately not in the universal pass, each with the reason. A redirect
    #: emits no page to hold to a law about pages; it is covered by the test below that
    #: asserts it redirects and by the law tests on its destination.
    EXCUSED = {
        "/": "redirects to /drafts",
        "/draft/{draft_id}": "redirects to /drafts/{draft_id}",
    }
    #: ND-056/T2's JSON surface. Excused from the PAGE laws because it serves no pages —
    #: there is no seal to check, no footnote to render, no digest span to format. It is
    #: not excused from having laws: `test_every_api_route_is_held_by_the_api_laws` below
    #: enumerates exactly this set off the same route table and applies the laws that do
    #: apply to a JSON surface. An exemption that led nowhere would be the hole this
    #: whole test exists to close.
    json_surface = {r for r in served if r.startswith(api.API_ROOT)}
    missing = served - covered - set(EXCUSED) - json_surface
    assert not missing, f"these GET routes serve pages no law test has ever seen: {sorted(missing)}"
    for tab in shell.TABS:
        assert any(tab.path == p.split("?")[0] for p in populated.paths), tab.label


def test_every_api_route_is_held_by_the_api_laws(populated) -> None:
    """The JSON surface's own universal pass — the other half of its page-law excusal.

    Enumerated off the **running app**, exactly like the page pass, so a route added to
    the API without a thought still meets these. Three laws apply to a JSON surface:

    1. it answers JSON, and says so in the media type — R059 §2's whole-response honesty;
    2. it reaches no external origin, the same promise the header makes for pages;
    3. it never ratifies — the wall T2 exists inside.
    """
    served = {
        route.path
        for route in populated.app.routes
        if "GET" in getattr(route, "methods", set()) and route.path.startswith(api.API_ROOT)
    }
    assert served, "precondition: the API is mounted, or this pass is vacuous"

    draft = populated.post(api.API_ROOT + "/drafts", json={"title": "law"}).json()
    checked = 0
    for route in sorted(served):
        path = route.replace("{draft_id}", draft["draft_id"]).replace(
            "{action_type}", "payments.transfer"
        )
        response = populated.get(path)
        assert response.status_code in (200, 404), f"{path} answered {response.status_code}"
        assert response.headers["content-type"].startswith("application/json"), path
        # Every host the answer names must be this machine. Stated as the requirement
        # rather than as a ban on `//`, which matches a URL inside a sentence just as
        # readily as an origin something fetches.
        for host in re.findall(r"https?://([^/\s\"'`)]+)", response.text):
            name = host.split(":")[0]
            assert name == "localhost" or ipaddress.ip_address(name).is_loopback, (
                f"{path} names {host!r}, which is not this machine"
            )
        for marker in ('"src"', "<script", "cdn.jsdelivr.net", "fonts.googleapis.com"):
            assert marker not in response.text, f"{path} carries {marker}"
        assert "ratify" not in route, f"{route} ratifies, and the v1 API may not"
        checked += 1
    assert checked == len(served), "every API GET route was visited"


def test_the_studio_serves_no_page_it_did_not_write(populated) -> None:
    """FastAPI's auto-docs are off, and this test is why they stay off.

    `/docs` served Swagger UI from `cdn.jsdelivr.net`, `/redoc` pulled fonts from
    `fonts.googleapis.com`, and both fetched a favicon from `fastapi.tiangolo.com` — on
    a server whose header promises **nothing leaves this machine**. The promise was
    false on two live pages from V1 until V8.

    A page this project did not write is a page whose contents it cannot promise
    anything about.
    """
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert populated.get(path).status_code == 404, f"{path} is being served again"


def test_the_published_entry_points_still_work(populated) -> None:
    """README and 0.6.2's handover both tell operators to open `http://127.0.0.1:8787`.

    A link that has been published is a link that keeps working — so the legacy paths
    redirect rather than 404.
    """
    root = populated.get("/", follow_redirects=False)
    assert root.status_code == 303
    assert root.headers["location"] == "/drafts"
    legacy = populated.get("/draft/abc", follow_redirects=False)
    assert legacy.status_code == 303
    assert legacy.headers["location"] == "/drafts/abc"


def test_the_empty_store_warning_survived_the_move_to_drafts(tmp_path) -> None:
    """F-H shipped in `0.6.2` on the old `/` page. When V5 moved Drafts to `/drafts` the
    warning stayed behind on a page nothing linked to — **a shipped fix quietly stranded
    by a redesign**, and the second thing V8's universal pass caught."""
    from onedoor.viewer import canvas as canvas_skin

    state = server.open_state(str(tmp_path / "e.db"), str(tmp_path / "s.db"))
    with TestClient(server.create_app(state)) as client:
        html = client.get("/drafts").text
        assert "never seen the engine" in html
        assert "onedoor-service.db" in html and "onedoor.db" in html
        assert canvas_skin.STORE_WARNING.split(":")[0] in html
    state.close()


# --- (a) the seal never signals state -------------------------------------------------


def test_no_emitted_page_routes_a_brand_token_by_state(populated) -> None:
    """R055 V8(a), universal. The check itself landed in V1; this asks it of every page
    a browser can actually receive, stylesheet included."""
    from tests.viewer.assertions import seal_state_violations

    for path, html in _pages(populated).items():
        assert seal_state_violations(html) == [], path


def test_anchor_status_is_never_rendered_in_the_brand_accent(populated) -> None:
    """**The owed oneview §5.4 item** (R055 V8(a)).

    The vendored spec contradicts itself: §4 says seal gold never signals state, and
    §5.4 says *"anchor status in seal color."* Anchor status **is** a state — anchored,
    not anchored, unverifiable — so §4 wins and §5.4's clause does not survive it.

    The spec is core's received data and is digest-pinned, so it is **not edited**; the
    resolution is recorded here and enforced as a test, the same shape as the palette's
    corrections layer. Nothing shipped ever implemented the §5.4 clause, so this closes
    the item by proving the defect never reached a page rather than by removing it.
    """
    for path, html in _pages(populated).items():
        for rule in html.split("}"):
            if "anchor" not in rule.lower():
                continue
            selector = rule.split("{")[0]
            assert "var(--gold" not in rule and "var(--seal" not in rule, (
                f"{path}: anchor status is styled with the brand accent in `{selector.strip()}`"
            )


# --- (b) an empty state for every list view --------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/policies", "the default is denial"),
        ("/drafts", "No drafts yet"),
        ("/history", "holds no decisions yet"),
        ("/state", "Nothing is being metered"),
        ("/verify", "no ratification receipts"),
    ],
)
def test_every_list_view_has_a_designed_empty_state(tmp_path, path, expected) -> None:
    """R055 V8(b). Absent is a state to render, and a blank page reads as a failure.

    Run against a **fresh, empty store** — the only way to see an empty state is to have
    nothing, and a fixture with data would test the populated branch and call it done.
    """
    state = server.open_state(str(tmp_path / "e.db"), str(tmp_path / "s.db"))
    with TestClient(server.create_app(state)) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert expected in response.text, f"{path} has no designed empty state"
        assert '<div class="empty">' in response.text
    state.close()


# --- (c) no external origin -------------------------------------------------------------


def test_no_emitted_page_references_an_external_origin(populated) -> None:
    """R055 V8(c). The header promises nothing leaves this machine, on every page that
    carries the header — which is all of them."""
    for path, html in _pages(populated).items():
        assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html), path
        for host in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn."):
            assert host not in html, f"{path} reaches {host}"


def test_the_only_script_any_page_runs_is_the_declared_one(populated) -> None:
    """A page promising nothing leaves the machine must not run code nobody read."""
    for path, html in _pages(populated).items():
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
        assert scripts in ([], [shell.PAGE_SCRIPT]), path
        assert not re.findall(r"\son[a-z]+\s*=\s*[\"']", html), f"{path} has an inline handler"


# --- (d) the honesty footnote, verbatim -------------------------------------------------


def test_the_honesty_notice_is_verbatim_wherever_the_validator_renders(populated) -> None:
    """R055 V8(d). It follows the validator, and it is never paraphrased.

    Checked in the form the reader receives (R061 §3): the page escapes the apostrophe
    in `engine's`, which is the page being correct.
    """
    from html import escape, unescape

    pages = _pages(populated)
    showing = [p for p, html in pages.items() if "Validation" in html]
    assert showing, "no page rendered the validator, so this law tested nothing"
    for path in showing:
        html = pages[path]
        assert escape(validate.INCOMPLETE_NOTICE) in html, path
        rendered = unescape(re.sub(r"<[^>]+>", "", html))
        assert validate.INCOMPLETE_NOTICE in rendered, path


# --- (e) the digest format ----------------------------------------------------------------

_SHORT = re.compile(r"\b[0-9a-f]{8}…[0-9a-f]{4}\b")


def test_every_rendered_digest_is_truncated_and_complete_on_hover(populated) -> None:
    """R055 V8(e): 8…4, a copy handle, and the full value available.

    The rule is about *digests rendered for reading*. A 64-character value inside a
    `<pre>` is a **file** a stranger must hash — the deposition page's whole point — so
    the check looks at digest spans, not at every hex string on the page.
    """
    for path, html in _pages(populated).items():
        for span in re.findall(r"<span class=\"digest[^\"]*\"[^>]*>(.*?)</span>", html):
            text = re.sub(r"<[^>]+>", "", span)
            assert len(text) < 64, f"{path}: a digest span shows the full value: {text[:20]}"
        for attrs, shown in re.findall(r"<span class=\"digest\"([^>]*)>(.*?)</span>", html):
            assert "data-digest=" in attrs, f"{path}: a digest has no copy handle"
            assert "title=" in attrs, f"{path}: a digest is not complete on hover"
            assert _SHORT.match(shown.strip()) or len(shown.strip()) <= 13, (
                f"{path}: a digest is not rendered 8…4: {shown!r}"
            )


def test_the_digest_check_can_find_a_violation() -> None:
    """A format check that matches anything measures nothing."""
    assert _SHORT.match("29e85d2c…5166")
    assert not _SHORT.match("29e85d2c5166")


# --- (f) a control that cannot act must not render enabled ---------------------------------


def test_no_page_offers_a_control_it_cannot_honour(populated) -> None:
    """R055 V8(f), universal.

    Every `<form>` must post somewhere the app actually routes, and every `<button>`
    must sit inside one. **A button with no form is a control with no backend**, which
    is the overclaim rendered in HTML this law exists to forbid.
    """
    routes = {getattr(r, "path", "") for r in populated.app.routes}

    def routed(action: str) -> bool:
        parts = action.split("?")[0].strip("/").split("/")
        for route in routes:
            template = route.strip("/").split("/")
            if len(template) != len(parts):
                continue
            if all(t.startswith("{") or t == p for t, p in zip(template, parts, strict=True)):
                return True
        return False

    for path, html in _pages(populated).items():
        for action in re.findall(r"<form[^>]*action=\"([^\"]+)\"", html):
            assert routed(action), f"{path}: a form posts to {action}, which is not routed"
        outside = re.sub(r"<form.*?</form>", "", html, flags=re.S)
        assert "<button" not in outside, f"{path}: a button sits outside every form"


def test_an_unbuilt_tab_is_still_never_a_link(populated) -> None:
    """The same law in the navigation. Every tab is built now, so this guards the shape
    for whoever adds the next one."""
    html = shell.nav_html("policies")
    for tab in shell.TABS:
        if not tab.built:
            assert f'href="{tab.path}"' not in html, tab.label


def test_the_copy_cursor_is_still_granted_only_by_the_script(populated) -> None:
    """V8(f) one layer down, checked on the served bytes rather than on `shell.css()`."""
    for path, html in _pages(populated).items():
        classes = re.findall(r'class="([^"]*)"', html.split("<script>")[0])
        assert not [c for c in classes if "copyable" in c], (
            f"{path}: the server emitted the class that grants the copy cursor"
        )
