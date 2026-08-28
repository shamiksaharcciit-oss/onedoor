"""The coverage map's skin (ND-052 / S4-T5).

Two things this suite holds, both from R049 §3: **no semantic pair anywhere on this
surface**, and **prominence ordered by behaviour** — the silent permit above the loud
denial, measured from the rendered document rather than trusted from the stylesheet's
comments.
"""

from __future__ import annotations

import re
from sqlite3 import Connection

from onedoor.guardrail import chain, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, EffectPolicy, Policy, Tier
from onedoor.store.db import tx
from onedoor.studio import coverage as model
from onedoor.viewer import coverage as skin
from tests.conftest import FROZEN_NOW, make_request


def _policy(action: str, effects: list[str] | None = None) -> Policy:
    return Policy(
        action_type=action,
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="demo.restore",
        effects=effects or [],
        bounds=Bounds(strict_params=False),
    )


def _map(fresh: Connection, config: EngineConfig) -> model.CoverageMap:
    """A store with one of every state on it."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(fresh, _policy("pay", effects=["money.egress"]))  # inert
    policy_loader.upsert(fresh, _policy("read", effects=["data.read"]))
    policy_loader.upsert_effect(fresh, EffectPolicy(effect="data.read", min_tier=None, caps=Caps()))
    policy_loader.upsert_effect(
        fresh, EffectPolicy(effect="never.touched", min_tier=None, caps=Caps())
    )
    with tx(fresh):
        chain.enable(fresh)
    decide_and_reserve(make_request("read", {}), conn=fresh, config=config, now=FROZEN_NOW)
    decide_and_reserve(
        make_request("nobody.declared.this", {}), conn=fresh, config=config, now=FROZEN_NOW
    )
    return model.build(fresh)


# --- No semantic pair, anywhere ---------------------------------------------------


def test_the_coverage_map_never_uses_a_verdicts_colours(
    fresh: Connection, config: EngineConfig
) -> None:
    """A coverage cell is a prediction about a class; a verdict is a fact about an event.

    One colour cannot carry both meanings, so the pair is spent everywhere or nowhere —
    and this surface has no verdicts on it at all.
    """
    html = skin.render_page(_map(fresh, config))
    for var in skin.STATE_COLOUR_VARS:
        assert f"var({var})" not in html, f"the coverage map used {var}, which belongs to verdicts"


def test_the_map_still_distinguishes_its_states_visually(
    fresh: Connection, config: EngineConfig
) -> None:
    """The other direction: refusing the pair must not flatten the map into one style.

    A rule checked one way forbids the wrong thing without requiring the right one, so
    prominence has to be *present* — size, position and weight — not merely not-red.

    **Inverted by R056 §4**, in the same commit as the migration that made it true. This
    test used to REQUIRE `var(--seal)` on the state row; when core superseded R049 §3's
    fourth mechanism, that requirement became a test demanding a violation. *A test that
    requires a violation becomes a defect the moment the law strengthens, and it must not
    survive one commit longer than the violation it protects.*

    The three mechanisms it now requires are the three R049 §3 kept.
    """
    html = skin.render_page(_map(fresh, config))
    styles = html.split("<style>")[1].split("</style>")[0]
    inert = [rule for rule in styles.split("}") if ".row.declared_inert" in rule]
    assert inert, "the most dangerous state has no distinguishing style at all"
    joined = " ".join(inert)
    assert "var(--seal)" not in joined, "the brand accent must not carry this state (R056 §4)"
    assert "font-weight:700" in joined, "weight"
    assert "font-size" in joined, "size"
    assert "border-left" in joined, "position"


# --- Prominence, ranked by behaviour ----------------------------------------------


def test_the_silent_permit_is_rendered_above_the_loud_denial(
    fresh: Connection, config: EngineConfig
) -> None:
    """R049 §3, measured from the document's own ordering."""
    m = _map(fresh, config)
    html = skin.render_page(m)
    inert_at = html.index("DECLARED, INERT")
    uncovered_at = html.index("UNCOVERED<")
    covered_at = html.rindex("covered<")
    assert inert_at < uncovered_at < covered_at, (
        "prominence is not ordered by behaviour — the silent permit must come first"
    )


def test_every_state_has_a_label_derived_from_the_model() -> None:
    """A missing key is a KeyError in a test, not an unlabelled row on a screen."""
    assert set(skin.STATE_LABEL) == set(model.PROMINENCE)


def test_unreached_renders_as_absent_and_never_as_safe(
    fresh: Connection, config: EngineConfig
) -> None:
    html = skin.render_page(_map(fresh, config))
    assert "UNREACHED" in html
    assert "never.touched" in html
    styles = html.split("<style>")[1].split("</style>")[0]
    unreached = " ".join(r for r in styles.split("}") if ".row.unreached" in r)
    assert "italic" in unreached or "opacity" in unreached
    assert "var(--ok)" not in unreached


# --- What the map must always say -------------------------------------------------


def test_the_citation_is_on_the_face_of_the_map(fresh: Connection, config: EngineConfig) -> None:
    """R049 §7: the cited range on the face of the map, not in a tooltip."""
    m = _map(fresh, config)
    html = skin.render_page(m)
    assert m.cited.row_hash_at_last_seq is not None
    assert m.cited.row_hash_at_last_seq in html, "the citation must be rendered in full"
    assert m.version_hash is not None and m.version_hash in html


def test_the_uncitable_state_says_so_on_the_page(fresh: Connection, config: EngineConfig) -> None:
    """An unchained store's numbers are real and uncheckable, and the page says both."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    decide_and_reserve(make_request("demo.restore", {}), conn=fresh, config=config, now=FROZEN_NOW)
    html = skin.render_page(model.build(fresh))
    assert "CANNOT CITE" in html


def test_the_notes_render_and_state_the_maps_own_limits(
    fresh: Connection, config: EngineConfig
) -> None:
    """Principle 4 turned on the coverage map itself."""
    html = skin.render_page(_map(fresh, config))
    assert "what this map does not measure" in html
    assert "PROJECTS, it does not recall" in html
    assert "unbounded" in html


def test_the_inert_row_carries_its_remedy(fresh: Connection, config: EngineConfig) -> None:
    """A fail-closed finding whose message does not say how to fix it becomes an outage."""
    html = skin.render_page(_map(fresh, config))
    assert "Declare the effect policy, or remove the label" in html


def test_the_page_escapes_policy_text(fresh: Connection) -> None:
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(fresh, _policy("<script>alert(1)</script>", effects=["<img src=x>"]))
    html = skin.render_page(model.build(fresh))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_counts_show_zero_rather_than_omitting_a_state(
    fresh: Connection, config: EngineConfig
) -> None:
    """A state with no rows still appears in the tally — absent is not invisible."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    html = skin.render_page(model.build(fresh))
    for state in model.PROMINENCE:
        assert skin.STATE_LABEL[state] in html
    assert re.search(r"DECLARED, INERT <b>0</b>", html)
