"""Approving a plan once (onedoor 0.11): proposal and
approval lifecycle. Matching and consuming an *active* plan against a live
decision lives in `onedoor.guardrail.plan_ref` instead -- this module never
imports the decision engine, the same separation `approvals`/`approval_ref`
already keep.

A plan is **proposed**, by an agent or an operator, and only becomes
**active** once a *different* identity approves it -- the same self-approval
exclusion `approvals.cas_approve` already enforces for every other
threshold-gated action in this engine. `propose()` creates a proposal row,
never an active plan.

A plan whose own `amount_ceiling` crosses at least one of its covered
actions' own two-person threshold (`onedoor.guardrail.approvals`' own
mechanism, `Policy.approval.two_person_above_eur`) needs a *second*,
different, identity before it activates -- a design requirement on top
of the general two-person mechanism, mirrored here the same way this
module already mirrors `cas_approve`'s self-approval exclusion.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import TypedDict

from onedoor._vendor.canonical import canon_decimal
from onedoor.guardrail.errors import ApprovalError, NeedsMoreApprovers, PlanError
from onedoor.guardrail.models import Policy
from onedoor.guardrail.policy import PolicyStore
from onedoor.store.clock import to_iso

ANY_RECIPIENT = "any recipient"
"""The literal text a plan's own record and its
approval text carry in place of an empty `recipients` list, wherever no
covered action declares a `recipient_param` at all -- there is nothing a
recipient ceiling could ever bound for that plan, so the record says so in
those exact words rather than an empty list a reader could mistake for "no
recipient is allowed", the opposite meaning."""


class ActionSpec(TypedDict, total=False):
    amount_param: str | None
    recipient_param: str | None


def recipients_text(recipients: list[str]) -> str:
    """The human-readable rendering of a plan's own recipient scope, for any
    caller building approval text: `"any recipient"` for an empty list,
    otherwise the recipients themselves, sorted and joined."""
    return ANY_RECIPIENT if not recipients else ", ".join(sorted(recipients))


def _policy_recipient_params(policy: Policy) -> frozenset[str]:
    """The parameter names this policy already restricts to an explicit
    list (`bounds.enum`) -- the one existing mechanism by which a policy
    "names a recipient parameter or list" (no dedicated field for this
    exists on `Policy`; an enum-bounded parameter, such as the shipped
    `account`/`payee`-style allowlists, is this engine's own idiom for a
    restricted-identity parameter). Empty means this policy names none."""
    return frozenset(policy.bounds.enum)


def _check_action_spec(action_type: str, spec: ActionSpec, *, policy: Policy) -> None:
    """Refuses a plan's own declaration for one covered action whenever its
    `amount_param` is not actually the field the policy reads as the
    amount (a real attack found against the first version of this check,
    which only asked whether `amount_param` was PRESENT, never whether it
    was the right one -- a plan naming `amount_param="fee"` against a
    policy that reads its cost from `amount_eur` opened every ceiling this
    plan ever claimed to bound, at every entry point, `strict_params` or
    not, because nothing here ever read `fee` back against the policy's
    own cost field).

    Three shapes, in order, whichever the policy actually declares:

    1. **`cost_param` declared** -- `amount_param` must equal it exactly.
       Anything else (absent, or a different name) ties the plan's own
       ceiling to a field the policy never reads as the cost, which is the
       same as not bounding it at all.
    2. **No `cost_param`, but a euro cap or a two-person threshold is** --
       refused outright, for every `amount_param` including a correct
       guess: without `cost_param` there is no SINGLE policy-declared
       field those caps apply to, so no `amount_param` a plan could name
       would ever be the right one to tie a ceiling to.
    3. **No `cost_param`, no euro cap, no two-person threshold, but
       `bounds.numeric` is non-empty** -- `amount_param` must name one of
       the numerically-bounded parameters; the plan's own ceiling applies
       to that field, the one thing here a request's own value is actually
       checked against.

    None of the three means this policy bounds no amount at all -- a plan
    naming no `amount_param` for it is not open-ended against anything,
    there being nothing to be open-ended against.
    """
    amount_param = spec.get("amount_param")
    if policy.cost_param is not None:
        if amount_param != policy.cost_param:
            raise PlanError(
                f"policy '{action_type}' reads its own cost from cost_param "
                f"{policy.cost_param!r}, but this plan names amount_param "
                f"{amount_param!r} for it -- its own ceiling would bound a field "
                "the policy never reads as the cost"
            )
    elif (
        policy.caps.eur_day is not None
        or policy.caps.eur_month is not None
        or (policy.approval is not None and policy.approval.two_person_above_eur is not None)
    ):
        raise PlanError(
            f"policy '{action_type}' bounds a euro cap or a two-person threshold "
            "but declares no cost_param -- there is no policy-declared amount a "
            "plan's own ceiling could ever be tied to, so this action cannot be "
            "covered by a plan at all"
        )
    elif policy.bounds.numeric:
        if amount_param is None or amount_param not in policy.bounds.numeric:
            raise PlanError(
                f"policy '{action_type}' bounds {sorted(policy.bounds.numeric)!r} "
                "numerically, but this plan names no matching amount_param for it "
                "-- its own ceiling would never be read"
            )
    recipient_params = _policy_recipient_params(policy)
    if recipient_params and spec.get("recipient_param") not in recipient_params:
        raise PlanError(
            f"policy '{action_type}' bounds a recipient parameter "
            f"({sorted(recipient_params)!r}), but this plan names no matching "
            "recipient_param for it -- its own recipient list would never be read"
        )


def propose(
    conn: sqlite3.Connection,
    approver: str,
    action_specs: dict[str, ActionSpec],
    count_ceiling: int,
    amount_ceiling: Decimal,
    recipients: set[str] | list[str],
    expires_at: datetime,
    now: datetime,
    *,
    policy_store: PolicyStore | None = None,
) -> int:
    """Create a PROPOSAL row -- `state='proposed'`, never active until
    `approve()` flips it. `approver` is recorded as who proposed it (the
    column that will later record who approved it is a separate one,
    `approved_by`, left `NULL` until that happens): `approve()` refuses the
    same identity approving its own proposal.

    `required_approvers_at_proposal` (the same
    shape as `approvals.create`'s own snapshot) is `required_approvers`
    evaluated against the covered actions' policies AS THEY STAND RIGHT
    NOW, frozen into the row -- the snapshot `approve()` later compares
    against the then-current policy, taking whichever is stricter.

    Refuses a plan for any covered action whose
    policy bounds an amount or a recipient unless this plan names the
    matching `amount_param`/`recipient_param` -- a plan that cannot read
    the amount or recipient a policy already bounds would be an
    open-ended authorization, approved against a ceiling that never
    applies. Raises `PlanError` before writing any row.
    """
    store = policy_store or PolicyStore()
    for action_type, spec in action_specs.items():
        _check_action_spec(action_type, spec, policy=store.get(conn, action_type))
    recipient_bound_declared = any(
        spec.get("recipient_param") is not None for spec in action_specs.values()
    )
    # One recipient list, one meaning. A stored `recipients_json` is
    # a single list read uniformly against every covered action -- if even
    # one of them names no `recipient_param` at all, that action ignores
    # the list completely while the record still shows it as though it
    # bounded everything this plan covers. Refused outright rather than
    # silently covering an action the list was never going to restrict.
    if recipient_bound_declared and any(
        spec.get("recipient_param") is None for spec in action_specs.values()
    ):
        unbound = sorted(
            action_type
            for action_type, spec in action_specs.items()
            if spec.get("recipient_param") is None
        )
        raise PlanError(
            f"this plan names a recipient_param for at least one covered action, "
            f"but not for {unbound!r} -- the stored recipient list would be "
            "silently ignored by those actions, which is not what the record "
            "would say it covers"
        )
    stored_recipients = sorted(recipients) if recipient_bound_declared else [ANY_RECIPIENT]
    snapshot_required = required_approvers(conn, action_specs, amount_ceiling, policy_store=store)
    cur = conn.execute(
        "INSERT INTO plans (proposed_by, approved_by, action_specs_json, count_ceiling, "
        "amount_ceiling, recipients_json, expires_at, consumed_count, consumed_amount, "
        "state, created_at, approved_at, required_approvers_at_proposal) "
        "VALUES (?, NULL, ?, ?, ?, ?, ?, 0, '0', 'proposed', ?, NULL, ?)",
        (
            approver,
            json.dumps(action_specs),
            count_ceiling,
            canon_decimal(amount_ceiling),
            json.dumps(stored_recipients),
            to_iso(expires_at),
            to_iso(now),
            snapshot_required,
        ),
    )
    return int(cur.lastrowid or 0)


def required_approvers(
    conn: sqlite3.Connection,
    action_specs: dict[str, ActionSpec],
    amount_ceiling: Decimal,
    *,
    policy_store: PolicyStore,
) -> int:
    """How many distinct approvers this plan needs before it activates, AS
    THE COVERED ACTIONS' POLICIES READ RIGHT NOW -- 1 unless
    `amount_ceiling` crosses the two-person threshold of at least one of
    them (a design requirement on top of the general two-person mechanism).

    Public (not `_required_approvers`) since `propose` now calls this too,
    to snapshot the answer at proposal time -- `approve` uses this same
    function again at approval time, and takes the stricter of the two
    (the same fix `approvals.required_approvers`/`cas_approve` already got
    for the general two-person rule): a policy edited
    between a plan's proposal and its approval must not let it activate
    with fewer approvers than the stricter of the two reads requires.
    """
    for action_type in action_specs:
        policy = policy_store.get(conn, action_type)
        if (
            policy.approval is not None
            and policy.approval.two_person_above_eur is not None
            and amount_ceiling > policy.approval.two_person_above_eur
        ):
            return 2
    return 1


def approve(
    conn: sqlite3.Connection,
    plan_id: int,
    approver: str,
    now: datetime,
    *,
    policy_store: PolicyStore | None = None,
) -> None:
    """Flip proposed -> active iff still proposed, `approver` did not
    propose it, and (above the two-person threshold of at least one of the
    plan's own covered actions) a second, DIFFERENT identity has now
    approved too. Mirrors `approvals.cas_approve`'s own shape: the same
    self-approval refusal, and the same same-identity-twice refusal.

    Do not wrap this call in `onedoor.store.db.tx` -- see `approvals.
    cas_approve`'s own docstring for why; the same reasoning applies here,
    unchanged: the mutation is already one atomic, self-committing `UPDATE`,
    and an outer explicit transaction would defer that commit to its own
    exit, so `NeedsMoreApprovers` would roll back the very approver this
    call just recorded.
    """
    row = conn.execute(
        "SELECT proposed_by, state, action_specs_json, amount_ceiling, approvers_json, "
        "required_approvers_at_proposal FROM plans WHERE id=?",
        (plan_id,),
    ).fetchone()
    if row is None:
        raise ApprovalError(f"plan {plan_id} does not exist")
    if row["proposed_by"] == approver:
        raise ApprovalError(
            f"plan {plan_id} was proposed by {approver!r}; the principal that "
            f"proposed a plan cannot approve it"
        )
    if row["state"] != "proposed":
        raise ApprovalError(f"plan {plan_id} is not awaiting approval")
    current_json = row["approvers_json"] or "[]"
    current_approvers: list[str] = json.loads(current_json)
    if approver in current_approvers:
        raise ApprovalError(
            f"plan {plan_id} was already approved by {approver!r}; the same "
            f"identity approving twice does not count as two"
        )
    store = policy_store or PolicyStore()
    action_specs: dict[str, ActionSpec] = json.loads(row["action_specs_json"])
    current_required = required_approvers(
        conn, action_specs, Decimal(row["amount_ceiling"]), policy_store=store
    )
    # The stricter of the two (same fix as approvals.cas_approve):
    # `None` -- a row from before this migration, with
    # no snapshot recorded -- falls back to the current policy alone, the
    # same behaviour this program always had.
    snapshot_required = row["required_approvers_at_proposal"]
    required = (
        current_required
        if snapshot_required is None
        else max(current_required, int(snapshot_required))
    )
    new_approvers = [*current_approvers, approver]
    fully_approved = len(new_approvers) >= required
    cur = conn.execute(
        "UPDATE plans SET approvers_json=?, state=?, approved_by=?, approved_at=? "
        "WHERE id=? AND state='proposed' AND approvers_json=?",
        (
            json.dumps(new_approvers),
            "active" if fully_approved else "proposed",
            approver if fully_approved else None,
            to_iso(now) if fully_approved else None,
            plan_id,
            current_json,
        ),
    )
    if cur.rowcount == 0:
        raise ApprovalError(f"plan {plan_id} is not awaiting approval")
    if not fully_approved:
        raise NeedsMoreApprovers(
            plan_id, required=required, recorded=len(new_approvers), kind="plan"
        )


def deny(conn: sqlite3.Connection, plan_id: int, approver: str, now: datetime) -> None:
    """Flip proposed -> denied iff still proposed. An active plan cannot be
    denied -- it can only run out its own ceilings or expiry."""
    cur = conn.execute(
        "UPDATE plans SET state='denied', approved_by=?, approved_at=? "
        "WHERE id=? AND state='proposed'",
        (approver, to_iso(now), plan_id),
    )
    if cur.rowcount == 0:
        raise ApprovalError(f"plan {plan_id} is not awaiting approval")
