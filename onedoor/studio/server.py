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
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.store.clock import now_utc
from onedoor.store.db import Database
from onedoor.studio import canvas, ratify, store

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
    """The two stores, held apart on purpose (R047 §2).

    `enforcer` is opened for reading and for the ratification ceremony, which writes
    only through the engine's own functions. `studio` holds drafts and is the only
    thing this process edits directly. **The enforcer's database contains no row the
    Studio can edit.**
    """

    enforcer: sqlite3.Connection
    studio: sqlite3.Connection
    config: EngineConfig

    def close(self) -> None:
        self.enforcer.close()
        self.studio.close()


def open_state(
    db_path: str, studio_path: str = DEFAULT_STUDIO_DB, *, config: EngineConfig | None = None
) -> StudioState:
    database = Database(db_path)
    database.init()
    return StudioState(
        enforcer=database.connect(),
        studio=store.open_store(studio_path),
        config=config or _default_config(),
    )


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


# --- Serving -----------------------------------------------------------------------


def create_app(state: StudioState) -> Any:
    """Build the ASGI app. Imports FastAPI here so the library never requires it.

    The same shape as signing's X-6 reading (R038 §2): the dependency is hard **at the
    point of use**, refused with a message naming the remedy, rather than carried by
    every reader who only ever used the engine as a library.
    """
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
    except ImportError as exc:  # pragma: no cover - exercised by the extra being absent
        raise RuntimeError(
            "the Studio server needs FastAPI: install `onedoor[studio]`. The canvas has "
            "to run engine functions to show any number at all, so there is no static "
            "fallback that would be honest."
        ) from exc

    from onedoor.viewer.canvas import render_page

    app = FastAPI(title="onedoor policy studio", version="0.4.x")
    app.state.studio = state

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return render_page(None, drafts=store.listing(state.studio))

    @app.get("/draft/{draft_id}", response_class=HTMLResponse)
    def draft_page(draft_id: str, backtest: bool = False) -> str:
        try:
            model = view(state, draft_id, with_backtest=backtest)
        except store.StudioStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return render_page(model, drafts=store.listing(state.studio))

    @app.post("/draft")
    def create_draft(title: str = "untitled draft") -> dict[str, str]:
        return {"draft_id": new_draft(state, title=title).draft_id}

    @app.post("/draft/{draft_id}/repin")
    def repin_draft(draft_id: str) -> dict[str, Any]:
        try:
            draft = repin(state, draft_id)
        except store.StudioStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"draft_id": draft.draft_id, "base_version": draft.base_version}

    @app.post("/draft/{draft_id}/ratify")
    def ratify_endpoint(draft_id: str, session: str) -> dict[str, Any]:
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
        return outcome.receipt.sealed()

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
