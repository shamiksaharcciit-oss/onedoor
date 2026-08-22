"""The emitted page, and the sabotage that proves the tests would catch a lie.

R028's two mandatory tests are here, and both are **sabotage-verified**: the breakage
is applied in-process, the properties are re-checked one at a time, and the assertion
is that **exactly the intended property fails and the rest still hold**. A test that
has only ever seen correct input is a test with an unknown catch radius.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, Policy, Source, Tier
from onedoor.guardrail.receipt import Status, hero_decision, verify_decision
from onedoor.store.db import Database, tx
from onedoor.viewer import page as page_module
from onedoor.viewer.page import build_model, build_page, render
from tests.conftest import FROZEN_NOW, make_request
from tests.viewer.assertions import (
    ALL_PROPERTIES,
    PropertyViolation,
    assert_every_displayed_budget_number_matches_the_store,
    assert_every_displayed_digest_is_in_the_store,
    assert_failure_state_shown,
    assert_sound_receipt_shows_its_values,
)


def _seed(conn: Connection, config: EngineConfig) -> None:
    """A store with the demo hero in it, produced by the real engine."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("10")),
            cost_param="amount_eur",
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.plain",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    decide_and_reserve(make_request("demo.plain", {}), conn=conn, config=config, now=FROZEN_NOW)
    decide_and_reserve(
        make_request("demo.spend", {"amount_eur": Decimal("99")}, cost_eur=Decimal("99")),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )


def test_a_healthy_page_satisfies_every_property(conn: Connection, config: EngineConfig) -> None:
    _seed(conn, config)
    html = build_page(conn)
    for prop in ALL_PROPERTIES:
        if prop.__code__.co_argcount == 2:
            prop(html, conn)  # type: ignore[call-arg]
        else:
            prop(html)  # type: ignore[call-arg]
    assert_sound_receipt_shows_its_values(html)


def test_the_chain_block_says_absent_rather_than_showing_a_digest(
    conn: Connection, config: EngineConfig
) -> None:
    """The mockup shows `a3c1e7f0…` here. `0.4.1` has NULL, and the page says so.

    This is the single most important line in the viewer. Rendering a plausible digest
    over a dark column is precisely the dashboard lie the whole design exists to avoid,
    and it would have been the easiest thing in the world to do — the mockup shows one,
    so a faithful implementation of the mockup produces one.
    """
    _seed(conn, config)
    html = build_page(conn)
    assert "chain not yet in operation (ND-001)" in html
    assert "chain intact" not in html
    hero = hero_decision(conn)
    assert hero is not None
    assert verify_decision(conn, hero).by_name("chain").status is Status.ABSENT


def test_an_unsound_receipt_shows_the_failure_state_and_no_values(
    conn: Connection, config: EngineConfig
) -> None:
    """R028's first mandatory test. The store is damaged; the page must refuse."""
    _seed(conn, config)
    with tx(conn):
        conn.execute("DROP TRIGGER policy_versions_no_delete")
        conn.execute("DELETE FROM policy_versions")
    html = build_page(conn)
    assert_failure_state_shown(html)
    with pytest.raises(PropertyViolation):
        assert_sound_receipt_shows_its_values(html)


def test_an_unverifiable_check_is_as_loud_as_a_failed_one(
    conn: Connection, config: EngineConfig
) -> None:
    """Three outcomes, never two. `unverifiable` is a failure to surface, not a skip."""
    _seed(conn, config)
    with tx(conn):
        conn.execute("DROP TRIGGER policy_versions_no_delete")
        conn.execute("DELETE FROM policy_versions")
    model = build_model(conn)
    assert model.verification is not None
    assert model.verification.by_name("policy_snapshot").status is Status.UNVERIFIABLE
    assert_failure_state_shown(render(model))


# --- Sabotage (R028): the right tests fail, and no others ------------------------


def _properties_that_fail(html: str, conn: Connection) -> set[str]:
    """Run every property and name the ones that raise. The measurement itself."""
    failed: set[str] = set()
    for prop in (
        *ALL_PROPERTIES,
        assert_failure_state_shown,
        assert_sound_receipt_shows_its_values,
    ):
        try:
            if prop.__code__.co_argcount == 2:
                prop(html, conn)  # type: ignore[call-arg]
            else:
                prop(html)  # type: ignore[call-arg]
        except PropertyViolation:
            failed.add(prop.__name__)
    return failed


def test_sabotage_render_as_if_verified_fails_exactly_the_failure_state_test(
    conn: Connection, config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sabotage A. Force the renderer to show values for an unsound receipt.

    The intended catch is `assert_failure_state_shown` and nothing else: the page is
    still well-formed, still uses only token colours, still has no script, still
    escapes its input. Only its honesty is broken, and only the honesty test may move.
    """
    _seed(conn, config)
    with tx(conn):
        conn.execute("DROP TRIGGER policy_versions_no_delete")
        conn.execute("DELETE FROM policy_versions")

    healthy_failures = _properties_that_fail(build_page(conn), conn)
    assert healthy_failures == {"assert_sound_receipt_shows_its_values"}, (
        "before sabotage, the damaged store correctly renders the failure state"
    )

    # The sabotage: claim soundness regardless of the checks.
    monkeypatch.setattr(
        page_module.ReceiptVerification, "sound", property(lambda self: True), raising=True
    )
    sabotaged = _properties_that_fail(build_page(conn), conn)

    assert "assert_failure_state_shown" in sabotaged, (
        "render-as-if-verified must be caught by the failure-state test"
    )
    assert sabotaged - {"assert_failure_state_shown"} == set(), (
        f"the sabotage moved tests it should not have: "
        f"{sorted(sabotaged - {'assert_failure_state_shown'})}"
    )


def test_sabotage_a_fabricated_digest_fails_exactly_the_digest_test(
    conn: Connection, config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sabotage B. Put a digest on the page that the store does not carry.

    The intended catch is `assert_every_displayed_digest_is_in_the_store` and nothing
    else. This is the X-11 test for a UI, and the failure it models is the most
    seductive one available: a digest that *looks* right, taken from a mockup or
    computed for display, sitting on a page that is otherwise perfect.
    """
    _seed(conn, config)
    healthy = _properties_that_fail(build_page(conn), conn)
    assert healthy == {"assert_failure_state_shown"}, (
        "before sabotage, the sound store correctly shows its values"
    )

    fabricated = "a3c1e7f09d5b24c8571f0a6db93e48d2c05b7f1e8a94d6031bc27e5f4a8d90b1"
    assert (
        conn.execute("SELECT 1 FROM actions_audit WHERE policy_version=?", (fabricated,)).fetchone()
        is None
    ), "the fabricated digest must genuinely not be in the store"

    original_render = page_module.render
    monkeypatch.setattr(
        page_module,
        "render",
        lambda model: original_render(model).replace(
            str(model.hero["policy_version"]),
            fabricated,  # type: ignore[index]
        ),
    )
    sabotaged = _properties_that_fail(build_page(conn), conn)

    assert "assert_every_displayed_digest_is_in_the_store" in sabotaged, (
        "a digest the store does not carry must be caught by the X-11 test"
    )
    expected_noise = {"assert_failure_state_shown"}  # unchanged: this page is sound
    assert sabotaged - expected_noise == {"assert_every_displayed_digest_is_in_the_store"}, (
        f"the sabotage moved tests it should not have: "
        f"{sorted(sabotaged - expected_noise - {'assert_every_displayed_digest_is_in_the_store'})}"
    )


def test_sabotage_a_budget_number_rewritten_for_display_is_caught(
    conn: Connection, config: EngineConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A third sabotage, unasked for, because it is the likelier real mistake.

    Nobody fabricates a digest on purpose. Somebody absolutely formats `10` as `10.00`
    to make a column line up — and under E8 those are the same value and different
    evidence, so the page would then be showing a number the ledger does not contain.
    """
    _seed(conn, config)
    original_render = page_module.render
    monkeypatch.setattr(
        page_module,
        "render",
        lambda model: original_render(model).replace(">10</span>", ">10.00</span>"),
    )
    html = build_page(conn)
    with pytest.raises(PropertyViolation, match="rendered verbatim"):
        assert_every_displayed_budget_number_matches_the_store(html, conn)


# --- Escaping, sample labelling, empty stores -------------------------------------


def test_attacker_shaped_params_are_escaped(conn: Connection, config: EngineConfig) -> None:
    """Params reach the ledger verbatim by design; the page must not execute them."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.plain",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    )
    decide_and_reserve(
        make_request("demo.plain", {"note": "<script>alert(1)</script>"}, source=Source.LLM),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    html = build_page(conn)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_the_sample_label_travels_in_the_store(tmp_path: Path) -> None:
    """A flag on a command line is forgotten; a row in the artifact is not."""
    from onedoor.viewer.__main__ import seed_demo_store

    store = tmp_path / "demo.db"
    seed_demo_store(store)
    database = Database(str(store))
    conn = database.connect()
    try:
        assert build_model(conn).is_sample
        assert "SAMPLE DATA" in build_page(conn)
    finally:
        conn.close()


def test_a_real_store_is_not_labelled_as_sample(conn: Connection, config: EngineConfig) -> None:
    _seed(conn, config)
    assert not build_model(conn).is_sample
    assert "SAMPLE DATA" not in build_page(conn)


def test_an_empty_store_renders_without_inventing_a_receipt(tmp_path: Path) -> None:
    database = Database(str(tmp_path / "empty.db"))
    database.init()
    conn = database.connect()
    try:
        html = build_page(conn)
        assert "no verdicts" in html
        for prop in ALL_PROPERTIES:
            if prop.__code__.co_argcount == 2:
                prop(html, conn)  # type: ignore[call-arg]
            else:
                prop(html)  # type: ignore[call-arg]
    finally:
        conn.close()


def test_the_tail_shows_allows_and_denies(conn: Connection, config: EngineConfig) -> None:
    """The permit is `exec_intent`, not `decision`. A tail that misses it lies by omission."""
    _seed(conn, config)
    html = build_page(conn)
    assert "<b>ALLOW</b>" in html
    assert "<b>DENY</b>" in html


def test_the_budget_renders_the_stored_canonical_form(
    conn: Connection, config: EngineConfig
) -> None:
    """E8: the number on the page is the number in the ledger, spelling included."""
    _seed(conn, config)
    hero = hero_decision(conn)
    assert hero is not None
    budget = json.loads(hero["budget_json"])
    html = build_page(conn)
    for key in ("limit", "consumed", "remaining"):
        assert f">{budget[key]}</span>" in html


def test_the_viewer_needs_no_change_when_the_chain_comes_alive(
    conn: Connection, config: EngineConfig
) -> None:
    """The acceptance test for the single-verification rule (ND-001 / C4).

    The viewer was written while `row_hash` was NULL on every row and the chain block
    rendered the absent state. `ND-001` fills those columns and flips `_check_chain`
    from `absent` to `verified` — and this page, unchanged, now renders the digests.
    Not one line of `page.py` or `tokens.py` moved.

    That is what "one verification, and the viewer does not own it" buys. Had the
    renderer carried its own idea of what a chain looks like, this ticket would have
    had to edit it, and the two would have started to drift on the day they were most
    load-bearing.
    """
    from onedoor.guardrail import chain

    _seed(conn, config)
    assert "chain not yet in operation" in build_page(conn)

    with tx(conn):
        chain.enable(conn)
    _seed(conn, config)

    html = build_page(conn)
    assert "chain not yet in operation" not in html
    assert "contents re-derived" in html
    hero = hero_decision(conn)
    assert hero is not None
    assert hero["row_hash"] in html, "the real digest is on the page now"
    assert_every_displayed_digest_is_in_the_store(html, conn)
    assert_sound_receipt_shows_its_values(html)


def test_a_tampered_row_makes_the_viewer_refuse_to_show_it(
    conn: Connection, config: EngineConfig
) -> None:
    """And the failure state arrives without the page knowing what a chain is."""
    from onedoor.guardrail import chain

    with tx(conn):
        chain.enable(conn)
    _seed(conn, config)
    hero = hero_decision(conn)
    assert hero is not None

    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute("UPDATE actions_audit SET detail='edited' WHERE id=?", (hero["id"],))
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only'); END"
        )

    assert_failure_state_shown(build_page(conn))
