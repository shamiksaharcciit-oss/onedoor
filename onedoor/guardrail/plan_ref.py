"""Resolving a PEP-presented `plan_ref` (onedoor 0.11).

A human already approved a *plan* -- a bounded set of action types, ceilings and
an expiry -- through `onedoor.guardrail.plans`. A later request presents a
reference to it, and this module answers the one question a plan can ever
answer: **does this call fall inside what was approved, with room left?** A
plan replaces exactly the approval step; it is consulted only at the one
point in `decide_and_reserve` where that step would otherwise fire, and every
other check (bounds, caps, the kill switch, untrusted-input, sequence rules, a
bound permit, `irreversible_requires`) still decides fully on its own merits,
before and after this ever runs.

Same anti-probing shape as `approval_ref`: a bad, expired, exhausted or
mismatched reference evaluates as **absent**, never as an error -- the action
re-evaluates on its own merits and a Tier-3 action simply proposes again.

Matching and spending are two separate steps, deliberately. `resolve_match`
only reads: it answers whether this call falls inside the plan, with room
left, and what the plan's own counters would become -- it writes nothing.
A caller must call `apply_match` itself, and only once it has independently
confirmed the call is actually going to execute (not a dry run, not then
denied by caps or a budget) -- a plan's ceilings exist to bound what actually
happens, not what merely proposed to. Both must run inside the same `BEGIN
IMMEDIATE` transaction `decide_and_reserve` already holds for the whole
decision: nothing else can observe or change this plan's row between the two
calls, so `apply_match` writing back exactly the counters `resolve_match`
already computed, inside that same lock, is race-free by construction -- the
same reasoning `approval_ref.resolve`'s own read-then-conditional-update
already relies on, extended across two calls instead of one.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from onedoor._vendor.canonical import canon_decimal
from onedoor.guardrail.errors import PlanError
from onedoor.guardrail.models import ActionRequest
from onedoor.guardrail.numeric import numeric_value
from onedoor.guardrail.plans import _check_action_spec, required_approvers
from onedoor.guardrail.policy import PolicyStore
from onedoor.store.clock import to_iso


@dataclass(frozen=True)
class PlanMatch:
    plan_id: int
    consumed_count_after: int
    consumed_amount_after: Decimal | None
    """`None` when the matched action name declares no `amount_param` -- there
    is no amount to add, and the plan's own `consumed_amount` is untouched."""


def resolve_match(
    conn: sqlite3.Connection,
    *,
    plan_ref: int | None,
    request: ActionRequest,
    now: datetime,
    policy_store: PolicyStore | None = None,
) -> PlanMatch | None:
    """Does `plan_ref` name an active plan this call falls inside, with room
    left? Read-only: computes what the plan's own counters would become, but
    writes nothing -- a caller that goes on to actually execute the call
    must still call `apply_match` itself. `None` for every way a reference
    can fail to apply -- absent, unknown, not active, expired, wrong action,
    missing a declared param, a non-positive or non-finite amount, over
    either ceiling, an unlisted recipient, or a
    declared param the action's CURRENT policy no longer accepts as enough
    -- all evaluated identically, as if no plan had been presented at all.

    The item-2 check re-runs `plans.propose`'s own shape check against
    today's policy, not the one in force when this plan was proposed: a
    plan proposed honestly, naming no `amount_param`/`recipient_param`
    because nothing bounded them yet, must not go on matching once the
    covered action's policy is edited to bound one -- the same "current
    policy, not the proposal-time one" reasoning `plans.required_approvers`
    already applies to the approver count.
    """
    if plan_ref is None:
        return None
    if not -(2**63) <= plan_ref < 2**63:
        return None

    row = conn.execute(
        "SELECT state, action_specs_json, count_ceiling, amount_ceiling, "
        "recipients_json, expires_at, consumed_count, consumed_amount, approvers_json "
        "FROM plans WHERE id=?",
        (plan_ref,),
    ).fetchone()
    if row is None or row["state"] != "active":
        return None
    if str(row["expires_at"]) <= to_iso(now):
        return None

    specs = json.loads(row["action_specs_json"])
    spec = specs.get(request.action_type)
    if spec is None:
        return None
    store = policy_store or PolicyStore()
    try:
        _check_action_spec(request.action_type, spec, policy=store.get(conn, request.action_type))
    except PlanError:
        return None
    # The same stricter-of-two-reads rule already
    # applies at a plan's own approval -- extended here to MATCH time, for a
    # plan that was already active when a covered action's policy tightened
    # further still. An already-active plan keeps the approver count it
    # actually got; if the action's CURRENT policy would now need more than
    # that, this plan no longer carries enough authorization to match, and
    # the call falls back to ordinary approval instead of spending against a
    # ceiling a single approver can no longer open.
    current_required = required_approvers(
        conn, specs, Decimal(str(row["amount_ceiling"])), policy_store=store
    )
    recorded_approvers = len(json.loads(row["approvers_json"] or "[]"))
    if current_required > recorded_approvers:
        return None
    amount_param = spec.get("amount_param")
    recipient_param = spec.get("recipient_param")

    amount: Decimal | None = None
    if amount_param is not None:
        if amount_param not in request.params:
            return None
        amount = numeric_value(request.params[amount_param])
        # `numeric_value` already refuses a non-finite value (NaN, +/-inf);
        # a plan's own ceiling is a one-way accumulator, so a value that is
        # not strictly positive (zero, or negative) does not match either --
        # letting one through would let it LOWER `consumed_amount`, spending
        # back room a ceiling already granted rather than using any.
        if amount is None or amount <= 0:
            return None

    if recipient_param is not None:
        if recipient_param not in request.params:
            return None
        recipient = request.params[recipient_param]
        recipients = json.loads(row["recipients_json"])
        if not isinstance(recipient, str) or recipient not in recipients:
            return None

    new_count = int(row["consumed_count"]) + 1
    if new_count > int(row["count_ceiling"]):
        return None

    consumed_amount = Decimal(str(row["consumed_amount"]))
    new_amount = consumed_amount if amount is None else consumed_amount + amount
    if amount is not None and new_amount > Decimal(str(row["amount_ceiling"])):
        return None

    return PlanMatch(
        plan_id=plan_ref,
        consumed_count_after=new_count,
        consumed_amount_after=None if amount is None else new_amount,
    )


def apply_match(conn: sqlite3.Connection, match: PlanMatch) -> None:
    """Spends what `resolve_match` already found room for -- called only once
    a caller has independently confirmed the call is actually going to
    execute (never for a dry run, never after caps or a budget goes on to
    deny the same call). Writes the exact absolute counters `resolve_match`
    already computed, gated by the same CAS discipline `approval_ref.
    resolve` and `caps.check_and_reserve` both rely on: the UPDATE's own
    WHERE re-checks `state='active'`, inside the one `BEGIN IMMEDIATE`
    transaction `decide_and_reserve` already holds for the whole decision --
    nothing else could have changed this plan's row since `resolve_match`
    read it, so writing exactly that result back is race-free by
    construction, not merely by the earlier read having looked current.
    `consumed_amount_after` is `None` when the matched action declares no
    `amount_param` -- that column is simply left untouched."""
    if match.consumed_amount_after is None:
        cur = conn.execute(
            "UPDATE plans SET consumed_count=? WHERE id=? AND state='active'",
            (match.consumed_count_after, match.plan_id),
        )
    else:
        cur = conn.execute(
            "UPDATE plans SET consumed_count=?, consumed_amount=? WHERE id=? AND state='active'",
            (match.consumed_count_after, canon_decimal(match.consumed_amount_after), match.plan_id),
        )
    assert cur.rowcount == 1, (
        f"plan {match.plan_id} row changed between resolve_match and apply_match "
        "within what must be the same transaction"
    )
