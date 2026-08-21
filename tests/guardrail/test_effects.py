"""Effect labels: aliasing-resistant governance.

The problem these test: policy binds to action *names*, but the same
real-world effect is reachable through many tools. Effects give the engine a
second, name-independent binding: shared caps, tier floors, and deterministic
parameter rules for generic tools.
"""

from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    Bounds,
    Caps,
    CheckId,
    Decision,
    EffectPolicy,
    ParamEffectRule,
    Policy,
    Tier,
)
from tests.conftest import FROZEN_NOW, make_request


def _seed_effects(conn: Connection) -> None:
    # Two differently-named tools, same declared effect; a generic tool whose
    # effect depends on a parameter; an effect with a shared cap and a floor.
    policy_loader.upsert_effect(
        conn,
        EffectPolicy(effect="money.egress", min_tier=None, caps=Caps(daily_rate=2)),
    )
    policy_loader.upsert_effect(
        conn, EffectPolicy(effect="state.destructive", min_tier=Tier.CONFIRM, caps=Caps())
    )
    for name in ("demo.pay_direct", "demo.pay_http"):
        policy_loader.upsert(
            conn,
            Policy(
                action_type=name,
                tier=Tier.AUTO,
                dry_run=False,
                compensating_command="demo.restore",
                effects=["money.egress"],
                bounds=Bounds(strict_params=False),
            ),
        )
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.http",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            param_effects=[
                ParamEffectRule(
                    param="url",
                    pattern=r"https://bank\.example\.com/.*",
                    add_effects=["money.egress"],
                ),
                ParamEffectRule(
                    param="url", pattern=r".*/delete/.*", add_effects=["state.destructive"]
                ),
            ],
        ),
    )


def test_effect_cap_is_shared_across_aliased_actions(
    conn: Connection, config: EngineConfig
) -> None:
    _seed_effects(conn)
    # Two payments through two differently-named tools consume ONE shared budget...
    r1 = decide_and_reserve(
        make_request("demo.pay_direct"), conn=conn, config=config, now=FROZEN_NOW
    )
    r2 = decide_and_reserve(make_request("demo.pay_http"), conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(r1, PermittedIntent) and isinstance(r2, PermittedIntent)
    # ...so the third, via either name, is denied by the effect's cap.
    r3 = decide_and_reserve(
        make_request("demo.pay_direct"), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(r3, PermittedIntent)
    assert r3.decision.reason_code == CheckId.CAP_RATE
    assert "money.egress" in (r3.decision.detail or "")


def test_param_rule_gives_generic_tool_the_effect(conn: Connection, config: EngineConfig) -> None:
    _seed_effects(conn)
    # A generic http call to the bank domain carries money.egress: it shares
    # the same budget as the named payment tools.
    for _ in range(2):
        r = decide_and_reserve(
            make_request("demo.http", {"url": "https://bank.example.com/transfer"}),
            conn=conn,
            config=config,
            now=FROZEN_NOW,
        )
        assert isinstance(r, PermittedIntent)
    blocked = decide_and_reserve(
        make_request("demo.pay_direct"), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(blocked, PermittedIntent)
    assert blocked.decision.reason_code == CheckId.CAP_RATE


def test_effect_tier_floor_escalates_auto_action(conn: Connection, config: EngineConfig) -> None:
    _seed_effects(conn)
    # demo.http is Tier 1, but a /delete/ URL carries state.destructive whose
    # floor is Tier 3: proposed, with the effect_floor reason.
    r = decide_and_reserve(
        make_request("demo.http", {"url": "https://api.example.com/delete/users"}),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(r, PermittedIntent)
    assert r.decision.decision == Decision.PROPOSED
    assert r.decision.reason_code == CheckId.EFFECT_FLOOR


def test_innocent_params_gain_no_effects(conn: Connection, config: EngineConfig) -> None:
    _seed_effects(conn)
    r = decide_and_reserve(
        make_request("demo.http", {"url": "https://weather.example.com/today"}),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(r, PermittedIntent)  # no label, no floor, no shared cap


def test_effect_cap_failure_reserves_nothing(conn: Connection, config: EngineConfig) -> None:
    _seed_effects(conn)
    # Exhaust the effect budget via pay_direct (which has no action-level cap).
    for _ in range(2):
        assert isinstance(
            decide_and_reserve(
                make_request("demo.pay_direct"), conn=conn, config=config, now=FROZEN_NOW
            ),
            PermittedIntent,
        )
    # A capped action that fails on the EFFECT cap must not consume its own
    # action-level counter: all-or-nothing reservation.
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.pay_capped",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            caps=Caps(daily_rate=5),
            effects=["money.egress"],
            bounds=Bounds(strict_params=False),
        ),
    )
    denied = decide_and_reserve(
        make_request("demo.pay_capped"), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(denied, PermittedIntent)
    row = conn.execute(
        "SELECT count FROM cap_counters WHERE action_type='demo.pay_capped'"
    ).fetchone()
    assert row is None  # nothing reserved for the action itself
