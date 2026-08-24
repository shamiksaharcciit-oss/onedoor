"""The canvas: store, validator, pin and panels (ND-052 / S3, T1–T5).

R047 §4 named the standing this suite has to produce, and four of the six items live
here: the **bind refusal**, the wrapper reporting *problems found* **in those words**,
the **stale surfacing with both hashes**, and T5's **verbatim refusals**. The
colour-rights test is next door in `tests/viewer/test_canvas.py`, because it is a
property of the skin rather than of the model.

The fifth thing this suite holds is the line R047 §2 drew and called the one that
survives the ticket: **the enforcer's database contains no row the Studio can edit.**
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import chain, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, EffectPolicy, Policy, Tier
from onedoor.store.db import tx
from onedoor.studio import backtest, canvas, ratify, server, store, validate
from tests.conftest import FROZEN_NOW, make_request

SESSION = "operator-1"


@pytest.fixture
def studio(tmp_path: Path) -> Connection:
    conn = store.open_store(tmp_path / "studio.db")
    yield conn
    conn.close()


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


def _state(conn: Connection, studio_conn: Connection, config: EngineConfig) -> server.StudioState:
    return server.StudioState(enforcer=conn, studio=studio_conn, config=config)


# --- T2: the bind refusal, both directions ----------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5", "[::1]"])
def test_a_loopback_host_is_accepted(host: str) -> None:
    assert server.require_loopback(host) is not None


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "10.0.0.1", "studio.local"])
def test_a_non_loopback_host_is_refused_before_any_socket_exists(host: str) -> None:
    """R047 §1's hard edge. A test, not a default.

    Possession of the box is an honest credential only while the binding makes it true;
    a drift to a routable address converts it into possession of the network with
    nothing about the process looking different.
    """
    with pytest.raises(server.BindRefused) as caught:
        server.require_loopback(host)
    assert host in str(caught.value)


def test_a_hostname_is_refused_without_being_resolved() -> None:
    """A boundary that depends on what DNS said a moment ago is not a boundary.

    `localhost` is accepted as a literal exception; anything else that is not an IP
    address is refused **without a lookup**, so a hosts-file entry cannot argue its way
    past the check between the test and the bind.
    """
    with pytest.raises(server.BindRefused) as caught:
        server.require_loopback("my-laptop.local")
    assert "it is a lookup" in str(caught.value)


def test_there_is_no_flag_that_turns_the_refusal_off() -> None:
    """`serve` calls the check unconditionally: an override IS the config drift.

    Structural rather than textual. The AST is asked two things a string search cannot
    answer honestly: that the call is a **top-level statement of the function body**
    rather than one branch of something, and that `serve` grew no parameter offering to
    skip it. A future `if not insecure_allow_public:` fails here at the moment it is
    written.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(server.serve)))
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)

    def calls_guard(node: ast.AST) -> bool:
        return any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "require_loopback"
            for inner in ast.walk(node)
        )

    top_level = [stmt for stmt in func.body if calls_guard(stmt)]
    assert len(top_level) == 1, "the bind refusal is not an unconditional statement of `serve`"
    assert not isinstance(top_level[0], ast.If | ast.Try), (
        "the bind refusal is guarded — it must be unconditional"
    )
    names = {a.arg for a in func.args.args} | {a.arg for a in func.args.kwonlyargs}
    assert not (names & {"allow_public", "insecure", "force", "skip_bind_check"}), (
        f"`serve` grew an override parameter: {sorted(names)}"
    )


# --- T1: the Studio store, and the line it holds ----------------------------------


def test_the_enforcer_store_gains_no_draft_table(conn: Connection, studio: Connection) -> None:
    """R047 §2's line: the enforcer's database contains no row the Studio can edit."""
    tables = {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "policy_candidates" not in tables
    studio_tables = {
        row["name"] for row in studio.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "policy_candidates" in studio_tables


def test_the_studio_store_carries_its_own_schema_version(studio: Connection) -> None:
    """Not a number from the enforcer's migration sequence (R047 §2)."""
    version = studio.execute("SELECT version FROM studio_schema").fetchone()["version"]
    assert int(version) == store.SCHEMA_VERSION
    from onedoor.store import db as db_module

    migrations = Path(db_module.__file__).parent / "migrations"
    assert not list(migrations.glob("0019*")), (
        "migration 0019 was released back to unclaimed (R047 §2) — a table in the "
        "Studio's own file must not be written into the enforcer's history"
    )


def test_a_newer_studio_store_is_refused_not_silently_downgraded(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    conn = store.open_store(path)
    conn.execute("UPDATE studio_schema SET version=?", (store.SCHEMA_VERSION + 1,))
    conn.close()
    with pytest.raises(store.StudioStoreError) as caught:
        store.open_store(path)
    assert "shape they were not written in" in str(caught.value)


def test_a_draft_round_trips_and_is_mutable(studio: Connection) -> None:
    """Editing is the whole point; an append-only draft table would seal every keystroke."""
    draft = store.create(
        studio,
        title="tighten payments",
        policies=[_policy(cap="500")],
        base_version="a" * 64,
        now=FROZEN_NOW,
        draft_id="d1",
    )
    assert draft.policies[0].caps.eur_day == Decimal("500")
    saved = store.save(studio, "d1", policies=[_policy(cap="250")], now=FROZEN_NOW)
    assert saved.policies[0].caps.eur_day == Decimal("250")
    assert saved.base_version == "a" * 64, "an edit must not move the pin"


def test_a_draft_opens_as_a_copy_of_the_rules_in_force(
    conn: Connection, studio: Connection
) -> None:
    """Fence post one: the canvas reads the active policies and writes only to its own store."""
    active = policy_loader.current_version(conn)
    draft = canvas.open_draft_from_active(conn, studio, title="from live", now=FROZEN_NOW)
    assert draft.base_version == active
    assert {p.action_type for p in draft.policies}, "the copy is empty"

    store.save(studio, draft.draft_id, policies=[_policy(cap="1")], now=FROZEN_NOW)
    assert policy_loader.current_version(conn) == active, "editing a draft moved the live rules"


# --- T1: the collecting validator, and its honesty clause -------------------------


def test_the_validator_collects_instead_of_raising_at_the_first() -> None:
    bad_cost = Policy(
        action_type="demo.spend",
        tier=Tier.AUTO_CAPPED,
        dry_run=False,
        compensating_command="demo.restore",
        cost_param="amount_eur",
        bounds=Bounds(strict_params=False),  # cost_param not in `required`
    )
    no_reversal = Policy(
        action_type="demo.wire",
        tier=Tier.AUTO,
        dry_run=False,
        bounds=Bounds(strict_params=False),
    )
    found = validate.problems([bad_cost, no_reversal])
    assert [p.action_type for p in found] == ["demo.spend", "demo.wire"], (
        "two invalid rules must produce two problems, not one exception"
    )


def test_the_validator_is_the_engines_own_and_not_a_second_one() -> None:
    """Fence post two applies to judgements, not only to numbers.

    The message is the loader's, verbatim — so a canvas cannot drift into saying "looks
    fine" about a rule the loader will refuse at boot.
    """
    bad = Policy(
        action_type="demo.spend",
        tier=Tier.AUTO_CAPPED,
        dry_run=False,
        compensating_command="demo.restore",
        cost_param="amount_eur",
        bounds=Bounds(strict_params=False),
    )
    message = validate.problems([bad])[0].message
    with pytest.raises(ValueError) as raised:
        policy_loader.validate_policy(bad)
    assert message == str(raised.value)


def test_the_summary_says_problems_found_in_those_words() -> None:
    """R047 §4 asked for the exact wording, and it is one constant, not two strings."""
    assert validate.FOUND_WORDING == "problems found"
    assert validate.FOUND_WORDING in validate.summary([])
    assert validate.summary([]) == "problems found: 0"
    assert validate.summary([validate.Problem("a", "b")]) == "problems found: 1"


def test_the_notice_never_claims_completeness() -> None:
    """An empty list means nothing was FOUND, which is weaker and truer than nothing is wrong."""
    assert "not all problems" in validate.INCOMPLETE_NOTICE
    assert "stops at" in validate.INCOMPLETE_NOTICE
    assert "read together" in validate.INCOMPLETE_NOTICE


# --- T3: pin and surface, with both hashes ----------------------------------------


def test_a_pinned_draft_is_current_and_its_panels_are_computed(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    store.save(
        studio, draft.draft_id, policies=[*draft.policies, _policy("demo.new")], now=FROZEN_NOW
    )
    view = canvas.build(conn, studio, draft.draft_id, config=config)
    assert view.pin.state == canvas.CURRENT
    assert not view.is_stale
    assert view.panels is not None
    assert view.panels.preview.to_version


def test_a_moved_active_set_surfaces_and_names_both_hashes(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """R047 §3: a warning that names no versions is a mood, not a fact."""
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    was = draft.base_version
    policy_loader.upsert(conn, _policy(cap="9999"))  # another operator moves the rules
    now_active = policy_loader.current_version(conn)
    assert was != now_active

    view = canvas.build(conn, studio, draft.draft_id, config=config)
    assert view.pin.state == canvas.MOVED
    sentence = view.pin.sentence()
    assert "moved beneath this draft" in sentence
    assert was in sentence and now_active in sentence, (
        "the surfaced state must name both hashes, not merely report that something moved"
    )


def test_a_stale_draft_shows_no_panel_at_all(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """They go stale together and recompute together — so there is no partial screen.

    Enforced by `Panels` being one object: no code path produces one panel from a base
    the diff no longer uses, because no code path produces one panel at all.
    """
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    policy_loader.upsert(conn, _policy(cap="9999"))
    view = canvas.build(conn, studio, draft.draft_id, config=config, with_backtest=True)
    assert view.is_stale
    assert view.panels is None


def test_re_pinning_recomputes_the_panels_against_the_new_base(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    policy_loader.upsert(conn, _policy(cap="9999"))
    assert canvas.build(conn, studio, draft.draft_id, config=config).is_stale

    state = _state(conn, studio, config)
    server.repin(state, draft.draft_id)
    view = canvas.build(conn, studio, draft.draft_id, config=config)
    assert not view.is_stale
    assert view.panels is not None
    assert view.panels.computed_from == policy_loader.current_version(conn)


def test_a_fresh_store_pins_absent_and_a_first_ratification_moves_it(
    fresh: Connection, studio: Connection, config: EngineConfig
) -> None:
    """Absent is a pin, not a missing one — and absent moving to present is a move."""
    draft = store.create(
        studio,
        title="first rules",
        policies=[_policy(), _restore()],
        base_version=None,
        now=FROZEN_NOW,
        draft_id="d0",
    )
    assert draft.base_version is None
    view = canvas.build(fresh, studio, "d0", config=config)
    assert view.pin.state == canvas.CURRENT

    policy_loader.upsert(fresh, _policy(cap="42"))
    moved = canvas.build(fresh, studio, "d0", config=config)
    assert moved.pin.state == canvas.MOVED
    assert "no recorded version" in moved.pin.sentence()


# --- T4: every number comes from an engine function --------------------------------


def test_the_previewed_hash_is_the_ceremonys_and_not_the_canvass(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """Fence post two. The canvas shows `ratify.preview`'s answer, not one of its own."""
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    store.save(studio, draft.draft_id, policies=[_policy(cap="250")], now=FROZEN_NOW)
    reloaded = store.load(studio, draft.draft_id)
    assert reloaded is not None

    view = canvas.build(conn, studio, draft.draft_id, config=config)
    assert view.panels is not None
    direct = ratify.preview(conn, reloaded.policies, effects=reloaded.effects)
    assert view.panels.preview.to_version == direct.to_version


def test_the_divergence_panel_holds_three_outcomes_apart(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """Not requested, refused, ran — and none of them renders as an empty table."""
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)

    quiet = canvas.build(conn, studio, draft.draft_id, config=config)
    assert quiet.panels is not None
    assert quiet.panels.divergence.state == canvas.BACKTEST_NOT_REQUESTED

    refused = canvas.build(conn, studio, draft.draft_id, config=config, with_backtest=True)
    assert refused.panels is not None
    assert refused.panels.divergence.state == canvas.BACKTEST_REFUSED
    assert "no hash-chained rows" in (refused.panels.divergence.refusal or "")

    with tx(conn):
        chain.enable(conn)
    for amount in ("10", "20"):
        decide_and_reserve(
            make_request("demo.spend", {"amount_eur": Decimal(amount)}, cost_eur=Decimal(amount)),
            conn=conn,
            config=config,
            now=FROZEN_NOW,
        )
    server.repin(_state(conn, studio, config), draft.draft_id)
    ran = canvas.build(conn, studio, draft.draft_id, config=config, with_backtest=True)
    assert ran.panels is not None
    assert ran.panels.divergence.state == canvas.BACKTEST_RAN
    assert ran.panels.divergence.receipt is not None


def test_the_canvas_writes_nothing_to_the_enforcers_ledger(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """Fence post one, measured rather than promised."""
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    with tx(conn):
        chain.enable(conn)
    decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("10")}, cost_eur=Decimal("10")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    server.repin(_state(conn, studio, config), draft.draft_id)
    before = conn.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"]
    caps = [tuple(r) for r in conn.execute("SELECT * FROM cap_counters ORDER BY 1,2,3")]

    canvas.build(conn, studio, draft.draft_id, config=config, with_backtest=True)

    assert conn.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"] == before
    assert [tuple(r) for r in conn.execute("SELECT * FROM cap_counters ORDER BY 1,2,3")] == caps


# --- T5: the ceremony is invoked, and its refusals travel verbatim ----------------


def test_ratifying_a_draft_invokes_the_ceremony_and_seals_a_receipt(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    store.save(
        studio, draft.draft_id, policies=[*draft.policies, _policy("demo.new")], now=FROZEN_NOW
    )
    outcome = server.ratify_draft(
        _state(conn, studio, config), draft.draft_id, session=SESSION, now=FROZEN_NOW
    )
    assert outcome.ratified
    assert outcome.receipt is not None
    assert outcome.receipt.ratified_by_session == SESSION
    stored = ratify.load(conn, outcome.receipt.digest())
    assert stored is not None, "the ceremony's receipt must be sealed in the enforcer's store"


def test_a_lost_race_reaches_the_canvas_with_the_ceremonys_own_words(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """T5: verbatim, with the named reason — never flattened into "could not ratify"."""
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    policy_loader.upsert(conn, _policy(cap="9999"))  # the world moves; the draft does not re-pin

    outcome = server.ratify_draft(
        _state(conn, studio, config), draft.draft_id, session=SESSION, now=FROZEN_NOW
    )
    assert not outcome.ratified
    assert outcome.reason == ratify.REFUSED_LOST_RACE
    assert "the diff was read from" in (outcome.message or "")
    assert "could not ratify" not in (outcome.message or "").lower()


def test_the_two_citation_refusals_stay_two_at_the_canvas(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """A UI that collapses them hands back the ambiguity the ceremony refused to have."""
    state = _state(conn, studio, config)
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)

    unresolvable = server.ratify_draft(
        state, draft.draft_id, session=SESSION, backtest_digest="f" * 64, now=FROZEN_NOW
    )
    assert unresolvable.reason == ratify.REFUSED_BACKTEST_UNRESOLVABLE

    with tx(conn):
        chain.enable(conn)
    decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("10")}, cost_eur=Decimal("10")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    other = backtest.run(
        conn, [_policy(cap="777"), _restore()], config=config, provenance=backtest.LIVE
    )
    digest = backtest.store(conn, other, FROZEN_NOW)
    server.repin(state, draft.draft_id)

    mismatch = server.ratify_draft(
        state, draft.draft_id, session=SESSION, backtest_digest=digest, now=FROZEN_NOW
    )
    assert mismatch.reason == ratify.REFUSED_BACKTEST_MISMATCH
    assert mismatch.reason != unresolvable.reason


def test_an_effect_policy_survives_the_draft_round_trip(
    conn: Connection, studio: Connection, config: EngineConfig
) -> None:
    """The ceremony takes models in memory, so a draft's effects must reach it intact."""
    draft = canvas.open_draft_from_active(conn, studio, title="d", now=FROZEN_NOW)
    effects = [EffectPolicy(effect="money.egress", min_tier=Tier.CONFIRM, caps=Caps())]
    store.save(studio, draft.draft_id, policies=draft.policies, effects=effects, now=FROZEN_NOW)
    reloaded = store.load(studio, draft.draft_id)
    assert reloaded is not None
    assert reloaded.effects[0].effect == "money.egress"
    assert reloaded.effects[0].min_tier == Tier.CONFIRM
