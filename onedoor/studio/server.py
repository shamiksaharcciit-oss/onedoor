"""The Studio server (ND-052 / S3-T2) — loopback only, and it refuses to be otherwise.

Why this is a **separate process** from `onedoor.service` (R047 §1)
--------------------------------------------------------------------
`onedoor.service` is the PDP: the machine-to-machine endpoint agents call for decisions.
An operator GUI that *changes the rules* must not live on it, because then **one leaked
credential both answers decisions and rewrites the rules those decisions are made
under**. Separating the processes makes the decide key worthless for policy-editing by
construction, rather than by an authorisation check somebody has to keep correct.

The bind refusal, and why it is a test rather than a default
--------------------------------------------------------------
Loopback-bound means *possession of the box is the credential*. That is an honest
statement — the same honesty as `ratified_by_session` naming what it actually knows —
and it is honest **only while it is true**. A config drift that binds `0.0.0.0` silently
converts possession-of-the-box into possession-of-the-network, and nothing about the
running process would look different.

So the boundary is X-6's shape: a hard requirement of the surface, refused at bind time
with a stated reason, never a default the process degrades past. `serve` raises before
a socket exists; there is no flag that turns it off, because a flag that turns it off is
the config drift.
"""

from __future__ import annotations

import ipaddress
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.store.clock import now_utc
from onedoor.store.db import Database
from onedoor.studio import (
    api,
    canvas,
    descriptions,
    drafts,
    editor,
    forecast,
    history,
    library,
    live,
    live_proposer,
    ratify,
    reevaluate,
    screens,
    shell,
    staging,
    store,
    validate,
    verify,
)
from onedoor.studio import proposer as studio_proposer

if TYPE_CHECKING:  # pragma: no cover - resolved by the type checker, not at runtime
    from fastapi import Request
else:  # pragma: no cover - which branch runs depends on whether the extra is installed
    try:
        from fastapi import Request
    except ImportError:
        # `from __future__ import annotations` makes every annotation a STRING, and
        # FastAPI resolves route annotations against the MODULE's globals -- not the
        # closure `create_app` builds them in. A `Request` imported only inside that
        # function is invisible at resolution time, so FastAPI read `request: Request`
        # as an unresolvable QUERY parameter and every browser form POST returned 422.
        #
        # So the name lives at module scope. The X-6 property is unchanged: importing
        # this module still works without FastAPI, and `create_app` still refuses with a
        # remedy -- and if it did not refuse, this import already succeeded.
        Request = object

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_STUDIO_DB = "studio.db"


class BindRefused(RuntimeError):
    """The Studio will not listen on a non-loopback address. Raised before any socket."""


def require_loopback(host: str) -> str:
    """Return `host` if it is loopback; raise with the reason if it is not.

    Accepts a literal address or the name `localhost`. A hostname that is not
    `localhost` is refused **without resolving it** — resolution is a moving target
    that a hosts file or a DNS answer can change between the check and the bind, and a
    boundary that depends on what DNS said a moment ago is not a boundary.
    """
    candidate = host.strip()
    if candidate.lower() == "localhost":
        return candidate
    try:
        address = ipaddress.ip_address(candidate.strip("[]"))
    except ValueError:
        raise BindRefused(
            f"the Studio refuses to bind {host!r}: it accepts a loopback literal or "
            "'localhost', and nothing else. A name is resolved by whatever answers at "
            "bind time, which is not a boundary — it is a lookup."
        ) from None
    if not address.is_loopback:
        raise BindRefused(
            f"the Studio refuses to bind {host!r}. Loopback-bound means possession of "
            "the box is the credential, which is an honest statement only while it is "
            "true; binding a routable address silently converts that into possession "
            "of the network. This is not a default to override — the Studio edits "
            "policy, and the PDP it edits policy for is a different process for the "
            "same reason."
        )
    return candidate


@dataclass
class StudioState:
    """The two stores, held apart on purpose (R047 §2), and safe to serve.

    `enforcer` is opened for reading and for the ratification ceremony, which writes
    only through the engine's own functions. `studio` holds drafts and is the only
    thing this process edits directly. **The enforcer's database contains no row the
    Studio can edit.**

    **Both connections are opened for cross-thread use and every route serialises on
    `lock`** — the same pair `onedoor.service` has always used, and they are a pair.
    FastAPI runs a sync `def` route in a **threadpool**, a different thread per request,
    and `sqlite3` refuses a connection touched from a thread other than its creator's.

    Found by the first operator to run `0.6.0`: `GET /` returned Internal Server Error,
    deterministically, while every library-level test passed. *A gate is a command and
    the world it runs in* — and the route function and the route under uvicorn's
    threadpool are different worlds.

    `check_same_thread=False` alone would trade a loud error for a quiet race, so the
    lock is not optional and `open_state` is the only way to build this.
    """

    enforcer: sqlite3.Connection
    studio: sqlite3.Connection
    config: EngineConfig
    lock: threading.Lock = field(default_factory=threading.Lock)
    proposer: Any | None = None
    """ND-056/T3's model-backed proposer, or `None` when none is configured.

    `None` is the default and it means the feature is ABSENT: no tab, no route, no
    mention anywhere on any page. Not a disabled control — a control that renders and
    cannot act is the right-typed lie as a button, and the Studio has refused that shape
    since V4's kill switch.
    """

    def close(self) -> None:
        self.enforcer.close()
        self.studio.close()


def open_state(
    db_path: str, studio_path: str = DEFAULT_STUDIO_DB, *, config: EngineConfig | None = None
) -> StudioState:
    database = Database(db_path)
    database.init()
    return StudioState(
        # Cross-thread on both, because both are read on FastAPI's threadpool threads.
        # `StudioState.lock` is what makes that safe rather than merely quiet.
        enforcer=database.connect(check_same_thread=False),
        studio=store.open_store(studio_path, check_same_thread=False),
        config=config or _default_config(),
        # Off by default: `from_env` returns None unless an operator configured an
        # endpoint AND a model. No bundled credentials, no default provider, and
        # explicitly no fallback to the fixture -- a demo that looks like a model and is
        # not is the failure `proposer_provenance` exists to prevent.
        proposer=live_proposer.from_env(),
    )


def tabs_for(state: StudioState) -> tuple[shell.Tab, ...]:
    """The tab bar this deployment shows. One function, so no two pages disagree."""
    return shell.tabs_with_propose(state.proposer is not None)


def derivation_for(state: StudioState, draft_id: str) -> dict[str, Any] | None:
    """The derivation record behind a draft, or `None` when a person wrote it.

    `None` is rendered as "written by hand" rather than as a blank — every draft either
    names the instrument that drafted it or was written by a person, and a blank would
    let a reader supply whichever they expected.

    A draft that NAMES a record this store cannot read returns `None` too, and that is a
    known limit rather than a hidden one: the row is append-only, so the case means the
    stores were separated after the fact. It is the one place here where absent and
    unverifiable are not yet distinguished, and it is stated so it can be fixed rather
    than discovered.
    """
    draft = store.load(state.studio, draft_id)
    if draft is None or draft.derivation_record_digest is None:
        return None
    return descriptions.load_record(state.studio, draft.derivation_record_digest)


def _default_config() -> EngineConfig:
    from zoneinfo import ZoneInfo

    return EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC")
    )


# --- The actions the canvas can take. Thin, and each one delegates. ----------------


def new_draft(state: StudioState, *, title: str, now: datetime | None = None) -> store.Draft:
    return canvas.open_draft_from_active(
        state.enforcer, state.studio, title=title, now=now or now_utc()
    )


def view(state: StudioState, draft_id: str, *, with_backtest: bool = False) -> canvas.CanvasView:
    return canvas.build(
        state.enforcer,
        state.studio,
        draft_id,
        config=state.config,
        with_backtest=with_backtest,
    )


def active_policy_count(state: StudioState) -> int:
    """How many policies the enforcer store holds. Zero is F-H's tell."""
    row = state.enforcer.execute("SELECT COUNT(*) AS n FROM policies").fetchone()
    return int(row["n"])


def effect_policy_count(state: StudioState) -> int:
    """How many effect policies the enforcer store holds."""
    row = state.enforcer.execute("SELECT COUNT(*) AS n FROM effect_policies").fetchone()
    return int(row["n"])


def banner_for(state: StudioState) -> shell.Banner:
    """What the V1 header states, resolved from the enforcer store.

    Both facts come from the **enforcer** database: `policy_loader.current_version`
    reads what is in force, and `ratifications` is an enforcer table (migration `0017`)
    because a ratification receipt is a fact about the store whose rules it changed.
    `ratify.ratify` already writes there; reading anywhere else would be reading a
    different question's answer.

    Delivery's own defect, caught here: the first version of this function passed
    `state.studio`, and every shell route raised `no such table: ratifications` on a
    fresh store. It was found by `test_every_shell_route_renders_over_http` -- through
    the server, on the first request -- and not by any of the library-level tests, which
    is F-A's lesson holding: *a served surface is tested through the server.* The
    programme rule it broke has a name too: **select on fields you have verified, not
    the record** -- `state.studio` is a Connection, `state.enforcer` is a Connection,
    and only one of them has the table.

    The date is reported only when the latest ratification is the one that produced the
    version actually in force. When it is not, the banner says so in words rather than
    printing a date belonging to a different version -- see `shell.RATIFIED_ELSEWHERE`
    and the three-outcome rule it is an instance of.
    """
    in_force = policy_loader.current_version(state.enforcer)
    latest = ratify.latest(state.enforcer)
    ratified: str | None
    if latest is None:
        ratified = None  # the log is empty; the banner's word for that is NEVER_RATIFIED
    elif str(latest.get("to_version")) == in_force:
        ratified = str(latest.get("ratified_at", ""))[:10] or None
    else:
        ratified = shell.RATIFIED_ELSEWHERE
    return shell.Banner(
        in_force=in_force,
        ratified=ratified,
        policies=active_policy_count(state),
        effects=effect_policy_count(state),
    )


def repin(state: StudioState, draft_id: str) -> store.Draft:
    """Re-pin a moved draft to the version now in force.

    Every preview computed from the old base dies with this call — not because this
    function deletes them, but because `canvas.build` recomputes `Panels` as a unit from
    whatever the pin now says. R047 §3: they go stale together and recompute together.
    """
    return store.repin(
        state.studio, draft_id, base_version=policy_loader.current_version(state.enforcer)
    )


@dataclass(frozen=True)
class RatifyOutcome:
    """Ratified, or refused **in the ceremony's own words** (T5).

    The refusal is carried verbatim with its named reason rather than flattened into
    "could not ratify". S2 gave the lost race and the two citation failures distinct
    words *because they are distinct facts with distinct remedies*, and a UI that
    collapses them hands the operator back exactly the ambiguity the ceremony refused
    to have.
    """

    ratified: bool
    receipt: ratify.Ratification | None = None
    reason: str | None = None
    message: str | None = None


def ratify_draft(
    state: StudioState,
    draft_id: str,
    *,
    session: str,
    backtest_digest: str | None = None,
    now: datetime | None = None,
) -> RatifyOutcome:
    """Invoke S2's ceremony. Never a reimplementation of it (fence post one).

    The draft's models are passed **in memory** — the ceremony takes `list[Policy]` as
    an argument and never needed a draft's address, only its content, which is what
    makes the two-store split cost nothing here.
    """
    draft = store.load(state.studio, draft_id)
    if draft is None:
        raise store.StudioStoreError(f"no draft {draft_id} in this studio store")
    try:
        receipt = ratify.ratify(
            state.enforcer,
            draft.policies,
            expected_version=draft.base_version,
            ratified_by_session=session,
            backtest_digest=backtest_digest,
            effects=draft.effects,
            now=now or now_utc(),
        )
    except ratify.RatificationRefused as exc:
        return RatifyOutcome(ratified=False, reason=exc.reason, message=str(exc))
    return RatifyOutcome(ratified=True, receipt=receipt)


def save_draft(
    state: StudioState,
    draft_id: str,
    *,
    policies: list[Any],
    effects: list[Any] | None = None,
    now: datetime | None = None,
) -> store.Draft:
    return store.save(
        state.studio, draft_id, policies=policies, effects=effects, now=now or now_utc()
    )


def known_effects(state: StudioState) -> set[str]:
    """Every effect name with an effect policy behind it, in force right now.

    Supplied to `forecast.build` so the declared-inert check can run. Read from the
    enforcer because that is where the floor either exists or does not; a candidate's own
    effects are added by `forecast.build` itself. Without this set the check is ABSENT
    rather than guessed — see `forecast.INERT_UNKNOWN`.
    """
    return {
        str(row["effect"]) for row in state.enforcer.execute("SELECT effect FROM effect_policies")
    }


def validation_for_rule(state: StudioState, text: str) -> tuple[Any, Any]:
    """Both lists for one rule's text: what the loader refuses, and what it will do.

    One function so the editor page and the live-validation fragment cannot answer
    differently — the same reason V7 syncs the panes through the server. Two callers
    computing "the same" validation two ways is the two-parser defect with extra steps.
    """
    result = staging.staged_rule(text)
    items = forecast.build(result.policies, result.effects, known_effects=known_effects(state))
    return result, items


# --- Serving -----------------------------------------------------------------------


def create_app(state: StudioState) -> Any:
    """Build the ASGI app. Imports FastAPI here so the library never requires it.

    The same shape as signing's X-6 reading (R038 §2): the dependency is hard **at the
    point of use**, refused with a message naming the remedy, rather than carried by
    every reader who only ever used the engine as a library.
    """
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse, RedirectResponse
    except ImportError as exc:  # pragma: no cover - exercised by the extra being absent
        raise RuntimeError(
            "the Studio server needs FastAPI: install `onedoor[studio]`. The canvas has "
            "to run engine functions to show any number at all, so there is no static "
            "fallback that would be honest."
        ) from exc

    import onedoor

    # DERIVED, never typed (F-D). This said `version="0.4.x"` -- a literal that was
    # already wrong when 0.5.0 shipped and had no way of ever becoming right. A name
    # outrunning its artifact, in the one field whose whole job is to say which artifact
    # this is.
    # The auto-generated API docs are OFF, and this is a correctness fix rather than a
    # preference. `/docs` serves Swagger UI from `cdn.jsdelivr.net`, `/redoc` pulls
    # fonts from `fonts.googleapis.com`, and both fetch a favicon from
    # `fastapi.tiangolo.com` -- on a server whose own header promises **"loopback only
    # -- nothing leaves this machine."** Two live pages made that promise false, and
    # every per-screen test missed them because they only ever looked at screens this
    # project wrote. V8's universal pass over the app's OWN route table found them.
    #
    # Turning them off rather than vendoring the assets: the Studio is an operator GUI
    # on loopback, not an API surface for third parties, and the JSON endpoints it does
    # have are documented in the README where they do not cost a network call.
    # `openapi_url` is ON for ND-056/T2 and `/docs`/`/redoc` stay OFF (Q12, R066 §5).
    # V8's finding had two heads: a surface nobody chose to publish, and external
    # origins pulled in to render it. T2 is a chosen surface, and the JSON schema fetches
    # nothing -- so the first head is answered by the choice and the second never applies.
    # The two HTML doc pages are the half that reached the network; they stay dark.
    app = FastAPI(
        title="onedoor policy studio",
        version=onedoor.__version__,
        description=api.NO_APPROVAL_NOTE,
        docs_url=None,
        redoc_url=None,
        openapi_url=api.OPENAPI_PATH,
    )
    app.state.studio = state

    def _refused(exc: api.ApiRefusal) -> Any:
        """A typed refusal, honest as a whole: status, media type and body together."""
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status, content=exc.body())

    def _draft_or_refuse(draft_id: str) -> Any:
        draft = store.load(state.studio, draft_id)
        if draft is None:
            raise api.ApiRefusal(
                api.NO_SUCH_DRAFT, f"there is no draft {draft_id} in this studio store"
            )
        return draft

    async def _json_body(request: Request) -> dict[str, Any]:
        """The request's JSON object, or a typed refusal. Never a guess."""
        import json

        raw = await request.body()
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise api.ApiRefusal(
                api.MALFORMED_REQUEST, f"the request body is not JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise api.ApiRefusal(
                api.MALFORMED_REQUEST,
                f"the request body must be a JSON object, got {type(payload).__name__}",
            )
        return payload

    @app.get("/")
    def index() -> Any:
        """The documented entry point, now the Studio's front door to the shell.

        Until V8 this rendered the pre-V1 canvas, so the Studio served **two designs at
        once**: the ledger-room shell behind every tab, and the old skin at `/` and
        `/draft/{id}`, reachable by anyone who kept a bookmark. The legacy pages bypassed
        every law V8 makes universal.

        Redirected rather than deleted: `README` and `0.6.2`'s handover both tell
        operators to open `http://127.0.0.1:8787`, and a link that has been published is
        a link that keeps working.
        """
        return RedirectResponse(url="/drafts", status_code=303)

    @app.get("/draft/{draft_id}")
    def legacy_draft(draft_id: str) -> Any:
        """The pre-V5 draft page. Same reasoning as `/`: published links keep working."""
        return RedirectResponse(url=f"/drafts/{draft_id}", status_code=303)

    @app.post("/draft")
    async def create_draft(request: Request, title: str = "untitled draft") -> Any:
        """Create a draft. Serves a browser form and the JSON API from one route.

        A browser sends `application/x-www-form-urlencoded`; the JSON API passes `title`
        as a query parameter. Both are read here, and **the caller's content type decides
        which answer it gets** — a form submission lands on the draft it created, an API
        call still receives JSON. Rendering a form whose body the server ignored would
        create a draft silently titled "untitled draft", which looks like success.

        Parsed with the standard library rather than `request.form()`: Starlette requires
        `python-multipart` even for urlencoded bodies, and a dependency for one text field
        is one the `[studio]` extra does not need.
        """
        from_form = "application/x-www-form-urlencoded" in (
            request.headers.get("content-type") or ""
        )
        if from_form:
            fields = parse_qs((await request.body()).decode("utf-8"))
            submitted = (fields.get("title") or [""])[0].strip()
            title = submitted or title
        with state.lock:
            draft_id = new_draft(state, title=title).draft_id
        if from_form:
            # 303: the result of a POST is a page to GO TO, not a body to re-post.
            return RedirectResponse(url=f"/draft/{draft_id}", status_code=303)
        return {"draft_id": draft_id}

    @app.get("/drafts", response_class=HTMLResponse)
    def drafts_page() -> str:
        """S3 index."""
        with state.lock:
            return shell.render(
                body=screens.drafts_body(
                    drafts.listing(state.studio),
                    policy_loader.current_version(state.enforcer),
                    active_policy_count(state),
                ),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="drafts",
                title="onedoor policy studio \u2014 drafts",
            )

    @app.post("/drafts")
    async def create_draft_v5(request: Request, title: str = "untitled draft") -> Any:
        """Same content-type dispatch F-G established: a browser gets a redirect, the
        JSON caller gets JSON, and neither learns about the other."""
        from_form = "application/x-www-form-urlencoded" in (
            request.headers.get("content-type") or ""
        )
        if from_form:
            fields = parse_qs((await request.body()).decode("utf-8"))
            submitted = (fields.get("title") or [""])[0].strip()
            title = submitted or title
        with state.lock:
            draft = new_draft(state, title=title)
        if from_form:
            return RedirectResponse(url=f"/drafts/{draft.draft_id}", status_code=303)
        return {"draft_id": draft.draft_id}

    @app.post("/drafts/upload", response_class=HTMLResponse)
    async def upload_draft(request: Request) -> Any:
        """Create a draft from an uploaded policy file (ND-056/T1).

        The bytes enter at the TOP of the loader's path, which is the point of the
        feature: until now the Studio could only ever reach `validate_policy`, because
        the editor handed it `Policy` objects that had already survived the three stages
        before it. A file that will not parse, or will not validate against the schema,
        could not be shown a problem at all.

        **A file the loader would refuse still creates a draft.** It is written to the
        Studio's store with whatever parsed, and the draft's page shows the refusals. The
        alternative -- refusing the upload -- hands the operator back their file and a
        message, which is the on-save refusal this ticket exists to replace. Nothing
        reaches the enforcer either way; a draft is not a policy set.

        The uploaded bytes are frozen verbatim (E10) before anything parses them, so what
        the operator actually sent survives independently of what this build could make
        of it.
        """
        form = await request.form()
        upload = form.get("policy_file")
        raw = await upload.read() if hasattr(upload, "read") else None  # type: ignore[union-attr]
        if not raw:
            return HTMLResponse(
                content=shell.render(
                    body=screens.upload_missing_body(),
                    banner=banner_for(state),
                    tabs=tabs_for(state),
                    active="drafts",
                    title="onedoor policy studio — upload",
                ),
                status_code=400,
            )
        filename = getattr(upload, "filename", "") or "uploaded policy"
        # Decoded for the parser, frozen as BYTES for the record. A file that is not
        # UTF-8 is a refusal at the load stage, not a crash in the route.
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return HTMLResponse(
                content=shell.render(
                    body=screens.upload_undecodable_body(str(filename), str(exc)),
                    banner=banner_for(state),
                    tabs=tabs_for(state),
                    active="drafts",
                    title="onedoor policy studio — upload",
                ),
                status_code=400,
            )

        result = staging.staged(text)
        with state.lock:
            descriptions.freeze(state.studio, text, now=now_utc())
            draft = new_draft(state, title=f"uploaded: {filename}")
            if result.policies:
                save_draft(
                    state,
                    draft.draft_id,
                    policies=list(result.policies),
                    effects=list(result.effects),
                )
        return RedirectResponse(url=f"/drafts/{draft.draft_id}?uploaded=1", status_code=303)

    @app.post("/drafts/{draft_id}/validate", response_class=HTMLResponse)
    async def validate_fragment(request: Request, draft_id: str) -> Any:
        """Live validation: the SERVER parses, and returns the rendered lists.

        R063 §1 is what shapes this route. The panes sync through the server because the
        server owns the only parser, and *they cannot drift because there is nothing to
        drift between*. Live validation must not weaken that, so the browser sends text
        and receives HTML — it never learns what a policy is.

        The fragment is built by `screens.validation_fragment`, the same function the
        editor page calls, so a keystroke and a page load render the same bytes. A second
        renderer for the "live" case would be the two-parser defect wearing HTML.
        """
        fields = parse_qs((await request.body()).decode("utf-8"))
        text = (fields.get("raw") or [""])[0]
        with state.lock:
            if store.load(state.studio, draft_id) is None:
                return HTMLResponse(
                    content=screens.validation_unavailable(draft_id), status_code=404
                )
            result, items = validation_for_rule(state, text)
        return HTMLResponse(content=screens.validation_fragment(result, items, inert_checked=True))

    @app.get("/drafts/{draft_id}", response_class=HTMLResponse)
    def draft_detail(draft_id: str, backtest: bool = False) -> Any:
        with state.lock:
            try:
                view = drafts.build(
                    state.enforcer,
                    state.studio,
                    draft_id,
                    config=state.config,
                    with_backtest=backtest,
                )
            except store.StudioStoreError:
                return _draft_missing(draft_id)
            return shell.render(
                body=screens.draft_body(view, derivation_for(state, draft_id)),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="drafts",
                title=f"onedoor policy studio \u2014 {view.draft.title}",
            )

    @app.get("/drafts/{draft_id}/ratify", response_class=HTMLResponse)
    def ceremony_page(draft_id: str) -> Any:
        """The ceremony, shown before it is performed.

        A GET that changes nothing: the operator reads what will be in force, what
        changes, and what ratifying does not undo, and only then confirms. Splitting the
        reading from the doing is the whole reason this is a page and not a button.
        """
        with state.lock:
            try:
                view = drafts.build(state.enforcer, state.studio, draft_id, config=state.config)
            except store.StudioStoreError:
                return _draft_missing(draft_id)
            return shell.render(
                body=screens.ceremony_body(view),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="drafts",
                title=f"onedoor policy studio \u2014 ratify {view.draft.title}",
            )

    @app.post("/drafts/{draft_id}/ratify", response_class=HTMLResponse)
    async def ceremony_confirm(request: Request, draft_id: str) -> Any:
        """Perform it, and render what came back \u2014 receipt or refusal, in the
        ceremony's own words."""
        fields = parse_qs((await request.body()).decode("utf-8"))
        session = (fields.get("session") or [""])[0].strip()
        if not session:
            return HTMLResponse(
                content=shell.render(
                    body=(
                        '<h2>Not ratified</h2><div class="rulebar"></div>'
                        '<div class="empty">A session note is required: it is what the '
                        "receipt records about who ratified. Nothing was applied.</div>"
                    ),
                    banner=banner_for(state),
                    tabs=tabs_for(state),
                    active="drafts",
                    title="onedoor policy studio \u2014 not ratified",
                ),
                status_code=400,
            )
        with state.lock:
            try:
                outcome = ratify_draft(state, draft_id, session=session)
            except store.StudioStoreError:
                return _draft_missing(draft_id)
            body = screens.receipt_body(outcome, draft_id)
            banner = banner_for(state)
        return HTMLResponse(
            content=shell.render(
                body=body,
                banner=banner,
                active="drafts",
                title="onedoor policy studio \u2014 ratified"
                if outcome.ratified
                else "onedoor policy studio \u2014 not ratified",
            ),
            # A refused ratification is not a server error and not a success: the
            # request was well-formed and the engine declined it. 409 is the status for
            # a state conflict, which is exactly what a moved base or a failed citation
            # is. R059 §2: status, media type and body are one statement.
            status_code=200 if outcome.ratified else 409,
        )

    @app.post("/drafts/{draft_id}/repin", response_class=HTMLResponse)
    def repin_page(draft_id: str) -> Any:
        """Re-pin a stale draft to the version in force, then show it recomputed."""
        with state.lock:
            try:
                repin(state, draft_id)
            except store.StudioStoreError:
                return _draft_missing(draft_id)
        return RedirectResponse(url=f"/drafts/{draft_id}", status_code=303)

    def _draft_missing(draft_id: str) -> Any:
        return HTMLResponse(
            content=shell.render(
                body=(
                    '<h2>Draft not found</h2><div class="rulebar"></div>'
                    f'<div class="empty">No draft <code>{escape(draft_id)}</code> exists '
                    "in this Studio store.</div>"
                ),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="drafts",
                title="onedoor policy studio \u2014 draft not found",
            ),
            status_code=404,
        )

    @app.get("/drafts/{draft_id}/edit/{action_type}", response_class=HTMLResponse)
    def editor_page(draft_id: str, action_type: str, saved: bool = False) -> Any:
        """S2, inside a draft only. Fence post one: nothing here reaches the live rules."""
        with state.lock:
            draft = store.load(state.studio, draft_id)
            if draft is None:
                return _draft_missing(draft_id)
            policy = next((p for p in draft.policies if p.action_type == action_type), None)
            if policy is None:
                return _rule_missing(draft, action_type)
            result, items = validation_for_rule(state, editor.raw_for(policy))
            return shell.render(
                body=screens.editor_body(
                    draft,
                    policy,
                    validation=screens.validation_fragment(result, items, inert_checked=True),
                    message="Both panes below are rendered from what was stored." if saved else "",
                ),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="drafts",
                title=f"onedoor policy studio \u2014 {action_type}",
            )

    @app.post("/drafts/{draft_id}/edit/{action_type}", response_class=HTMLResponse)
    async def editor_save(request: Request, draft_id: str, action_type: str) -> Any:
        """Parse whichever pane was submitted, save into the DRAFT, re-render both.

        A parse failure re-renders the page with the message and **writes nothing** --
        the operator's text is not silently dropped and the draft is not half-saved.
        """
        fields = parse_qs((await request.body()).decode("utf-8"))
        pane = (fields.get("pane") or ["form"])[0]
        with state.lock:
            draft = store.load(state.studio, draft_id)
            if draft is None:
                return _draft_missing(draft_id)
            base = next((p for p in draft.policies if p.action_type == action_type), None)
            if base is None:
                return _rule_missing(draft, action_type)
            try:
                updated = (
                    editor.policy_from_raw((fields.get("raw") or [""])[0], base=base)
                    if pane == "raw"
                    else editor.policy_from_form(fields, base=base)
                )
            except editor.EditError as exc:
                result, items = validation_for_rule(state, editor.raw_for(base))
                return HTMLResponse(
                    content=shell.render(
                        body=screens.editor_body(
                            draft,
                            base,
                            validation=screens.validation_fragment(
                                result, items, inert_checked=True
                            ),
                            error=str(exc),
                        ),
                        banner=banner_for(state),
                        tabs=tabs_for(state),
                        active="drafts",
                        title=f"onedoor policy studio \u2014 {action_type}",
                    ),
                    status_code=400,
                )
            policies = [updated if p.action_type == action_type else p for p in draft.policies]
            save_draft(state, draft_id, policies=policies, effects=list(draft.effects))
        return RedirectResponse(
            url=f"/drafts/{draft_id}/edit/{updated.action_type}?saved=1", status_code=303
        )

    def _rule_missing(draft: Any, action_type: str) -> Any:
        return HTMLResponse(
            content=shell.render(
                body=(
                    f'<h2>{escape(action_type)}</h2><div class="rulebar"></div>'
                    '<div class="empty">This draft has no rule for '
                    f"<code>{escape(action_type)}</code>.</div>"
                ),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="drafts",
                title="onedoor policy studio \u2014 rule not found",
            ),
            status_code=404,
        )

    @app.get("/verify", response_class=HTMLResponse)
    def verify_index() -> str:
        """S6: the receipts this store can hand a stranger."""
        with state.lock:
            return shell.render(
                body=screens.verify_index_body(verify.available(state.enforcer)),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="verify",
                title="onedoor policy studio \u2014 verify",
            )

    @app.get("/verify/{ratification_digest}", response_class=HTMLResponse)
    def verify_receipt(ratification_digest: str) -> Any:
        """The deposition page. Read-only, and it opens no socket."""
        with state.lock:
            dep = verify.deposition(state.enforcer, ratification_digest)
            banner = banner_for(state)
        if dep is None:
            return HTMLResponse(
                content=shell.render(
                    body=screens.deposition_missing_body(ratification_digest),
                    banner=banner,
                    active="verify",
                    title="onedoor policy studio \u2014 verify",
                ),
                status_code=404,
            )
        return shell.render(
            body=screens.deposition_body(dep),
            banner=banner,
            active="verify",
            title="onedoor policy studio \u2014 verify",
        )

    @app.get("/policies", response_class=HTMLResponse)
    def policies_page() -> str:
        """S1: the library, read from the snapshot behind the version in force."""
        with state.lock:
            model = library.build(state.enforcer)
            return shell.render(
                body=screens.library_body(model),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="policies",
                title="onedoor policy studio — policies",
            )

    @app.get("/policies/{action_type}", response_class=HTMLResponse)
    def policy_detail(action_type: str) -> Any:
        """One rule: what it does, beside what it says.

        A rule absent from the version in force answers **404**, with an honest body
        that still explains what the absence means (R058 §6).

        V2 answered 200 here, reasoning that the route is valid and the absence is a
        fact about the deployed system. Core ruled that a defect, and the reason is the
        audience: **the status code is the machine-readable verdict, and a 200 whose
        body says "not found" is the right-typed lie for machines.** Every crawler,
        cache, monitor and script reads the type and believes the page exists -- so the
        prose being honest is precisely what makes the mismatch dangerous rather than
        harmless. Both channels now say the same thing.
        """
        with state.lock:
            model = library.build(state.enforcer)
            policy = library.policy_at(state.enforcer, action_type)
            if policy is None:
                # An HTMLResponse rather than HTTPException: FastAPI serialises an
                # exception's `detail` as JSON, which would answer 404 with a
                # `content-type: application/json` body full of HTML. Fixing the status
                # code while breaking the media type just moves the lie to a different
                # header -- and the whole point of this ruling is that every
                # machine-readable channel says what the prose says.
                return HTMLResponse(
                    content=shell.render(
                        body=screens.not_found_body(action_type),
                        banner=banner_for(state),
                        tabs=tabs_for(state),
                        active="policies",
                        title=f"onedoor policy studio — {action_type}",
                    ),
                    status_code=404,
                )
            return shell.render(
                body=screens.policy_body(
                    policy,
                    model,
                    library.frozen_words(state.enforcer, state.studio, action_type),
                ),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="policies",
                title=f"onedoor policy studio — {action_type}",
            )

    @app.get("/history", response_class=HTMLResponse)
    def history_page(
        action: str = "",
        verdict: str = "",
        version: str = "",
        source: str = "",
        since: str = "",
        until: str = "",
    ) -> str:
        """S4: the execution ledger. Filters live in the query string, so an auditor can
        paste the address of what they were looking at and have it mean the same thing
        tomorrow."""
        filters = history.Filters(
            action=action,
            verdict=verdict,
            version=version,
            source=source,
            since=since,
            until=until,
        )
        with state.lock:
            return shell.render(
                body=screens.history_body(
                    history.page(state.enforcer, filters), history.choices(state.enforcer)
                ),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="history",
                title="onedoor policy studio — history",
            )

    @app.get("/history/{row_id}", response_class=HTMLResponse)
    def history_entry(row_id: int, against: str = "") -> Any:
        """One decision in full. 404 when the entry does not exist (R058 §6)."""
        with state.lock:
            row = history.entry(state.enforcer, row_id)
            if row is None:
                return HTMLResponse(
                    content=shell.render(
                        body=(
                            f'<h2>Entry {row_id}</h2><div class="rulebar"></div>'
                            '<div class="empty">No decision with this id is recorded in '
                            "this ledger.</div>"
                        ),
                        banner=banner_for(state),
                        tabs=tabs_for(state),
                        active="history",
                        title=f"onedoor policy studio — entry {row_id}",
                    ),
                    status_code=404,
                )
            comparison = (
                reevaluate.compare(state.enforcer, row, against, config=state.config)
                if against
                else None
            )
            flagship = screens.reevaluate_block(
                row, reevaluate.retrievable_versions(state.enforcer), comparison
            )
            return shell.render(
                body=screens.entry_body(row) + flagship,
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="history",
                title=f"onedoor policy studio — entry {row_id}",
            )

    @app.get("/state", response_class=HTMLResponse)
    def live_page() -> str:
        """S5: the live room. Reads the enforcer store and writes nothing to it."""
        with state.lock:
            return shell.render(
                body=screens.live_body(live.build(state.enforcer, state.config)),
                banner=banner_for(state),
                tabs=tabs_for(state),
                active="state",
                title="onedoor policy studio — live state",
            )

    # V1: every tab in the shell resolves to a route. The ones whose screens are not
    # built say so in the page rather than 404-ing -- a 404 tells the operator the
    # Studio is broken; this tells them which stage builds it. `shell.TABS` is the only
    # place that knowledge lives, so the bar and the routes cannot disagree.
    def _unbuilt(tab: shell.Tab) -> Callable[[], str]:
        def route() -> str:
            with state.lock:
                return shell.render(
                    body=shell.unbuilt_html(tab),
                    banner=banner_for(state),
                    tabs=tabs_for(state),
                    active=tab.key,
                    title=f"onedoor policy studio — {tab.label.lower()}",
                )

        route.__name__ = f"{tab.key}_page"
        return route

    for _tab in shell.TABS:
        if not _tab.built:
            app.get(_tab.path, response_class=HTMLResponse)(_unbuilt(_tab))

    # --- ND-056 / T3: natural-language authoring ------------------------------------
    #
    # Mounted ONLY when a proposer is configured. Wall 4: absent, not broken. There is no
    # route to 404 and no tab to click, because a deployment without an endpoint does not
    # have this feature rather than having a broken one.
    configured: studio_proposer.Proposer | None = state.proposer
    if configured is not None:
        # Bound to a local before the closures capture it. `state.proposer` is a mutable
        # attribute, so a narrowing on it would not survive into a route body -- and the
        # type checker is right to say so: a proposer swapped out between requests would
        # make the route's `is not None` a claim about the past.

        @app.get("/propose", response_class=HTMLResponse)
        def propose_page() -> str:
            with state.lock:
                return shell.render(
                    body=screens.propose_body(configured.identity()),
                    banner=banner_for(state),
                    tabs=tabs_for(state),
                    active="propose",
                    title="onedoor policy studio — propose",
                )

        @app.post("/propose", response_class=HTMLResponse)
        async def propose_submit(request: Request) -> Any:
            """Description in, DRAFT out. Never a policy, and never a repair.

            The model's text goes through `staging.staged` — the loader's own four
            stages — and a generation the parser refuses is rendered refused, with the
            stage that refused it and where. Nothing here rewrites the model's output to
            make it parse: that would be this code deciding what the model meant.
            """
            fields = parse_qs((await request.body()).decode("utf-8"))
            description = (fields.get("description") or [""])[0].strip()
            if not description:
                return HTMLResponse(
                    content=shell.render(
                        body=screens.propose_body(
                            configured.identity(),
                            error="No description arrived, so nothing was drafted.",
                        ),
                        banner=banner_for(state),
                        tabs=tabs_for(state),
                        active="propose",
                        title="onedoor policy studio — propose",
                    ),
                    status_code=400,
                )
            try:
                proposal, record = studio_proposer.derive(configured, description, now=now_utc())
            except live_proposer.ProposalRefused as exc:
                # The parser refused it. Shown with reasons, never auto-repaired.
                return HTMLResponse(
                    content=shell.render(
                        body=screens.proposal_refused_body(
                            configured.identity(), exc.result, exc.text
                        ),
                        banner=banner_for(state),
                        tabs=tabs_for(state),
                        active="propose",
                        title="onedoor policy studio — propose",
                    ),
                    status_code=422,
                )
            except studio_proposer.ProposerUnavailable as exc:
                # Unavailable is its OWN outcome. Telling an operator their description
                # was rejected when what failed was a socket would be a verdict about
                # content delivered about a call nothing completed.
                return HTMLResponse(
                    content=shell.render(
                        body=screens.propose_body(configured.identity(), unavailable=str(exc)),
                        banner=banner_for(state),
                        tabs=tabs_for(state),
                        active="propose",
                        title="onedoor policy studio — propose",
                    ),
                    status_code=503,
                )
            with state.lock:
                descriptions.freeze(state.studio, description, now=now_utc())
                digest = descriptions.store_record(state.studio, record, now=now_utc())
                draft = new_draft(state, title=f"proposed: {description[:48]}")
                save_draft(
                    state,
                    draft.draft_id,
                    policies=list(proposal.policies),
                    effects=list(proposal.effects),
                )
                store.set_derivation(state.studio, draft.draft_id, record_digest=digest)
            return RedirectResponse(url=f"/drafts/{draft.draft_id}?proposed=1", status_code=303)

    # --- ND-056 / T2: the policy REST API ------------------------------------------
    #
    # Same store, same parser, same refusals. Loopback-only comes free: these ride the
    # app `require_loopback` already governs, so there is no second surface to secure.

    @app.get(f"{api.API_ROOT}/drafts")
    def api_list_drafts() -> Any:
        with state.lock:
            active = policy_loader.current_version(state.enforcer)
            return {
                "drafts": [
                    api.draft_object(d, active_version=active) for d in store.listing(state.studio)
                ],
                "active_version": active,
            }

    @app.post(f"{api.API_ROOT}/drafts", status_code=201)
    async def api_create_draft(request: Request) -> Any:
        """Create a draft, optionally with rules in the same call.

        Rules go through `api.parse_rule`, so a candidate the loader would refuse is
        refused HERE with the staged reasons — never stored half-parsed and discovered
        at ratification.
        """
        try:
            payload = await _json_body(request)
            title = str(payload.get("title") or "untitled draft")
            rules = payload.get("rules") or []
            if not isinstance(rules, list):
                raise api.ApiRefusal(
                    api.MALFORMED_REQUEST, "`rules` must be a list of rule objects"
                )
            policies = [api.parse_rule(r) for r in rules]
        except api.ApiRefusal as exc:
            return _refused(exc)
        with state.lock:
            draft = new_draft(state, title=title)
            if policies:
                draft = save_draft(state, draft.draft_id, policies=policies)
            active = policy_loader.current_version(state.enforcer)
        return api.draft_object(draft, active_version=active)

    @app.get(f"{api.API_ROOT}/drafts/{{draft_id}}")
    def api_get_draft(draft_id: str) -> Any:
        with state.lock:
            try:
                draft = _draft_or_refuse(draft_id)
            except api.ApiRefusal as exc:
                return _refused(exc)
            active = policy_loader.current_version(state.enforcer)
        return api.draft_object(draft, active_version=active)

    @app.delete(f"{api.API_ROOT}/drafts/{{draft_id}}")
    def api_delete_draft(draft_id: str) -> Any:
        with state.lock:
            try:
                _draft_or_refuse(draft_id)
            except api.ApiRefusal as exc:
                return _refused(exc)
            store.delete(state.studio, draft_id)
        return {"draft_id": draft_id, "deleted": True}

    @app.put(f"{api.API_ROOT}/drafts/{{draft_id}}/rules/{{action_type}}")
    async def api_put_rule(request: Request, draft_id: str, action_type: str) -> Any:
        """Add or update ONE rule inside a draft. Everything else is left alone.

        R063 §4's law, at the API: *a partial editor that writes a whole object deletes
        what it never displayed.* The other rules are carried over rather than rebuilt,
        and a body whose `action_type` disagrees with the path is a malformed request
        rather than a silent rename.
        """
        try:
            payload = await _json_body(request)
            named = payload.get("action_type")
            if named is not None and named != action_type:
                raise api.ApiRefusal(
                    api.MALFORMED_REQUEST,
                    f"the body names action_type {named!r} and the path names "
                    f"{action_type!r}. A rename is a different act from an edit, so this "
                    "is refused rather than guessed.",
                )
            rule = api.parse_rule({**payload, "action_type": action_type})
        except api.ApiRefusal as exc:
            return _refused(exc)
        with state.lock:
            try:
                draft = _draft_or_refuse(draft_id)
            except api.ApiRefusal as exc:
                return _refused(exc)
            kept = [p for p in draft.policies if p.action_type != action_type]
            draft = save_draft(
                state,
                draft_id,
                policies=[*kept, rule],
                effects=list(draft.effects),
            )
            active = policy_loader.current_version(state.enforcer)
        return api.draft_object(draft, active_version=active)

    @app.delete(f"{api.API_ROOT}/drafts/{{draft_id}}/rules/{{action_type}}")
    def api_delete_rule(draft_id: str, action_type: str) -> Any:
        with state.lock:
            try:
                draft = _draft_or_refuse(draft_id)
                if not any(p.action_type == action_type for p in draft.policies):
                    raise api.ApiRefusal(
                        api.NO_SUCH_RULE,
                        f"draft {draft_id} has no rule for {action_type!r}",
                    )
            except api.ApiRefusal as exc:
                return _refused(exc)
            draft = save_draft(
                state,
                draft_id,
                policies=[p for p in draft.policies if p.action_type != action_type],
                effects=list(draft.effects),
            )
            active = policy_loader.current_version(state.enforcer)
        return api.draft_object(draft, active_version=active)

    @app.get(f"{api.API_ROOT}/drafts/{{draft_id}}/validation")
    def api_validation(draft_id: str) -> Any:
        """Both lists as data — the same two the editor renders, from the same functions."""
        with state.lock:
            try:
                draft = _draft_or_refuse(draft_id)
            except api.ApiRefusal as exc:
                return _refused(exc)
            result = staging.StagedResult(
                stopped_at=staging.STAGE_RULES if validate.problems(draft.policies) else None,
                refusals=tuple(
                    staging.Refusal(
                        stage=staging.STAGE_RULES,
                        action_type=p.action_type,
                        message=p.message,
                        position=staging.Position(staging.ABSENT),
                    )
                    for p in validate.problems(draft.policies)
                ),
                policies=tuple(draft.policies),
                effects=tuple(draft.effects),
            )
            items = forecast.build(
                draft.policies, draft.effects, known_effects=known_effects(state)
            )
        return api.validation_object(result, items)

    @app.post(f"{api.API_ROOT}/drafts/{{draft_id}}/submit")
    def api_submit(draft_id: str) -> Any:
        """Submit for ratification. **This approves nothing.**

        It sets a flag meaning a human has been asked, and returns where they go to
        answer. No version pointer moves, no receipt is written, and the enforcer's store
        is not touched — `test_submit_is_not_approval` asserts all three against a
        ceremony that is proven able to move them.
        """
        with state.lock:
            try:
                draft = _draft_or_refuse(draft_id)
                if draft.state == store.SUBMITTED:
                    raise api.ApiRefusal(
                        api.ALREADY_SUBMITTED,
                        f"draft {draft_id} is already submitted for ratification",
                    )
                active = policy_loader.current_version(state.enforcer)
                if draft.base_version != active:
                    raise api.ApiRefusal(
                        api.BASE_MOVED,
                        "this draft is pinned to a version that is no longer in force, "
                        "so every number computed for it is about a dead base. Re-pin "
                        "before submitting.",
                        base_version=draft.base_version,
                        active_version=active,
                    )
            except api.ApiRefusal as exc:
                return _refused(exc)
            draft = store.set_state(state.studio, draft_id, state=store.SUBMITTED)
        return {
            **api.draft_object(draft, active_version=active),
            "means": api.SUBMIT_MEANS,
            "ceremony_url": f"/drafts/{draft_id}/ratify",
        }

    @app.get(f"{api.API_ROOT}/policies")
    def api_policies() -> Any:
        """The rules in force, read from the SNAPSHOT the version names (R058 §1).

        Not from live tables. The digest in the header names the snapshot, so the
        snapshot is the only honest source for the answer under it — and the two agree
        through the normal write path and can disagree through any other, at which point
        they answer different questions.
        """
        with state.lock:
            version, policies, retrievable = _snapshot_policies()
        return {
            "version": version,
            "retrievable": retrievable,
            "policies": [api.rule_object(p) for p in policies],
            "absence_is_denial": library.ABSENCE_IS_DENIAL,
        }

    def _snapshot_policies() -> tuple[str | None, list[Any], bool]:
        """The rules behind the version in force, from that version's SNAPSHOT.

        `ratify._policies_at` rebuilds them from the archived snapshot, which is what
        makes this answer agree with the digest it is returned beside. Reading the live
        `policies` table instead would produce a set that can disagree with the version
        naming it — and then the two answer different questions while looking like one.

        The third outcome is carried: a version in force whose snapshot cannot be read is
        `retrievable: false`, never an empty list. An empty list would say *nothing is
        permitted* about a system that is permitting things.
        """
        version = policy_loader.current_version(state.enforcer)
        if version is None:
            return None, [], True
        snapshot = policy_loader.snapshot_for(state.enforcer, version)
        if snapshot is None:
            return version, [], False
        return version, ratify._policies_at(state.enforcer, version), True

    @app.get(f"{api.API_ROOT}/policies/{{action_type}}")
    def api_policy(action_type: str) -> Any:
        with state.lock:
            version, policies, retrievable = _snapshot_policies()
            found = next((p for p in policies if p.action_type == action_type), None)
        if found is None:
            return _refused(
                api.ApiRefusal(
                    api.NO_SUCH_RULE,
                    f"the version in force declares no rule for {action_type!r}. Under "
                    "default-deny, that action is refused."
                    if retrievable
                    else f"the snapshot for the version in force cannot be read, so "
                    f"whether {action_type!r} is declared is unknown — this is not a "
                    "statement that it is undeclared.",
                    retrievable=retrievable,
                )
            )
        return {"version": version, "rule": api.rule_object(found)}

    @app.get(f"{api.API_ROOT}/versions")
    def api_versions() -> Any:
        with state.lock:
            rows = state.enforcer.execute(
                "SELECT version_hash, created_at FROM policy_versions ORDER BY created_at DESC"
            ).fetchall()
            active = policy_loader.current_version(state.enforcer)
        return {
            "active_version": active,
            "versions": [
                {"version_hash": str(r["version_hash"]), "created_at": str(r["created_at"])}
                for r in rows
            ],
        }

    @app.post("/draft/{draft_id}/repin")
    def repin_draft(draft_id: str) -> dict[str, Any]:
        with state.lock:
            try:
                draft = repin(state, draft_id)
            except store.StudioStoreError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"draft_id": draft.draft_id, "base_version": draft.base_version}

    @app.post("/draft/{draft_id}/ratify", deprecated=True)
    def ratify_endpoint(draft_id: str, session: str) -> dict[str, Any]:
        """LEGACY, deprecated. Ratifies over HTTP with a DECLARED session string.

        Shipped in `ND-052`/S3-T2, undocumented and untested by path until ND-056 found
        it while checking Forward 006's "no approval-by-API" wall against the code. The
        wall was written by the author of a tree that already served this route, and V8's
        universal pass could not have caught it because no law said what a route may DO.
        That law exists now; this route is what it was written for.

        R066 §1 rules it stays through this release — launch week is the wrong week to
        break a published surface — and adds two teeth, both here:

        1. **A witness test** pins its exact current behaviour, so its retirement in the
           actor-identity release is a deliberate, tested change and never a silent one.
        2. **A deprecation field in its own response**, so a caller learns what this is
           from the thing itself rather than from documentation they never had to read.

        It records `ratified_by_session`: declared, never authenticated. The receipt is
        honest about that, which is why it was safe to leave serving and not safe to
        leave unlabelled.
        """
        with state.lock:
            try:
                outcome = ratify_draft(state, draft_id, session=session)
            except store.StudioStoreError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not outcome.ratified:
            # Verbatim, with the reason, and 409 rather than 400: the request was
            # well-formed and the world declined it.
            raise HTTPException(
                status_code=409, detail={"reason": outcome.reason, "message": outcome.message}
            )
        assert outcome.receipt is not None
        # The receipt, unchanged and under its own key, plus the deprecation notice
        # BESIDE it. Beside, never merged into it: the sealed receipt is evidence with a
        # digest over exactly these fields, and folding a notice into it would change
        # what the digest covers. Corrections annotate evidence; they do not rewrite it.
        return {**outcome.receipt.sealed(), "deprecation": api.LEGACY_DEPRECATION}

    return app


def serve(
    db_path: str,
    studio_path: str = DEFAULT_STUDIO_DB,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:  # pragma: no cover - exercised by `require_loopback` and the app tests
    """Run the Studio. Refuses a non-loopback host **before** a socket exists."""
    require_loopback(host)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("the Studio server needs uvicorn: install `onedoor[studio]`") from exc
    state = open_state(db_path, studio_path)
    try:
        uvicorn.run(create_app(state), host=host, port=port, log_level="warning")
    finally:
        state.close()
