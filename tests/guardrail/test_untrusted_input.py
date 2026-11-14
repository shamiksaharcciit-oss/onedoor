"""Untrusted-input checks: a caller-marked
path matching a policy's own `untrusted_params.deny`/`hold` stops the action
before bounds and caps are ever consulted. Deny wins over hold; a path named
in neither has no effect, whether or not the caller marked it.
"""

from __future__ import annotations

from sqlite3 import Connection

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    Bounds,
    CheckId,
    Decision,
    Policy,
    Source,
    Tier,
    UntrustedParams,
)
from tests.conftest import FROZEN_NOW, make_request

ACTION = "demo.untrusted"


def _policy(conn: Connection, **kw: object) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
            **kw,  # type: ignore[arg-type]
        ),
    )


def _request(params: dict[str, object], untrusted: list[str]) -> object:
    return make_request(ACTION, params, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"untrusted": untrusted}
    )


def test_a_deny_listed_marked_path_is_denied_outright(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn, untrusted_params=UntrustedParams(deny=["command"]))
    result = decide_and_reserve(
        _request({"command": "rm -rf /"}, ["command"]), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.UNTRUSTED_INPUT
    assert result.decision.untrusted_matched == ["command"]


def test_a_hold_listed_marked_path_is_proposed_never_auto_executed(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn, untrusted_params=UntrustedParams(hold=["recipient"]))
    result = decide_and_reserve(
        _request({"recipient": "someone@example.test"}, ["recipient"]),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.UNTRUSTED_INPUT
    assert result.decision.effective_tier == Tier.CONFIRM
    assert result.decision.untrusted_matched == ["recipient"]


def test_an_unmarked_value_decides_as_before_this_feature_existed(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn, untrusted_params=UntrustedParams(deny=["command"], hold=["recipient"]))
    result = decide_and_reserve(
        _request({"recipient": "someone@example.test"}, []),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)


def test_a_marked_path_the_policy_names_in_neither_list_has_no_effect(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn, untrusted_params=UntrustedParams(deny=["command"], hold=["recipient"]))
    result = decide_and_reserve(
        _request({"recipient": "x", "other": "y"}, ["other"]),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert isinstance(result, PermittedIntent)


def test_untrusted_matched_is_recorded_as_empty_not_null_when_the_policy_uses_the_check(
    conn: Connection, config: EngineConfig
) -> None:
    """A policy that declares `untrusted_params` gets a real, recorded result
    even on a clean pass -- `[]`, not NULL -- so an auditor can tell "checked,
    nothing matched" from "this policy never uses the check" (the latter is
    `test_an_unmarked_value_decides_as_before_this_feature_existed`'s sibling
    case and is covered by digest-stability tests elsewhere)."""
    _policy(conn, untrusted_params=UntrustedParams(deny=["command"], hold=["recipient"]))
    req = _request({"recipient": "someone@example.test"}, [])
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    row = conn.execute(
        "SELECT untrusted_matched_json FROM actions_audit WHERE request_id=?",
        (str(req.request_id),),  # type: ignore[attr-defined]
    ).fetchone()
    assert row["untrusted_matched_json"] == "[]"


def test_deny_wins_over_hold_when_both_are_marked_on_the_same_call(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn, untrusted_params=UntrustedParams(deny=["command"], hold=["recipient"]))
    result = decide_and_reserve(
        _request({"command": "x", "recipient": "y"}, ["command", "recipient"]),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.UNTRUSTED_INPUT
    assert result.decision.untrusted_matched == ["command"]


def test_untrusted_input_is_checked_before_bounds(conn: Connection, config: EngineConfig) -> None:
    """A deny-listed marked path is refused for provenance even when the same
    call would also fail bounds -- the provenance refusal must win, named by
    its own reason code, not a generic bounds failure."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(required=["amount"]),  # 'command' is missing -> would fail bounds too
            untrusted_params=UntrustedParams(deny=["command"]),
        ),
    )
    result = decide_and_reserve(
        _request({"command": "x"}, ["command"]), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.reason_code == CheckId.UNTRUSTED_INPUT


def test_a_policy_naming_no_untrusted_params_decides_identically_to_0_10_x(
    conn: Connection, config: EngineConfig
) -> None:
    _policy(conn)  # no untrusted_params at all
    result = decide_and_reserve(
        _request({"recipient": "x"}, ["recipient"]), conn=conn, config=config, now=FROZEN_NOW
    )
    assert isinstance(result, PermittedIntent)


def test_a_tier_0_read_with_a_deny_listed_marked_path_is_denied_not_executed(
    conn: Connection, config: EngineConfig
) -> None:
    """A tier-0 (OBSERVE) action used to return before this check ever ran, so
    a marked, denied path on a pure read executed unchecked. The check must
    apply at every tier, including the one tier that otherwise never reaches
    bounds or caps at all."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.OBSERVE,
            bounds=Bounds(strict_params=False),
            untrusted_params=UntrustedParams(deny=["command"]),
        ),
    )
    result = decide_and_reserve(
        _request({"command": "rm -rf /"}, ["command"]), conn=conn, config=config, now=FROZEN_NOW
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.UNTRUSTED_INPUT
    assert result.decision.untrusted_matched == ["command"]


def test_a_hold_match_is_kept_in_the_receipt_when_bounds_then_denies(
    conn: Connection, config: EngineConfig
) -> None:
    """A hold match from 5c escalates the tier, but bounds (step 6) is the
    one that actually denies this call -- the record of what already
    matched must not disappear just because a different, later check is
    the one that denied."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=ACTION,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(required=["amount"], strict_params=False),
            untrusted_params=UntrustedParams(hold=["recipient"]),
        ),
    )
    result = decide_and_reserve(
        # "amount" is missing entirely -> bounds fails; "recipient" is marked
        # and hold-listed -> 5c already matched before bounds ever ran.
        _request({"recipient": "someone@example.test"}, ["recipient"]),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.BOUNDS
    assert result.decision.untrusted_matched == ["recipient"]
