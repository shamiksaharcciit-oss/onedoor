"""The two rendering disciplines (ND-052 / S2-T5, R045 §4.2).

**Absence is rendered, not merely null**, and **a cited backtest surfaces its
`ledger_provenance` by dereferencing** — in *every* view, which is the part that needs
structure rather than care. So the tests do not name `render_text` and `render_html`:
they iterate `RENDERERS`, and a separate test asserts that every public `render_*` in
the module is in `RENDERERS`. A third rendering added later joins these tests at the
moment it is written, not at the moment someone notices.

The same AST-guard shape as `test_every_audit_write_path_stamps_the_chain`, adopted for
the same reason: a rule pushed into structure outranks a rule kept in a checklist.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import chain, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Policy, Tier
from onedoor.store.db import tx
from onedoor.studio import backtest, fixture, ratify
from onedoor.viewer import ratification
from tests.conftest import FROZEN_NOW, make_request

MODULE = Path(ratification.__file__)
SESSION = "operator-1"


def _policy(action: str = "demo.spend", cap: str = "500") -> Policy:
    return Policy(
        action_type=action,
        tier=Tier.AUTO_CAPPED,
        dry_run=False,
        compensating_command="demo.restore",
        caps=Caps(eur_day=Decimal(cap)),
        cost_param="amount_eur",
        bounds=Bounds(strict_params=False, required=["amount_eur"]),
    )


def _restore() -> Policy:
    return Policy(
        action_type="demo.restore",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="demo.restore",
        bounds=Bounds(strict_params=False),
    )


def _chained_backtest(conn: Connection, config: EngineConfig, candidate: list[Policy]) -> str:
    """A real backtest over this store, stored here. Needs decisions, not just a chain."""
    with tx(conn):
        chain.enable(conn)
    for amount in ("10", "20"):
        decide_and_reserve(
            make_request("demo.spend", {"amount_eur": Decimal(amount)}, cost_eur=Decimal(amount)),
            conn=conn,
            config=config,
            now=FROZEN_NOW,
        )
    receipt = backtest.run(conn, candidate, config=config, provenance=backtest.LIVE)
    return backtest.store(conn, receipt, FROZEN_NOW)


def _ratified(conn: Connection, backtest_digest: str | None = None) -> ratify.RatificationView:
    receipt = ratify.ratify(
        conn,
        [_policy(), _restore()],
        expected_version=policy_loader.current_version(conn),
        ratified_by_session=SESSION,
        backtest_digest=backtest_digest,
        now=FROZEN_NOW,
    )
    return ratify.view_model(conn, receipt.sealed())


# --- The set of renderings is closed by structure ---------------------------------


def test_every_public_renderer_is_in_the_renderers_tuple() -> None:
    """The guard that makes the two disciplines below cover future views too."""
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("render_")
    }
    listed = {fn.__name__ for fn in ratification.RENDERERS}
    assert defined == listed, (
        f"a rendering exists outside RENDERERS: {sorted(defined ^ listed)}. Every view of "
        "a ratification must state an absent backtest and surface a cited one's provenance, "
        "and these tests only reach the views RENDERERS names."
    )
    assert defined, "the module defines no renderer at all"


# --- Discipline one: absence is rendered, not merely null -------------------------


@pytest.mark.parametrize("render", ratification.RENDERERS, ids=lambda fn: fn.__name__)
def test_a_ratification_without_a_backtest_says_so_on_its_face(conn: Connection, render) -> None:
    """Not by omitting a line. An omitted line reads as "nothing to report"."""
    view = _ratified(conn)
    assert view.backtest is None
    assert ratification.NO_BACKTEST_SENTENCE in render(view)


@pytest.mark.parametrize("render", ratification.RENDERERS, ids=lambda fn: fn.__name__)
def test_the_absence_statement_is_gone_when_a_backtest_is_cited(
    conn: Connection, config: EngineConfig, render
) -> None:
    """The other direction: a fix that overshoots would print it always."""
    policy_loader.upsert(conn, _policy(cap="999"))
    policy_loader.upsert(conn, _restore())
    digest = _chained_backtest(conn, config, [_policy(), _restore()])

    view = _ratified(conn, backtest_digest=digest)
    assert ratification.NO_BACKTEST_SENTENCE not in render(view)


# --- Discipline two: a cited backtest's provenance is surfaced --------------------


@pytest.mark.parametrize("render", ratification.RENDERERS, ids=lambda fn: fn.__name__)
def test_a_fixture_informed_ratification_is_visible_as_one(
    conn: Connection, config: EngineConfig, render
) -> None:
    """R045 §4.2. Legitimate, and it must not read as production-backed.

    The backtest is run against the shipped fixture ledger and its receipt is copied
    into this store, which is exactly the day-one path: nothing to backtest against
    locally, so the demo ledger stands in — labelled.
    """
    demo = fixture.open_fixture()
    try:
        receipt = backtest.run(
            demo,
            [_policy(), _restore()],
            config=config,
            provenance=backtest.FIXTURE,
        )
    finally:
        demo.close()
    digest = backtest.store(conn, receipt, FROZEN_NOW)
    assert receipt.ledger_provenance == backtest.FIXTURE

    view = _ratified(conn, backtest_digest=digest)
    assert view.backtest is not None
    assert view.backtest.provenance == "fixture"
    assert "fixture" in render(view), (
        "a fixture-informed ratification rendered without its provenance reads as a "
        "production-backed one"
    )


@pytest.mark.parametrize("render", ratification.RENDERERS, ids=lambda fn: fn.__name__)
def test_a_citation_that_does_not_resolve_is_not_rendered_as_no_citation(
    conn: Connection, render
) -> None:
    """Three states, never two: absent, unresolvable, resolved.

    A stored receipt can be exported to a store that lacks the backtest it cites. That
    is *unverifiable*, not *absent*, and the rendering must not quietly downgrade it to
    "no backtest informed this".
    """
    view = ratify.RatificationView(
        from_version=None,
        to_version="a" * 64,
        changes=ratify.Changes(added=["demo.spend"], modified=[]),
        kill_switch_engaged=False,
        ratified_by_session=SESSION,
        ratified_at="2026-01-01T00:00:00Z",
        backtest=ratify.CitedBacktest(digest="b" * 64, provenance=None),
        digest="c" * 64,
    )
    out = render(view)
    assert ratification.NO_BACKTEST_SENTENCE not in out
    assert "does not resolve" in out


# --- The rest of what every view must carry ---------------------------------------


@pytest.mark.parametrize("render", ratification.RENDERERS, ids=lambda fn: fn.__name__)
def test_every_view_shows_both_hashes(conn: Connection, render) -> None:
    """T5's line: a ratification rendered with its from/to hashes."""
    policy_loader.upsert(conn, _policy(cap="999"))
    policy_loader.upsert(conn, _restore())
    before = policy_loader.current_version(conn)
    assert before is not None
    view = _ratified(conn)
    out = render(view)
    assert before in out
    assert view.to_version in out
    assert view.to_version != before


@pytest.mark.parametrize("render", ratification.RENDERERS, ids=lambda fn: fn.__name__)
def test_every_view_says_the_session_is_declared(conn: Connection, render) -> None:
    """The field's name carries its caveat; the rendering says it in words too."""
    view = _ratified(conn)
    out = render(view)
    assert SESSION in out
    assert "declared, not authenticated" in out


@pytest.mark.parametrize("render", ratification.RENDERERS, ids=lambda fn: fn.__name__)
def test_every_view_states_the_kill_switch_state(conn: Connection, render) -> None:
    from onedoor.guardrail import killswitch

    with tx(conn):
        killswitch.set_engaged(conn, True, origin="test")
    view = _ratified(conn)
    assert "ENGAGED" in render(view)


@pytest.mark.parametrize("render", ratification.RENDERERS, ids=lambda fn: fn.__name__)
def test_an_absent_from_version_renders_as_words_not_as_a_blank(fresh: Connection, render) -> None:
    """A blank where a hash goes reads as a missing value, not as a first ratification."""
    view = _ratified(fresh)
    assert view.from_version is None
    assert "first ratification" in render(view)


def test_the_html_rendering_escapes_store_values() -> None:
    """Params are attacker-controlled elsewhere; a session string is caller-supplied here."""
    view = ratify.RatificationView(
        from_version=None,
        to_version="a" * 64,
        changes=ratify.Changes(added=["<script>alert(1)</script>"], modified=[]),
        kill_switch_engaged=False,
        ratified_by_session="<img src=x onerror=1>",
        ratified_at="2026-01-01T00:00:00Z",
        backtest=None,
        digest="c" * 64,
    )
    out = ratification.render_html(view)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "onerror" not in out or "&lt;img" in out


def test_the_renderer_forms_no_opinion_about_validity() -> None:
    """`page.py`'s law, applied to the second renderer as it is written.

    No hashing, no store: the module renders a view model someone else resolved.
    """
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not (imported & {"hashlib", "sqlite3", "onedoor.guardrail.receipt"}), (
        f"the ratification renderer reaches past its view model: {sorted(imported)}"
    )
