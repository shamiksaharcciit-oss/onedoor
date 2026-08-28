"""The Studio **as it is actually served** (F-A, from the 0.6.0 operator validation).

**These tests reach the app the way a browser does**, through `TestClient`, and that is
the entire point of the file. `tests/studio/test_canvas.py` exercises the same code by
calling `server.view(...)` directly and passes — while `GET /` returned *Internal Server
Error* deterministically for the first operator who ran it.

The gap between those two facts is R048's law one layer up: **a gate is a command and the
world it runs in**, and here *the route function* and *the route under uvicorn's
threadpool* are different worlds. A library call happens on the calling thread; a sync
`def` route is run by FastAPI in a **threadpool**, a different thread per request — and
`sqlite3`'s default `check_same_thread=True` raises the moment a connection built at
startup is touched from one.

So the rule this file exists to enforce: **a served surface is tested through the server.**
Testing the function it calls is testing something else that happens to share a name.

Every test here fails against the code as shipped in `0.6.0`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi", reason="the Studio server needs onedoor[studio]")
from fastapi.testclient import TestClient  # noqa: E402

from onedoor.guardrail import policy_loader  # noqa: E402
from onedoor.guardrail.models import Bounds, Policy, Tier  # noqa: E402
from onedoor.studio import server  # noqa: E402


@pytest.fixture
def studio_client(tmp_path: Path) -> TestClient:
    """A real Studio app over real stores, reached over HTTP like a browser reaches it."""
    enforcer = tmp_path / "onedoor.db"
    state = server.open_state(str(enforcer), str(tmp_path / "studio.db"))
    policy_loader.upsert(
        state.enforcer,
        Policy(
            action_type="demo.restore",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    app = server.create_app(state)
    with TestClient(app) as client:
        yield client
    state.close()


def test_the_index_page_renders_over_http(studio_client: TestClient) -> None:
    """F-A, the blocker: `GET /` returned Internal Server Error for the first operator.

    `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in
    that same thread` — the connection is built once at startup and every route is a sync
    `def`, so FastAPI runs it in a threadpool and the connection is touched from a
    different thread than the one that made it.
    """
    response = studio_client.get("/")
    assert response.status_code == 200, (
        f"GET / returned {response.status_code}. The Studio's stores must be opened for "
        "cross-thread use and serialised, exactly as onedoor.service already does."
    )
    assert "onedoor policy studio" in response.text


def test_a_draft_can_be_created_and_viewed_over_http(studio_client: TestClient) -> None:
    """The whole canvas flow, through the server rather than through library calls."""
    created = studio_client.post("/draft", params={"title": "operator draft"})
    assert created.status_code == 200, created.text
    draft_id = created.json()["draft_id"]

    page = studio_client.get(f"/draft/{draft_id}")
    assert page.status_code == 200, page.text
    assert "operator draft" in page.text
    assert "coverage" in page.text.lower() or "problems found" in page.text


def test_repin_works_over_http(studio_client: TestClient) -> None:
    draft_id = studio_client.post("/draft", params={"title": "d"}).json()["draft_id"]
    response = studio_client.post(f"/draft/{draft_id}/repin")
    assert response.status_code == 200, response.text
    assert "base_version" in response.json()


def test_a_missing_draft_is_a_404_not_a_500(studio_client: TestClient) -> None:
    """A wrong id is the operator's mistake; a 500 would blame the server for it."""
    response = studio_client.get("/draft/does-not-exist")
    assert response.status_code == 404, response.text


def test_many_sequential_requests_all_succeed(studio_client: TestClient) -> None:
    """Several requests, because the threadpool hands out **different** threads.

    A single request can pass by luck if it happens to land on the creating thread. This
    makes the cross-thread case near-certain rather than hoped for.
    """
    for _ in range(8):
        assert studio_client.get("/").status_code == 200


def test_the_studio_app_reports_the_installed_version(studio_client: TestClient) -> None:
    """F-D: a name outrunning its artifact. Derived, never typed.

    The app used to self-describe as `version="0.4.x"` — a literal that was already
    wrong when `0.5.0` shipped and had no way of ever becoming right.
    """
    import onedoor

    schema = studio_client.get("/openapi.json")
    assert schema.status_code == 200
    assert schema.json()["info"]["version"] == onedoor.__version__
    assert schema.json()["info"]["version"] != "0.4.x"


# --- V1: the shell's routes, held to exactly the same standard ------------------------
#
# R055's V1 asks for the F-A regression rerun "against every new route". The reason is
# not ceremony: F-A was a *threading* fault, so it appears once a route is reached from
# a threadpool thread and never when the same code is called directly. A new route added
# without this check is a new route that has never been served.
#
# The routes are read from `shell.TABS` rather than listed here. A route added to the
# shell and forgotten here would be a route with no test, and it would look exactly like
# a route with a passing one.


def _unbuilt_paths() -> list[str]:
    from onedoor.studio import shell

    return [tab.path for tab in shell.TABS if not tab.built]


@pytest.mark.parametrize("path", _unbuilt_paths())
def test_every_shell_route_renders_over_http(studio_client: TestClient, path: str) -> None:
    """F-A, rerun per route. 200 and a page, not a 500 and not a 404."""
    response = studio_client.get(path)
    assert response.status_code == 200, f"GET {path} returned {response.status_code}"
    assert "onedoor" in response.text.lower()


@pytest.mark.parametrize("path", _unbuilt_paths())
def test_every_shell_route_survives_eight_sequential_requests(
    studio_client: TestClient, path: str
) -> None:
    """The F-A shape specifically: the fault needs more than one request to show.

    The first request may land on the thread that opened the connection. Eight is the
    count the original regression used, and it is kept rather than reduced because the
    thing being tested is a race, and a race tested once is a race not tested.
    """
    for i in range(8):
        response = studio_client.get(path)
        assert response.status_code == 200, f"request {i + 1} to {path} failed"


@pytest.mark.parametrize("path", _unbuilt_paths())
def test_an_unbuilt_section_says_so_rather_than_pretending(
    studio_client: TestClient, path: str
) -> None:
    """A route that exists so the tab bar has somewhere to point must be honest.

    Not a 404 — the section is real and is coming — and not an empty page, which reads
    as a failure. V8(f) one layer up from the button: the *page* must not overclaim
    either.
    """
    text = studio_client.get(path).text
    assert "not built yet" in text
    assert "nothing here yet" in text


def test_the_shell_reaches_both_stores_without_either_being_ratified(
    studio_client: TestClient,
) -> None:
    """The banner reads the enforcer store AND the Studio's log, on a threadpool thread.

    This fixture has a policy and no ratification, which is the three-outcome case that
    a two-state banner gets wrong — and it is reached here through the server, because
    the banner is the one part of the shell that touches sqlite on every request.
    """
    from onedoor.studio import shell

    text = studio_client.get("/history").text
    assert shell.NEVER_RATIFIED in text
    assert "1 policy" in text
    assert "0 effects" in text


def test_no_shell_page_reaches_off_the_machine(studio_client: TestClient) -> None:
    """The header promises nothing leaves this machine, on every page that shows it."""
    import re

    for path in ["/", *_unbuilt_paths()]:
        html = studio_client.get(path).text
        assert not re.findall(r"(?:href|src)\s*=\s*[\"'](?:https?:)?//", html), path
