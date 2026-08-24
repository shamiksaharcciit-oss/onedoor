"""The coverage map (ND-052 / S4, T1–T3).

R049 §7's expected standing lives here: the four states computed, prominence ranked by
**behaviour** rather than by how alarming a name sounds, the cited range on the face of
the map, and the inert detector green.

The state that carries the ticket is `DECLARED_INERT`, because it is the one that is
dangerous while sounding fine — and it was measured on `0.5.0` rather than reasoned
about: the same request auto-executes with the label alone and goes to a human once the
effect policy exists.
"""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

from onedoor.guardrail import chain, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, EffectPolicy, Policy, Tier
from onedoor.store.db import tx
from onedoor.studio import coverage
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


def _state_of(rows: list[coverage.Row], name: str) -> str | None:
    return next((r.state for r in rows if r.name == name), None)


# --- The state that carries the ticket: a label with nothing behind it ------------


def test_a_labelled_effect_with_no_effect_policy_is_declared_inert(fresh: Connection) -> None:
    """The silent permit. Principle 4's exact target, in hand-written policy."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(fresh, _policy("pay", effects=["money.egress"]))

    m = coverage.build(fresh)
    assert _state_of(m.effects, "money.egress") == coverage.DECLARED_INERT
    row = next(r for r in m.effects if r.name == "money.egress")
    assert "no effect policy declares it" in row.detail
    assert "Declare the effect policy, or remove the label" in row.detail, (
        "a fail-closed finding whose message does not say how to fix it converts a "
        "defect into an outage"
    )


def test_declaring_the_effect_policy_moves_it_out_of_inert(fresh: Connection) -> None:
    """Both directions: the detector must clear when the gap is closed."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(fresh, _policy("pay", effects=["money.egress"]))
    assert _state_of(coverage.build(fresh).effects, "money.egress") == coverage.DECLARED_INERT

    policy_loader.upsert_effect(
        fresh, EffectPolicy(effect="money.egress", min_tier=Tier.CONFIRM, caps=Caps())
    )
    assert _state_of(coverage.build(fresh).effects, "money.egress") != coverage.DECLARED_INERT


def test_the_inert_state_is_the_one_that_actually_changes_the_verdict(
    fresh: Connection, config: EngineConfig
) -> None:
    """Measured, not asserted: this is why `DECLARED_INERT` outranks everything else.

    The map's claim is that an inert label is a silent permit. That claim is checked
    here against the engine itself rather than against the map's own docstring.
    """
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(fresh, _policy("pay", effects=["money.egress"]))
    assert _state_of(coverage.build(fresh).effects, "money.egress") == coverage.DECLARED_INERT

    out = decide_and_reserve(make_request("pay", {}), conn=fresh, config=config, now=FROZEN_NOW)
    assert isinstance(out, PermittedIntent), "the inert label should not have stopped it"

    policy_loader.upsert_effect(
        fresh, EffectPolicy(effect="money.egress", min_tier=Tier.CONFIRM, caps=Caps())
    )
    out2 = decide_and_reserve(make_request("pay", {}), conn=fresh, config=config, now=FROZEN_NOW)
    assert not isinstance(out2, PermittedIntent), (
        "declaring the effect policy must change the verdict — otherwise the map's "
        "central claim is wrong"
    )


# --- The other three states -------------------------------------------------------


def test_an_action_the_ledger_saw_and_no_policy_declares_is_uncovered_observed(
    fresh: Connection, config: EngineConfig
) -> None:
    """The world named this gap, not a model. `default_deny` — a loud denial."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    decide_and_reserve(
        make_request("nobody.declared.this", {}), conn=fresh, config=config, now=FROZEN_NOW
    )
    m = coverage.build(fresh)
    assert _state_of(m.actions, "nobody.declared.this") == coverage.UNCOVERED_OBSERVED
    assert _state_of(m.actions, "demo.restore") == coverage.COVERED


def test_a_declared_effect_no_observed_traffic_reaches_is_unobserved(
    fresh: Connection,
) -> None:
    """R049 §4: a row only inside a bounded vocabulary, and rendered **absent**."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(fresh, _policy("pay", effects=["money.egress"]))
    policy_loader.upsert_effect(
        fresh, EffectPolicy(effect="money.egress", min_tier=Tier.CONFIRM, caps=Caps())
    )
    m = coverage.build(fresh)
    assert _state_of(m.effects, "money.egress") == coverage.UNOBSERVED
    row = next(r for r in m.effects if r.name == "money.egress")
    assert "Absent, not safe" in row.detail
    assert "only that these rules do not route" in row.detail


def test_the_unbounded_set_is_a_footer_and_never_a_row(fresh: Connection) -> None:
    """A row cannot be drawn for something the map has never heard of."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    m = coverage.build(fresh)
    assert coverage.UNBOUNDED_NOTE in m.notes
    assert "NOT measured here" in coverage.UNBOUNDED_NOTE
    names = {r.name for r in m.actions} | {r.name for r in m.effects}
    assert all(n for n in names), "an empty-named row is the unbounded set leaking in"


# --- Prominence is ranked by behaviour --------------------------------------------


def test_prominence_ranks_the_silent_permit_above_the_loud_denial() -> None:
    """R049 §3's law: rank by what a state does, not by how alarming its name sounds."""
    assert coverage.PROMINENCE.index(coverage.DECLARED_INERT) < coverage.PROMINENCE.index(
        coverage.UNCOVERED_OBSERVED
    )
    assert coverage.PROMINENCE.index(coverage.UNCOVERED_OBSERVED) < coverage.PROMINENCE.index(
        coverage.UNOBSERVED
    )
    assert coverage.PROMINENCE.index(coverage.UNOBSERVED) < coverage.PROMINENCE.index(
        coverage.COVERED
    )


def test_ranked_puts_inert_first_on_a_real_map(fresh: Connection, config: EngineConfig) -> None:
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(fresh, _policy("pay", effects=["money.egress"]))
    policy_loader.upsert(fresh, _policy("read", effects=["data.read"]))
    policy_loader.upsert_effect(fresh, EffectPolicy(effect="data.read", min_tier=None, caps=Caps()))
    decide_and_reserve(make_request("read", {}), conn=fresh, config=config, now=FROZEN_NOW)

    m = coverage.build(fresh)
    ranked = m.ranked(m.effects)
    assert ranked[0].state == coverage.DECLARED_INERT
    assert ranked[0].name == "money.egress"


# --- The cited range, and its three states ----------------------------------------


def test_a_chained_store_gives_a_cited_range(fresh: Connection, config: EngineConfig) -> None:
    policy_loader.upsert(fresh, _policy("demo.restore"))
    with tx(fresh):
        chain.enable(fresh)
    decide_and_reserve(make_request("demo.restore", {}), conn=fresh, config=config, now=FROZEN_NOW)

    m = coverage.build(fresh)
    assert m.cited.state == coverage.CITED
    assert m.cited.row_hash_at_last_seq is not None
    assert m.cited.row_hash_at_last_seq in m.cited.sentence()


def test_an_unchained_store_says_it_cannot_cite_rather_than_reporting_a_bare_count(
    fresh: Connection, config: EngineConfig
) -> None:
    """Three outcomes: rows-but-no-chain is not rows-and-a-citation, and not no-rows."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    decide_and_reserve(make_request("demo.restore", {}), conn=fresh, config=config, now=FROZEN_NOW)

    m = coverage.build(fresh)
    assert m.cited.state == coverage.UNCITABLE
    assert m.cited.rows >= 1
    assert "CANNOT CITE" in m.cited.sentence()


def test_an_empty_ledger_is_a_non_measurement_not_a_zero(fresh: Connection) -> None:
    policy_loader.upsert(fresh, _policy("demo.restore"))
    m = coverage.build(fresh)
    assert m.cited.state == coverage.EMPTY
    assert "nothing observed is measured" in m.cited.sentence()


# --- The citation is exportable, and the derivation is documented -----------------


def test_the_citation_carries_only_what_a_third_party_re_derives_from(
    fresh: Connection, config: EngineConfig
) -> None:
    """R049 §5: `(version_hash, range)` and nothing else — the map is a view that cites."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    with tx(fresh):
        chain.enable(fresh)
    decide_and_reserve(make_request("demo.restore", {}), conn=fresh, config=config, now=FROZEN_NOW)

    citation = coverage.build(fresh).citation()
    assert set(citation) == {"schema", "version_hash", "range"}
    assert citation["version_hash"] == policy_loader.current_version(fresh)
    assert "coverage_digest" not in citation, (
        "a coverage digest would be a second address for facts that already have one"
    )


def test_the_derivation_document_exists_and_is_normative() -> None:
    """If it cannot be written clearly, the derivation is not as pure as the ruling assumes."""
    from pathlib import Path

    doc = Path(__file__).resolve().parents[2] / "docs" / "coverage-derivation.md"
    text = doc.read_text(encoding="utf-8")
    for state in coverage.PROMINENCE:
        assert state in text, f"the derivation document does not define {state}"
    assert "version_hash" in text and "row_hash_at_last_seq" in text


def test_every_note_the_map_carries_states_a_limit(fresh: Connection) -> None:
    """The map's own non-coverage, stated — principle 4 turned on the coverage map."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    m = coverage.build(fresh)
    assert coverage.PROJECTION_NOTE in m.notes
    assert "PROJECTS, it does not recall" in coverage.PROJECTION_NOTE
    assert "run a backtest over the range" in coverage.PROJECTION_NOTE, (
        "the note must name what DOES answer the historical question (R050 §4)"
    )


def test_effect_reachability_is_projected_from_the_mapped_policy_set(
    fresh: Connection, config: EngineConfig
) -> None:
    """The limit the note describes, demonstrated rather than only asserted.

    The action ran while its policy named no effect. Adding the label afterwards makes
    the effect read as reachable — because reachability is projected from the policy set being
    mapped, not recorded in the row. That is exactly what `PROJECTION_NOTE` warns about, and
    a test proves the warning is about real behaviour rather than a hypothetical.
    """
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(fresh, _policy("pay"))
    policy_loader.upsert_effect(
        fresh, EffectPolicy(effect="money.egress", min_tier=None, caps=Caps())
    )
    decide_and_reserve(make_request("pay", {}), conn=fresh, config=config, now=FROZEN_NOW)
    assert _state_of(coverage.build(fresh).effects, "money.egress") == coverage.UNOBSERVED

    policy_loader.upsert(fresh, _policy("pay", effects=["money.egress"]))
    assert _state_of(coverage.build(fresh).effects, "money.egress") == coverage.COVERED


def test_a_candidate_can_be_mapped_without_touching_the_active_set(
    fresh: Connection,
) -> None:
    """The canvas's use: map a draft, change nothing."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    active = policy_loader.current_version(fresh)
    candidate = [_policy("demo.restore"), _policy("pay", effects=["money.egress"])]

    m = coverage.build(fresh, policies=candidate, effects=[])
    assert _state_of(m.effects, "money.egress") == coverage.DECLARED_INERT
    assert policy_loader.current_version(fresh) == active


def test_the_map_writes_nothing_to_the_ledger(fresh: Connection, config: EngineConfig) -> None:
    policy_loader.upsert(fresh, _policy("demo.restore"))
    decide_and_reserve(make_request("demo.restore", {}), conn=fresh, config=config, now=FROZEN_NOW)
    before = fresh.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"]
    caps = [tuple(r) for r in fresh.execute("SELECT * FROM cap_counters ORDER BY 1,2,3")]

    coverage.build(fresh)

    assert fresh.execute("SELECT COUNT(*) AS n FROM actions_audit").fetchone()["n"] == before
    assert [tuple(r) for r in fresh.execute("SELECT * FROM cap_counters ORDER BY 1,2,3")] == caps


def test_counts_cover_every_state_including_the_empty_ones(fresh: Connection) -> None:
    """A state with no rows must still appear as 0, not vanish from the tally."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    m = coverage.build(fresh)
    assert set(m.counts(m.effects)) == set(coverage.PROMINENCE)
    assert set(m.counts(m.actions)) == set(coverage.PROMINENCE)


def test_a_param_effect_rule_label_also_counts_as_named(fresh: Connection) -> None:
    """`param_effects` can add an effect, so a label there has the same inert hazard."""
    from onedoor.guardrail.models import ParamEffectRule

    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(
        fresh,
        Policy(
            action_type="fetch",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            param_effects=[ParamEffectRule(param="url", pattern=".*", add_effects=["net.egress"])],
            bounds=Bounds(strict_params=False),
        ),
    )
    assert _state_of(coverage.build(fresh).effects, "net.egress") == coverage.DECLARED_INERT


def test_caps_on_an_inert_effect_are_equally_dropped(
    fresh: Connection, config: EngineConfig
) -> None:
    """Not just the tier floor — the effect's CAPS never apply either."""
    policy_loader.upsert(fresh, _policy("demo.restore"))
    policy_loader.upsert(
        fresh,
        Policy(
            action_type="spend",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(eur_day=Decimal("100000")),
            cost_param="amount_eur",
            effects=["money.egress"],
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
    )
    assert _state_of(coverage.build(fresh).effects, "money.egress") == coverage.DECLARED_INERT

    out = decide_and_reserve(
        make_request("spend", {"amount_eur": Decimal("99999")}, cost_eur=Decimal("99999")),
        conn=fresh,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(out, PermittedIntent), (
        "an effect cap that was never declared cannot have applied — which is the point"
    )
