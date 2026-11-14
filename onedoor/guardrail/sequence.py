"""Rules across a sequence (onedoor 0.11): policies over what
came before, in the same session. Two moving parts:

- :func:`record_event` — called once a settling action's own policy carries a
  `sequence` block at all (`tag_as` set or not), after the decision that
  settles it (the OBSERVE return inside :func:`onedoor.guardrail.decision.
  decide_and_reserve`, or a `success` outcome inside :func:`onedoor.guardrail.
  decision.report_result`). Appends one row to `sequence_events`, then enforces
  the per-session cap and the cross-session prune.
- :func:`evaluate` — called before bounds and caps, the same placement as the
  untrusted-input check (a stop here is about history, not this action's own
  value). Reads `policy.sequence.rules` against this session's own prior rows.

Both read and write through the same table; neither ever updates a row in
place (append-only, the same discipline as `actions_audit` itself).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from sqlite3 import Connection
from typing import Any

from onedoor.guardrail.models import (
    ActionRequest,
    CountOverSpec,
    Policy,
    SequencePolicy,
    SequenceRule,
)
from onedoor.guardrail.numeric import numeric_value
from onedoor.store.clock import from_iso, to_iso

DEFAULT_PRUNE_SECONDS = 30 * 24 * 3600
"""The bound `_enforce_cross_session_prune` prunes to
when no currently loaded policy's `sequence.rules` gives it a real
window to prune against -- with only `tag_as`-style (tagging only, no
rule) policies loaded, `longest_window_seconds` returns `None`, and
pruning used to skip entirely rather than fall back to this default,
leaving every session's events (and, separately, every session's own
`sequence_evicted` marker -- see `_prune_evicted_markers`) to grow
without bound forever. 30 days -- long enough that no real deployment's
own rule window is likely to exceed it, short enough that the table
stays bounded regardless."""


def record_event(
    conn: Connection,
    *,
    session_id: str,
    action_type: str,
    tag: str | None,
    at: datetime,
    audit_id: int,
    max_events_per_session: int,
) -> None:
    """Appends one row, then enforces both bounds. Call only for a settled
    action whose policy carries a `sequence` block at all -- an action type
    with `sequence` unset is invisible to this table entirely, by construction
    (nothing ever calls this for it)."""
    conn.execute(
        "INSERT INTO sequence_events (session_id, action_type, tag, at, audit_id) "
        "VALUES (?,?,?,?,?)",
        (session_id, action_type, tag, to_iso(at), audit_id),
    )
    _enforce_per_session_cap(conn, session_id=session_id, max_events=max_events_per_session)
    _enforce_cross_session_prune(conn, now=at)


def _enforce_per_session_cap(conn: Connection, *, session_id: str, max_events: int) -> None:
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM sequence_events WHERE session_id=?", (session_id,)
    ).fetchone()
    overflow = count - max_events
    if overflow <= 0:
        return
    # Oldest first: the `overflow` rows with the smallest `at` (ties broken by
    # `id`, insertion order, since `at` can repeat within one transaction).
    rows = conn.execute(
        "SELECT id, at FROM sequence_events WHERE session_id=? ORDER BY at ASC, id ASC LIMIT ?",
        (session_id, overflow),
    ).fetchall()
    newest_evicted_at = rows[-1]["at"]
    conn.execute(
        "DELETE FROM sequence_events WHERE id IN ({})".format(",".join("?" * len(rows))),
        tuple(r["id"] for r in rows),
    )
    _mark_evicted_through(conn, session_id=session_id, through=newest_evicted_at)


def _mark_evicted_through(conn: Connection, *, session_id: str, through: str) -> None:
    conn.execute(
        "INSERT INTO sequence_evicted (session_id, evicted_through) VALUES (?,?) "
        "ON CONFLICT(session_id) DO UPDATE SET evicted_through="
        "CASE WHEN excluded.evicted_through > sequence_evicted.evicted_through "
        "THEN excluded.evicted_through ELSE sequence_evicted.evicted_through END",
        (session_id, through),
    )


def _enforce_cross_session_prune(conn: Connection, *, now: datetime) -> None:
    """No loaded policy's own rule can legitimately need to look further back
    than the longest `within_seconds` any of them uses -- a row past that, in
    ANY session, is dead weight. Marks `evicted_through` for every session a
    row is actually pruned from, same as the per-session prune above.

    With no rule loaded at all (`longest_window_seconds`
    returns `None` -- every loaded policy's `sequence` block, if any, is
    `tag_as`-only), this now prunes to `DEFAULT_PRUNE_SECONDS` instead of
    skipping entirely -- events are bounded either way, never left to
    grow forever just because nothing is currently checking history.
    Also prunes `sequence_evicted` itself (`_prune_evicted_markers`): a
    marker older than the same cutoff could not matter to any rule's
    `history_incomplete` check either, by the same reasoning.
    """
    longest = longest_window_seconds(conn)
    window = longest if longest is not None else DEFAULT_PRUNE_SECONDS
    cutoff = to_iso(now - timedelta(seconds=window))
    affected = conn.execute(
        "SELECT DISTINCT session_id, "
        "(SELECT MAX(at) FROM sequence_events se2 "
        " WHERE se2.session_id = se1.session_id AND se2.at < ?) AS newest_evicted_at "
        "FROM sequence_events se1 WHERE at < ?",
        (cutoff, cutoff),
    ).fetchall()
    conn.execute("DELETE FROM sequence_events WHERE at < ?", (cutoff,))
    for row in affected:
        if row["newest_evicted_at"] is not None:
            _mark_evicted_through(
                conn, session_id=row["session_id"], through=row["newest_evicted_at"]
            )
    _prune_evicted_markers(conn, cutoff=cutoff)


def _prune_evicted_markers(conn: Connection, *, cutoff: str) -> None:
    """`sequence_evicted` kept one row per session ever
    pruned, forever -- a marker whose own `evicted_through` is older than
    the same cutoff `_enforce_cross_session_prune` just used for events
    cannot affect any rule's `history_incomplete` check either (every
    rule's own window reaches back at most that far), so it is dead
    weight exactly the same way an events row past that cutoff is."""
    conn.execute("DELETE FROM sequence_evicted WHERE evicted_through < ?", (cutoff,))


def longest_window_seconds(conn: Connection) -> int | None:
    """The longest `within_seconds` any currently loaded policy's `sequence`
    block uses (an `after_tag` rule's own field, or a `count_over` spec's own
    nested field) -- `None` when no loaded policy declares `sequence` at all."""
    longest: int | None = None
    for (sequence_json,) in conn.execute(
        "SELECT sequence_json FROM policies WHERE sequence_json IS NOT NULL"
    ).fetchall():
        policy_seq = SequencePolicy.model_validate_json(sequence_json)
        for rule in policy_seq.rules:
            window = _rule_window_seconds(rule)
            if longest is None or window > longest:
                longest = window
    return longest


@dataclass(frozen=True)
class SequenceCheckResult:
    matched_effect: str | None  # "hold" | "deny" | None
    matched_rule: str | None
    events_considered: int
    history_incomplete: bool
    no_session: bool = False
    """A policy whose own `rules` is non-empty was presented with no
    `session_id` to check them against, and the policy does not declare
    `session_optional: true` -- the caller must not be able to avoid every
    sequence rule just by leaving `session_id` out. The call is held
    (`CheckId.SEQUENCE_NO_SESSION`) rather than silently evaluated as though
    no rule existed. Never true at the same time as a real `matched_effect`:
    this is itself the only outcome when it fires."""


def evaluate(
    conn: Connection, request: ActionRequest, policy: Policy, *, now: datetime
) -> SequenceCheckResult:
    """Checked before bounds and caps. `policy.sequence` absent, or its own
    `rules` empty, means nothing to check -- the opt-in default, same as
    every other feature here. `rules` non-empty with no `session_id`
    presented is NOT "nothing to check": it is held, unless the policy opts
    out with `session_optional: true` (see `SequenceCheckResult.no_session`)."""
    if policy.sequence is None or not policy.sequence.rules:
        return SequenceCheckResult(None, None, 0, False)
    if request.session_id is None:
        if policy.sequence.session_optional:
            return SequenceCheckResult(None, None, 0, False)
        return SequenceCheckResult(None, None, 0, False, no_session=True)

    session_id = request.session_id
    evicted_row = conn.execute(
        "SELECT evicted_through FROM sequence_evicted WHERE session_id=?", (session_id,)
    ).fetchone()
    evicted_through = from_iso(evicted_row["evicted_through"]) if evicted_row else None

    total_considered = 0
    history_incomplete = False
    deny_match: str | None = None
    hold_match: str | None = None

    for rule in policy.sequence.rules:
        window_start = now - timedelta(seconds=_rule_window_seconds(rule))
        if evicted_through is not None and evicted_through > window_start:
            # This rule's own window reaches further back than this session's
            # history still holds -- fail closed: its own effect applies, and
            # the receipt says the answer was not a complete one, rather than
            # silently evaluating against a partial table and calling it
            # conclusive.
            history_incomplete = True
            name = _rule_name(rule)
            if rule.effect == "deny":
                deny_match = deny_match or name
            else:
                hold_match = hold_match or name
            continue

        if rule.after_tag is not None:
            rows = conn.execute(
                "SELECT COUNT(*) AS n FROM sequence_events WHERE session_id=? AND tag=? AND at>=?",
                (session_id, rule.after_tag, to_iso(window_start)),
            ).fetchone()
            total_considered += rows["n"]
            if rows["n"] > 0:
                name = _rule_name(rule)
                if rule.effect == "deny":
                    deny_match = deny_match or name
                else:
                    hold_match = hold_match or name
            continue

        # count_over
        spec = rule.count_over
        assert spec is not None
        if spec.amount_param is not None and request.action_type == spec.action_type:
            # Self-referential (the common case: a wildcard or the same action
            # type watching its own history) -- the call being decided right
            # now counts toward its own threshold check, per the design note.
            # A rule watching a DIFFERENT action type's history has no such
            # value to check on the current request at all, so it is not
            # gated this way -- it counts the named type's history
            # unconditionally.
            current = numeric_value(request.params.get(spec.amount_param))
            if current is None or current <= spec.threshold_eur:  # type: ignore[operator]
                continue  # this call itself does not exceed the threshold
        prior_rows = conn.execute(
            "SELECT se.audit_id, aa.params_json FROM sequence_events se "
            "JOIN actions_audit aa ON aa.id = se.audit_id "
            "WHERE se.session_id=? AND se.action_type=? AND se.at>=?",
            (session_id, spec.action_type, to_iso(window_start)),
        ).fetchall()
        total_considered += len(prior_rows)
        prior_count = _count_over_threshold(prior_rows, spec)
        if prior_count >= spec.max_count:
            name = _rule_name(rule)
            if rule.effect == "deny":
                deny_match = deny_match or name
            else:
                hold_match = hold_match or name

    if deny_match is not None:
        return SequenceCheckResult("deny", deny_match, total_considered, history_incomplete)
    if hold_match is not None:
        return SequenceCheckResult("hold", hold_match, total_considered, history_incomplete)
    return SequenceCheckResult(None, None, total_considered, history_incomplete)


def _rule_window_seconds(rule: SequenceRule) -> int:
    if rule.after_tag is not None:
        assert rule.within_seconds is not None
        return rule.within_seconds
    assert rule.count_over is not None
    return rule.count_over.within_seconds


def _rule_name(rule: SequenceRule) -> str:
    if rule.after_tag is not None:
        return f"after_tag:{rule.after_tag}"
    assert rule.count_over is not None
    return f"count_over:{rule.count_over.action_type}"


def _count_over_threshold(rows: list[Any], spec: CountOverSpec) -> int:
    if spec.amount_param is None:
        return len(rows)
    count = 0
    for row in rows:
        params = json.loads(row["params_json"], parse_float=Decimal)
        value = numeric_value(params.get(spec.amount_param))
        if value is not None and value > spec.threshold_eur:  # type: ignore[operator]
            count += 1
    return count
