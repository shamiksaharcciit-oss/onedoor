"""With only `tag_as`-style (tagging only, no rule)
policies loaded, `longest_window_seconds` returns `None`, and the
cross-session prune used to skip entirely rather than fall back to a
default -- sequence_events, and separately sequence_evicted, grew
without bound forever. Reproduces the report's own shape: a tagging-only
policy, an old event, a trigger from an unrelated session.
"""

from __future__ import annotations

from datetime import timedelta
from sqlite3 import Connection

from onedoor.guardrail import policy_loader, sequence
from onedoor.guardrail.models import Policy, SequencePolicy, Tier
from tests.conftest import FROZEN_NOW

READ = "demo.seq_unbounded_read"


def _tag_only_policy(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(action_type=READ, tier=Tier.OBSERVE, sequence=SequencePolicy(tag_as="marked")),
    )


def test_events_are_pruned_at_a_default_bound_even_with_no_rule_loaded(
    conn: Connection,
) -> None:
    _tag_only_policy(conn)
    assert sequence.longest_window_seconds(conn) is None  # tag_as only -- no rule at all

    old_at = FROZEN_NOW - timedelta(seconds=sequence.DEFAULT_PRUNE_SECONDS + 60)
    sequence.record_event(
        conn,
        session_id="unbounded-1",
        action_type=READ,
        tag="marked",
        at=old_at,
        audit_id=1,
        max_events_per_session=500,
    )
    # An unrelated session's own event, recorded "now" -- triggers the
    # cross-session prune pass.
    sequence.record_event(
        conn,
        session_id="unbounded-2",
        action_type=READ,
        tag="marked",
        at=FROZEN_NOW,
        audit_id=2,
        max_events_per_session=500,
    )
    remaining = conn.execute(
        "SELECT session_id FROM sequence_events WHERE session_id='unbounded-1'"
    ).fetchall()
    assert remaining == [], "an old event must not survive forever just because no rule is loaded"


def test_a_recent_event_is_unaffected_with_no_rule_loaded(conn: Connection) -> None:
    _tag_only_policy(conn)
    recent_at = FROZEN_NOW - timedelta(seconds=60)
    sequence.record_event(
        conn,
        session_id="unbounded-3",
        action_type=READ,
        tag="marked",
        at=recent_at,
        audit_id=1,
        max_events_per_session=500,
    )
    sequence.record_event(
        conn,
        session_id="unbounded-4",
        action_type=READ,
        tag="marked",
        at=FROZEN_NOW,
        audit_id=2,
        max_events_per_session=500,
    )
    remaining = conn.execute(
        "SELECT session_id FROM sequence_events WHERE session_id='unbounded-3'"
    ).fetchall()
    assert len(remaining) == 1


def test_a_stale_eviction_marker_is_itself_pruned(conn: Connection) -> None:
    """`sequence_evicted` kept one row per session ever
    pruned, forever. A marker older than the same cutoff used for events
    cannot affect any currently-loaded rule's history_incomplete check
    either (there is no rule loaded at all here), so it is pruned too."""
    from onedoor.guardrail.models import Bounds, SequenceRule

    policy_loader.upsert(
        conn,
        Policy(
            action_type=READ,
            tier=Tier.OBSERVE,
            bounds=Bounds(strict_params=False),
            sequence=SequencePolicy(
                rules=[SequenceRule(after_tag="marked", within_seconds=60, effect="hold")]
            ),
        ),
    )
    old_at = FROZEN_NOW - timedelta(seconds=120)
    sequence.record_event(
        conn,
        session_id="stale-marker-1",
        action_type=READ,
        tag="marked",
        at=old_at,
        audit_id=1,
        max_events_per_session=500,
    )
    sequence.record_event(
        conn,
        session_id="stale-marker-2",
        action_type=READ,
        tag="marked",
        at=FROZEN_NOW,
        audit_id=2,
        max_events_per_session=500,
    )
    row = conn.execute(
        "SELECT evicted_through FROM sequence_evicted WHERE session_id='stale-marker-1'"
    ).fetchone()
    assert row is None
