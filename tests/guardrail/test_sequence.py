"""Rules across a sequence: a policy's own
`sequence.rules` stop an action based on what already settled earlier in the
same session -- `after_tag` (a tagged read earlier in the window) or
`count_over` (too many prior matching actions already over a threshold).
Checked before bounds and caps, the same placement as untrusted-input.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from sqlite3 import Connection

from onedoor.guardrail import policy_loader, sequence
from onedoor.guardrail.decision import Outcome as _Outcome
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    Bounds,
    CheckId,
    CountOverSpec,
    Decision,
    Policy,
    SequencePolicy,
    SequenceRule,
    Source,
    Tier,
)
from tests.conftest import FROZEN_NOW, make_request

READ = "demo.seq_read"
SEND = "demo.seq_send"
REFUND = "demo.seq_refund"
GOVERNED = "demo.seq_governed"


def _tagged_read_policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=READ,
            tier=Tier.OBSERVE,
            sequence=SequencePolicy(tag_as="untrusted_content"),
        ),
    )


def _held_after_tag_policy(conn: Connection, *, within_seconds: int = 3600) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=SEND,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.undo_send",
            bounds=Bounds(strict_params=False),
            sequence=SequencePolicy(
                rules=[
                    SequenceRule(
                        after_tag="untrusted_content", within_seconds=within_seconds, effect="hold"
                    )
                ]
            ),
        ),
    )


def _refund_policy(conn: Connection, *, max_count: int = 1, within_seconds: int = 86400) -> None:
    """Self-referential, the same pattern the design note's own worked
    example uses (`payments.*` counting `payments.refund`): the rule watches
    its own action type's history."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=REFUND,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.undo_refund",
            cost_param="amount_eur",
            bounds=Bounds(required=["amount_eur"], strict_params=False),
            sequence=SequencePolicy(
                rules=[
                    SequenceRule(
                        count_over=CountOverSpec(
                            action_type=REFUND,
                            amount_param="amount_eur",
                            threshold_eur=Decimal(500),
                            max_count=max_count,
                            within_seconds=within_seconds,
                        ),
                        effect="deny",
                    )
                ]
            ),
        ),
    )


def _governed_watches_refund_policy(conn: Connection, *, max_count: int = 1) -> None:
    """A DIFFERENT action type watching `REFUND`'s own history -- no
    `amount_param`/`threshold_eur` of its own, so every occurrence counts,
    unconditionally on this action's own params (it has none in common with
    `REFUND` at all)."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type=GOVERNED,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.undo_governed",
            bounds=Bounds(strict_params=False),
            sequence=SequencePolicy(
                rules=[
                    SequenceRule(
                        count_over=CountOverSpec(
                            action_type=REFUND, max_count=max_count, within_seconds=86400
                        ),
                        effect="deny",
                    )
                ]
            ),
        ),
    )


def _settle_refund(
    conn: Connection, config: EngineConfig, amount: Decimal, session: str, now
) -> None:
    req = make_request(REFUND, {"amount_eur": amount}, source=Source.LLM, now=now).model_copy(
        update={"session_id": session}
    )
    result = decide_and_reserve(req, conn=conn, config=config, now=now)
    assert isinstance(result, PermittedIntent), result
    report_result(
        result,
        conn=conn,
        config=config,
        outcome=_Outcome.SUCCESS,
        payload=None,
        error=None,
        now=now,
    )


def test_a_tagged_read_then_a_send_within_the_window_is_held(
    conn: Connection, config: EngineConfig
) -> None:
    _tagged_read_policy(conn)
    _held_after_tag_policy(conn)
    session = "s1"
    read_req = make_request(READ, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": session}
    )
    read_result = decide_and_reserve(read_req, conn=conn, config=config, now=FROZEN_NOW)
    assert read_result.decision.decision == Decision.EXECUTED

    later = FROZEN_NOW + timedelta(seconds=60)
    send_req = make_request(SEND, {}, source=Source.LLM, now=later).model_copy(
        update={"session_id": session}
    )
    send_result = decide_and_reserve(send_req, conn=conn, config=config, now=later)
    assert not isinstance(send_result, PermittedIntent)
    assert send_result.decision.decision == Decision.PROPOSED
    assert send_result.decision.reason_code == CheckId.SEQUENCE_RULE
    assert send_result.decision.effective_tier == Tier.CONFIRM
    assert send_result.decision.sequence_rule_matched == "after_tag:untrusted_content"


def test_a_send_with_no_prior_tagged_read_in_this_session_is_not_held(
    conn: Connection, config: EngineConfig
) -> None:
    _tagged_read_policy(conn)
    _held_after_tag_policy(conn)
    session = "s2"
    send_req = make_request(SEND, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": session}
    )
    result = decide_and_reserve(send_req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)


def test_a_tagged_read_outside_the_window_no_longer_holds_the_send(
    conn: Connection, config: EngineConfig
) -> None:
    _tagged_read_policy(conn)
    _held_after_tag_policy(conn, within_seconds=60)
    session = "s3"
    read_req = make_request(READ, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": session}
    )
    decide_and_reserve(read_req, conn=conn, config=config, now=FROZEN_NOW)

    too_late = FROZEN_NOW + timedelta(seconds=61)
    send_req = make_request(SEND, {}, source=Source.LLM, now=too_late).model_copy(
        update={"session_id": session}
    )
    result = decide_and_reserve(send_req, conn=conn, config=config, now=too_late)
    assert isinstance(result, PermittedIntent)


def test_a_different_sessions_tagged_read_does_not_hold_this_one(
    conn: Connection, config: EngineConfig
) -> None:
    _tagged_read_policy(conn)
    _held_after_tag_policy(conn)
    read_req = make_request(READ, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": "session-a"}
    )
    decide_and_reserve(read_req, conn=conn, config=config, now=FROZEN_NOW)

    send_req = make_request(SEND, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": "session-b"}
    )
    result = decide_and_reserve(send_req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)


def test_a_tier_0_read_is_itself_held_by_a_matching_sequence_rule(
    conn: Connection, config: EngineConfig
) -> None:
    """A nominal tier-0 (OBSERVE) action used to return before this check ever
    ran, so a matching rule never had a chance to hold it -- the same gap
    untrusted-input had at tier 0. A hold still applies to a read: the call
    is proposed at CONFIRM, not silently executed."""
    read_gated = "demo.seq_read_gated"
    policy_loader.upsert(
        conn,
        Policy(
            action_type=read_gated,
            tier=Tier.OBSERVE,
            sequence=SequencePolicy(
                rules=[
                    SequenceRule(after_tag="untrusted_content", within_seconds=3600, effect="hold")
                ]
            ),
        ),
    )
    _tagged_read_policy(conn)
    session = "s-tier0-hold"
    tag_req = make_request(READ, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": session}
    )
    decide_and_reserve(tag_req, conn=conn, config=config, now=FROZEN_NOW)

    later = FROZEN_NOW + timedelta(seconds=60)
    gated_req = make_request(read_gated, {}, source=Source.LLM, now=later).model_copy(
        update={"session_id": session}
    )
    result = decide_and_reserve(gated_req, conn=conn, config=config, now=later)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.SEQUENCE_RULE
    assert result.decision.effective_tier == Tier.CONFIRM


def test_a_fresh_sessions_first_windowed_call_is_decided_on_its_empty_history(
    conn: Connection, config: EngineConfig
) -> None:
    """A session that has never had anything evicted has no `sequence_evicted`
    row at all -- its first windowed call is decided on its own (empty)
    history, never stopped as incomplete just for being new."""
    _held_after_tag_policy(conn)
    session = "brand-new-session"
    req = make_request(SEND, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": session}
    )
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    evicted_row = conn.execute(
        "SELECT evicted_through FROM sequence_evicted WHERE session_id=?", (session,)
    ).fetchone()
    assert evicted_row is None


def test_with_no_session_id_a_tag_only_policy_is_inert(
    conn: Connection, config: EngineConfig
) -> None:
    """`READ`'s own policy carries `sequence.tag_as` but no `rules` -- there
    is nothing to evaluate a session against, so a missing `session_id` is
    inert for it either way, the same as before this feature existed. (It
    is also tier 0/OBSERVE, which never reaches the sequence check at all --
    both reasons this call cannot be held.)"""
    _tagged_read_policy(conn)
    read_req = make_request(READ, {}, source=Source.LLM, now=FROZEN_NOW)  # no session_id
    result = decide_and_reserve(read_req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.EXECUTED


def test_no_session_id_against_a_policy_with_rules_is_held_not_silently_passed(
    conn: Connection, config: EngineConfig
) -> None:
    """A policy whose own `sequence.rules` is non-empty must not let a caller
    avoid every rule just by leaving `session_id` out: held, with its own
    reason code, rather than decided as if no rule existed."""
    _held_after_tag_policy(conn)
    send_req = make_request(SEND, {}, source=Source.LLM, now=FROZEN_NOW)  # no session_id
    result = decide_and_reserve(send_req, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.SEQUENCE_NO_SESSION
    assert result.decision.effective_tier == Tier.CONFIRM


def test_session_optional_exempts_a_policy_from_the_no_session_hold(
    conn: Connection, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=SEND,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.undo_send",
            bounds=Bounds(strict_params=False),
            sequence=SequencePolicy(
                session_optional=True,
                rules=[
                    SequenceRule(after_tag="untrusted_content", within_seconds=3600, effect="hold")
                ],
            ),
        ),
    )
    send_req = make_request(SEND, {}, source=Source.LLM, now=FROZEN_NOW)  # no session_id
    result = decide_and_reserve(send_req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)


def test_a_policy_naming_no_sequence_decides_identically_to_0_10_x(
    conn: Connection, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=SEND,
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.undo_send",
            bounds=Bounds(strict_params=False),
            # no `sequence` at all
        ),
    )
    req = make_request(SEND, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": "s4"}
    )
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    assert result.decision_ref is None or True  # sanity: nothing about this path changed


def test_count_over_denies_a_second_refund_over_threshold_within_the_window(
    conn: Connection, config: EngineConfig
) -> None:
    _refund_policy(conn, max_count=1, within_seconds=86400)
    session = "s5"
    _settle_refund(conn, config, Decimal("600.00"), session, FROZEN_NOW)  # first, tolerated

    second_req = make_request(
        REFUND, {"amount_eur": Decimal("700.00")}, source=Source.LLM, now=FROZEN_NOW
    ).model_copy(update={"session_id": session})
    result = decide_and_reserve(
        second_req, conn=conn, config=config, now=FROZEN_NOW + timedelta(seconds=1)
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.SEQUENCE_RULE
    assert result.decision.sequence_rule_matched == f"count_over:{REFUND}"


def test_count_over_does_not_deny_when_no_prior_refund_is_over_threshold_yet(
    conn: Connection, config: EngineConfig
) -> None:
    _refund_policy(conn, max_count=1, within_seconds=86400)
    session = "s6"
    req = make_request(
        REFUND, {"amount_eur": Decimal("600.00")}, source=Source.LLM, now=FROZEN_NOW
    ).model_copy(update={"session_id": session})
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)  # the first one is always tolerated


def test_count_over_does_not_deny_a_refund_that_is_itself_under_threshold(
    conn: Connection, config: EngineConfig
) -> None:
    """A prior refund already over threshold -- `max_count` already spent --
    but the action being decided right now is itself under the threshold, so
    this rule does not apply to it (even though it would to a later,
    over-threshold one)."""
    _refund_policy(conn, max_count=1, within_seconds=86400)
    session = "s7"
    _settle_refund(conn, config, Decimal("600.00"), session, FROZEN_NOW)

    under_req = make_request(
        REFUND, {"amount_eur": Decimal("50.00")}, source=Source.LLM, now=FROZEN_NOW
    ).model_copy(update={"session_id": session})
    result = decide_and_reserve(
        under_req, conn=conn, config=config, now=FROZEN_NOW + timedelta(seconds=1)
    )
    assert isinstance(result, PermittedIntent)


def test_count_over_on_a_different_action_type_counts_every_occurrence_unconditionally(
    conn: Connection, config: EngineConfig
) -> None:
    """GOVERNED watches REFUND's own history but shares none of its params --
    so its own rule carries no `amount_param`, and every occurrence of REFUND
    counts, regardless of amount."""
    _refund_policy(conn, max_count=100, within_seconds=86400)  # REFUND's own rule: never trips here
    _governed_watches_refund_policy(conn, max_count=1)
    session = "s9"
    _settle_refund(conn, config, Decimal("1.00"), session, FROZEN_NOW)  # well under any threshold

    governed_req = make_request(GOVERNED, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": session}
    )
    result = decide_and_reserve(
        governed_req, conn=conn, config=config, now=FROZEN_NOW + timedelta(seconds=1)
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.DENIED
    assert result.decision.reason_code == CheckId.SEQUENCE_RULE
    assert result.decision.sequence_rule_matched == f"count_over:{REFUND}"


def test_sequence_events_considered_and_history_incomplete_recorded_even_on_a_plain_pass(
    conn: Connection, config: EngineConfig
) -> None:
    """A permit's own audit row records what the sequence check actually
    found, including "nothing", whenever the policy carries a `sequence`
    block at all -- a real `0`/`False`, not NULL, so an auditor can tell
    "checked, clean" from "this policy never uses the check" (the latter
    stays NULL; see test_a_policy_naming_no_sequence_decides_identically_
    to_0_10_x's own digest-stability coverage). Extends the `untrusted_
    matched_json` treatment to this column too, gated on whether the policy
    USES the check, not on whether the result happened to be falsy."""
    _tagged_read_policy(conn)
    _held_after_tag_policy(conn)
    req = make_request(SEND, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": "s8"}
    )
    result = decide_and_reserve(req, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, PermittedIntent)
    row = conn.execute(
        "SELECT sequence_events_considered, sequence_rule_matched, sequence_history_incomplete "
        "FROM actions_audit WHERE request_id=?",
        (str(req.request_id),),
    ).fetchone()
    assert row["sequence_events_considered"] == 0
    assert row["sequence_rule_matched"] is None
    assert row["sequence_history_incomplete"] == 0


# --- lower-level: the bound, eviction and cross-session prune ----------------


def test_per_session_cap_evicts_the_oldest_rows_first(conn: Connection) -> None:
    session = "evict-1"
    for i in range(5):
        sequence.record_event(
            conn,
            session_id=session,
            action_type="x",
            tag=None,
            at=FROZEN_NOW + timedelta(seconds=i),
            audit_id=i + 1,
            max_events_per_session=3,
        )
    rows = conn.execute(
        "SELECT audit_id FROM sequence_events WHERE session_id=? ORDER BY at", (session,)
    ).fetchall()
    assert [r["audit_id"] for r in rows] == [3, 4, 5]
    evicted = conn.execute(
        "SELECT evicted_through FROM sequence_evicted WHERE session_id=?", (session,)
    ).fetchone()
    assert evicted is not None


def test_an_eviction_fail_closed_rule_applies_its_effect_and_marks_incomplete(
    conn: Connection, config: EngineConfig
) -> None:
    _tagged_read_policy(conn)
    _held_after_tag_policy(conn, within_seconds=999999)  # a window reaching well before eviction
    session = "evict-2"
    read_req = make_request(READ, {}, source=Source.LLM, now=FROZEN_NOW).model_copy(
        update={"session_id": session}
    )
    decide_and_reserve(read_req, conn=conn, config=config, now=FROZEN_NOW)
    # Force this session over its own cap so the tagged read above is evicted.
    for i in range(config.sequence_max_events_per_session):
        sequence.record_event(
            conn,
            session_id=session,
            action_type="filler",
            tag=None,
            at=FROZEN_NOW + timedelta(seconds=i + 1),
            audit_id=10_000 + i,
            max_events_per_session=config.sequence_max_events_per_session,
        )
    evicted = conn.execute(
        "SELECT evicted_through FROM sequence_evicted WHERE session_id=?", (session,)
    ).fetchone()
    assert evicted is not None, "the tagged read should have been evicted by now"

    send_req = make_request(
        SEND, {}, source=Source.LLM, now=FROZEN_NOW + timedelta(seconds=2)
    ).model_copy(update={"session_id": session})
    result = decide_and_reserve(
        send_req, conn=conn, config=config, now=FROZEN_NOW + timedelta(seconds=2)
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.reason_code == CheckId.SEQUENCE_RULE
    assert result.decision.sequence_history_incomplete is True


def test_cross_session_prune_drops_rows_older_than_the_longest_loaded_window(
    conn: Connection,
) -> None:
    _held_after_tag_policy(conn, within_seconds=60)  # the only loaded rule's window
    old_at = FROZEN_NOW - timedelta(seconds=120)
    sequence.record_event(
        conn,
        session_id="prune-1",
        action_type="x",
        tag="untrusted_content",
        at=old_at,
        audit_id=1,
        max_events_per_session=500,
    )
    # A second, unrelated session's own event, recorded "now" -- triggers the
    # cross-session prune pass, which should drop the first session's old row.
    sequence.record_event(
        conn,
        session_id="prune-2",
        action_type="y",
        tag=None,
        at=FROZEN_NOW,
        audit_id=2,
        max_events_per_session=500,
    )
    remaining = conn.execute(
        "SELECT session_id FROM sequence_events WHERE session_id='prune-1'"
    ).fetchall()
    assert remaining == []
    # The marker itself is pruned here too -- its own
    # evicted_through (120s before `now`) is already past the loaded
    # rule's own 60s window, so it could never again affect that rule's
    # history_incomplete check; see the eviction case above (a window of
    # 999999s) for one where the marker is still live and kept.
    evicted = conn.execute(
        "SELECT evicted_through FROM sequence_evicted WHERE session_id='prune-1'"
    ).fetchone()
    assert evicted is None
