"""Shadow policy evaluation: what a candidate policy would decide for a
request that was (or will be) actually decided under the live policy —
recorded for later comparison, never fed back into anything live.

**Scope, disclosed.** This evaluates a policy's own default-deny, bounds,
caps and declared tier, clamped by the kill switch the same way the live
engine's own first clamp does (``Tier.OBSERVE`` exempt; the kill switch
otherwise forces ``Tier.CONFIRM``) and in the live engine's own order: an
``OBSERVE`` read returns before bounds or caps are even checked; an engaged
switch denies right after bounds, before caps, for anything else; caps are
checked against the action's own caps and its effects' shared caps
together, exactly as a live decision reserves them. It does **not** model
the live engine's further escalation paths: effect-level tier floors, sequence policies,
approval-ref/mandate interactions, dry-run, or compensating commands. A
shadow verdict answers "what would this policy's own declared limits have
allowed", not "what would every escalation path the live engine has grown
have done to this exact request" — the two agree whenever no such path
fires, which is the common case, and the live decision is always the
authoritative one; a shadow verdict is advisory only, and the two are never
compared as though one overrides the other.

Nothing here reserves a cap, touches the kill switch, creates an approval,
or writes to ``actions_audit``. :func:`evaluate` is read-only; :func:`record`
writes only to ``shadow_decisions``, a table the decision engine itself never
reads.

**One sentence on what a shadow verdict answers, and what it does not:** it
answers what a policy's own default-deny, bounds, caps and tier (clamped by
the kill switch) would have decided; it does not answer what the live
engine's further escalation paths — effect-level tier floors, sequence
policies, approval-ref/mandate resumption, dry-run, the compensating-command
check — would have done, and a verdict from one of those paths is marked as
outside this coverage, never silently compared as though it agreed or
disagreed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from onedoor.guardrail import bounds, caps
from onedoor.guardrail.models import ActionRequest, CheckId, Decision, Policy, PolicyDecision, Tier
from onedoor.guardrail.policy import PolicyStore
from onedoor.store.clock import to_iso

COVERAGE_ID = "limits-v1"
"""The one stable name for what :func:`evaluate` checks, carried on every
`ShadowDecision`, every `shadow_decisions` row, and `policy_tests.compare`'s
own report header — a single id to version, not free text written fresh
(and potentially differently worded) at each call site. `limits-v1` covers
exactly: default-deny, bounds, caps, and tier clamped by the kill switch
(the module docstring above, and `docs/design/shadow_policy_evaluation.md`,
are the full write-up). A future version that covers more gets its own id,
`limits-v2` or a new name entirely — this one's own meaning never changes
under it, so a row already recorded under `limits-v1` stays interpretable
exactly as it was written, whatever a later version adds."""

_MODELED_DENIAL_REASONS = frozenset(
    {
        CheckId.DEFAULT_DENY,
        CheckId.BOUNDS,
        CheckId.RATE_EXHAUSTED,
        CheckId.BUDGET_EXHAUSTED,
        CheckId.COST_UNKNOWN,
        CheckId.KILL_SWITCH,
    }
)
_MODELED_PROPOSE_REASONS = frozenset({CheckId.TIER_CONFIRM})
_MODELED_EXECUTE_REASONS = frozenset({CheckId.PASSED, CheckId.OBSERVE})
_MODELED_REASON_CODES = (
    _MODELED_DENIAL_REASONS | _MODELED_PROPOSE_REASONS | _MODELED_EXECUTE_REASONS
)
"""Exactly the live engine's own reason codes that `limits-v1` can be
compared against — the ones a decision reached through default-deny,
bounds, caps, or the plain tier/kill-switch clamp actually carries. Every
other reason code (`effect_floor`, `sequence_rule`, `sequence_no_session`,
`resume_request_mismatch`, `expired`, `external_authorization`,
`present_bound`, `dry_run`, `no_compensating_command`, `sender_mismatch`,
`untrusted_input`, `malformed`, `plan_ref`) names a path `limits-v1` does
not model, deliberately — and a reason code this module has never heard of
falls here too, by construction, rather than being silently treated as
agreeing or disagreeing with a check it was never compared against."""


@dataclass(frozen=True)
class ShadowDecision:
    """What :func:`evaluate` found — the same four fields a `Decision`
    carries, with nothing an actual permit, reservation or audit row would
    add, plus the coverage id naming what was checked to reach it."""

    decision: Decision
    effective_tier: Tier
    reason_code: CheckId | None
    detail: str | None
    coverage: str = COVERAGE_ID


def evaluate(
    conn: sqlite3.Connection,
    policy: Policy,
    request: ActionRequest,
    *,
    now: datetime,
    tz: ZoneInfo,
    kill_switch_engaged: bool,
) -> ShadowDecision:
    """What `policy` would have decided for `request`, right now, read-only.

    `kill_switch_engaged` is passed in, not read here, so a caller comparing
    several candidate policies against the same moment reads the kill
    switch once, not once per candidate -- and so a caller studying a
    hypothetical ("what if the switch had been engaged") can simply pass
    `True` without needing a real engaged switch to do it.
    """
    if policy.is_default_deny:
        return ShadowDecision(
            Decision.DENIED, Tier.CONFIRM, CheckId.DEFAULT_DENY, "policy.is_default_deny == true"
        )

    # Step 1 (live): resolve the effective tier, kill switch included, before
    # anything else -- `OBSERVE` exempt; otherwise the switch forces CONFIRM
    # regardless of the policy's own declared tier, and is why, not merely
    # that a Tier-3 policy happens to be in confirm too.
    kill_switch_is_why = False
    if policy.tier == Tier.OBSERVE:
        effective_tier = Tier.OBSERVE
    elif kill_switch_engaged:
        effective_tier = Tier.CONFIRM
        kill_switch_is_why = True
    else:
        effective_tier = policy.tier

    # Step 5 (live): an OBSERVE read returns here, before bounds or caps are
    # ever checked.
    if effective_tier == Tier.OBSERVE:
        return ShadowDecision(Decision.EXECUTED, Tier.OBSERVE, CheckId.OBSERVE, None)

    # Step 6 (live): bounds.
    bounds_result = bounds.validate(policy.bounds, request.params)
    if not bounds_result.ok:
        return ShadowDecision(Decision.DENIED, Tier.CONFIRM, CheckId.BOUNDS, bounds_result.detail)

    # Step 7 (live): an engaged switch denies outright here, before caps --
    # proposing during an incident would still fill the approval queue.
    if kill_switch_is_why:
        return ShadowDecision(
            Decision.DENIED, Tier.CONFIRM, CheckId.KILL_SWITCH, "kill switch engaged; not proposed"
        )

    # Step 9 (live): the action's own caps AND its effects' shared caps,
    # together -- `policy.effects` only; a `param_effects` rule that would add
    # more is outside this coverage (the rule itself is not modeled).
    effect_caps = [
        (name, effect_policy.caps)
        for name in policy.effects
        if (effect_policy := PolicyStore().get_effect(conn, name)) is not None
    ]
    cap_result = caps.check_only(conn, policy, request, now, tz, effect_caps=effect_caps)
    if cap_result.exceeded:
        return ShadowDecision(Decision.DENIED, Tier.CONFIRM, cap_result.reason, cap_result.detail)

    if effective_tier == Tier.CONFIRM:
        return ShadowDecision(Decision.PROPOSED, effective_tier, None, None)
    return ShadowDecision(Decision.EXECUTED, effective_tier, None, None)


def _reason_text(reason_code: CheckId | str) -> str:
    """A reason code's own string, whether it's a real `CheckId` member or a
    plain string reached by a construction that skipped validation --
    `PolicyDecision` itself refuses an unknown string once validated, so
    only an unvalidated `live_decision` reaches the plain-string case."""
    return reason_code.value if isinstance(reason_code, CheckId) else str(reason_code)


def _is_resumption(live_decision: PolicyDecision) -> bool:
    """Whether `live_decision` resumed an approval, an approval reference, or
    a mandate ratification -- the one place this coverage's own notion of
    "this was a resumption" is decided, so `_compare_to_live` never grows a
    second, possibly different reading of the same question.

    The only fact that qualifies today: `approvers is not None` -- never
    `None` on a decision built by `_decide_and_reserve` for a resumption
    it resolved, even `[]` for a mandate-only resumption no human approver
    acted on, or for a bare admin override with no approval row to read one
    from. This is read from **the intent's own decision** -- the one
    `_decide_and_reserve` actually built and persisted, carrying whatever
    resumption facts it resolved -- never from a decision built fresh with
    those facts left out: `report_result`'s own executed decision reads
    them back from the intent's audit row for exactly this reason, rather
    than building a decision with the resumption stripped out and leaving
    nothing here to check.
    """
    return live_decision.approvers is not None


def _compare_to_live(shadow: ShadowDecision, live_decision: PolicyDecision) -> str:
    """One of `"agree"`, `"disagree"`, or `"live decided by <path>; not
    modeled"` -- never a bare truth value, since a live decision reached
    through a path `limits-v1` does not model is neither agreement nor
    disagreement; it was never compared against anything.

    A resumption is "not modeled" by `_is_resumption`'s own facts, not by
    its reason code alone: a Tier-3 resumption that executes reads
    `passed`, which IS in the modeled set, and comparing it against a
    shadow verdict that never modeled resumption at all would read as a
    disagreement for a path this coverage declares out of scope.
    """
    live_reason_code = live_decision.reason_code
    if _is_resumption(live_decision) or live_reason_code not in _MODELED_REASON_CODES:
        return f"live decided by {_reason_text(live_reason_code)}; not modeled"
    if live_reason_code in _MODELED_DENIAL_REASONS:
        agree = shadow.decision == Decision.DENIED and shadow.reason_code == live_reason_code
    elif live_reason_code in _MODELED_PROPOSE_REASONS:
        agree = shadow.decision == Decision.PROPOSED
    else:  # _MODELED_EXECUTE_REASONS
        agree = shadow.decision == Decision.EXECUTED
    return "agree" if agree else "disagree"


def record(
    conn: sqlite3.Connection,
    request: ActionRequest,
    shadow: ShadowDecision,
    *,
    policy_label: str,
    now: datetime,
    live_audit_id: int | None = None,
    live_decision: PolicyDecision | None = None,
) -> int:
    """Persist one shadow verdict. Returns the new row's id.

    `policy_label` is the caller's own name for the candidate policy
    (a version tag, a ticket id typed by the deployer, anything) -- this
    module has no concept of policy identity beyond what the caller gives
    it, since a `Policy` object carries no version of its own.

    `live_decision`, when given, is compared against `shadow` through
    `_compare_to_live` -- but only ever as "agree", "disagree", or "live
    decided by <path>; not modeled". A live decision whose own reason code
    names a path outside `shadow.coverage` is marked as such, never folded
    into agreement or disagreement with a check it was never put through;
    its row still carries the shadow verdict itself (not the live one) in
    `decision`/`effective_tier`/`reason_code`/`detail`, with the live
    decision's own reason code and the comparison recorded alongside it.
    """
    live_reason_code = (
        _reason_text(live_decision.reason_code) if live_decision is not None else None
    )
    comparison = _compare_to_live(shadow, live_decision) if live_decision is not None else None
    cur = conn.execute(
        "INSERT INTO shadow_decisions "
        "(request_id, live_audit_id, action_type, policy_label, coverage, decision, "
        " effective_tier, reason_code, detail, live_reason_code, comparison, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(request.request_id),
            live_audit_id,
            request.action_type,
            policy_label,
            shadow.coverage,
            shadow.decision.value,
            int(shadow.effective_tier),
            shadow.reason_code.value if shadow.reason_code is not None else None,
            shadow.detail,
            live_reason_code,
            comparison,
            to_iso(now),
        ),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid
