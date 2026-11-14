"""The decision half of the engine — the Policy Decision Point (PDP).

v0.2 splits the executor into two public phases so that enforcement can live
anywhere (an in-process connector registry, an MCP proxy, an API gateway
filter) while the decision semantics stay in exactly one place:

- :func:`decide_and_reserve` — Tx A. Runs the full ordered check pipeline
  (kill switch -> policy/default-deny -> tier-1 integrity -> bounds -> dry-run
  -> caps check-and-reserve) and records the execution *intent* in the
  append-only audit log. Returns either a terminal :class:`ActionResult`
  (denied / proposed / dry-run / observed / replayed) or a
  :class:`PermittedIntent` — an obligation for the caller to enforce.

- :func:`report_result` — Tx B. The enforcement point calls this exactly once
  after acting (or failing to act), which appends the linked result row and
  publishes the outcome.

The in-process executor (`evaluate_and_execute`) is now a thin composition of
these two phases around a connector call; external enforcement points compose
them around whatever their "act" is. The audit log, cap accounting, undo
windows and approval flow are identical in both cases — one door, wherever the
door is installed.
"""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from sqlite3 import Connection
from uuid import UUID

from onedoor.guardrail import (
    approval_ref,
    approvals,
    audit,
    bounds,
    caps,
    killswitch,
    mandate,
    opaque_hosts,
    sequence,
)
from onedoor.guardrail import (
    plan_ref as plan_ref_mod,
)
from onedoor.guardrail.audit import RowSource
from onedoor.guardrail.models import (
    ActionRequest,
    ActionResult,
    CheckId,
    Decision,
    DecisionRef,
    EngineConfigLike,
    JsonValue,
    Outcome,
    PolicyDecision,
    Source,
    Tier,
)
from onedoor.guardrail.policy import PolicyStore
from onedoor.guardrail.rebuild import RebuiltIntent
from onedoor.guardrail.trace import Trace
from onedoor.guardrail.urlcanon import (
    CANON_SCHEMA,
    CanonicalizationError,
    url_rule_matches,
)
from onedoor.store import bus
from onedoor.store.clock import from_iso, to_iso
from onedoor.store.db import tx

# EngineConfig lives in executor.py for backwards compatibility; import lazily
# to avoid a circular import at module load.


def _decision_ref(
    conn: Connection, *, audit_id: int, request_id: UUID, decision: Decision, config: object
) -> DecisionRef | None:
    """Fetch the audit row just written and build its reference, or `None` if
    this deployment has not configured an issuer (`audit.build_decision_ref`
    does the actual construction -- shared with the replay-reconstruction path,
    which cannot import this module without a cycle).

    Reads the row BACK from the connection rather than re-serializing values
    already in hand: the row as SQLite actually stored it is the one thing
    `onedoor.decision_digest.decision_digest` and a later `python -m
    onedoor.export` are both guaranteed to agree on.
    """
    issuer = getattr(config, "issuer", None)
    if not issuer:
        return None
    row = conn.execute("SELECT * FROM actions_audit WHERE id=?", (audit_id,)).fetchone()
    return audit.build_decision_ref(row, request_id=request_id, decision=decision, issuer=issuer)


@dataclass(frozen=True)
class PermittedIntent:
    """A permitted action whose execution is now the caller's obligation.

    Produced by :func:`decide_and_reserve` after Tx A commits: the caps are
    reserved, the intent row is in the audit log, and the undo window (if any)
    is set. The enforcement point MUST follow up with :func:`report_result`
    exactly once, whatever happened.
    """

    request: ActionRequest
    intent_audit_id: int
    effective_tier: Tier
    nominal_tier: Tier
    compensating_command: str | None
    undo_until: datetime | None
    undo_of: int | None
    present_bound: str | None = None
    """AADP -03 §6. Present iff the policy declared one -- a PEP that
    does not recognize the obligation MUST refuse to exercise this permit itself and
    report `not_attempted` per the fail-closed rule; onedoor's own packaged PEPs do
    not implement audience presentation yet (see the design note on this obligation)
    and must do exactly that."""
    bound_permit: str | None = None
    """The signed bound permit (compact JWS, bound-permit profile §§3-4), present
    iff the policy declared `bound_permit_action_type` -- `decide_and_reserve`
    already refused the action before caps were ever reserved if issuance was not
    possible (no issuer configured, no presenter key thumbprint), so by the time a
    `PermittedIntent` exists with `present_bound` set and `bound_permit_action_type`
    configured, this is always populated. `None` when the policy asked for no bound
    permit at all -- unchanged from before this obligation existed."""
    sequence_tagged: bool = False
    """Whether the policy carried a `sequence` block at all (`tag_as` set or
    not) -- `report_result` only ever appends a `sequence_events` row when this
    is true, whatever `sequence_tag` itself holds."""
    sequence_tag: str | None = None
    """The policy's own `sequence.tag_as`, resolved once at decide time so
    `report_result` need not re-look up the policy later -- `None` either when
    `sequence_tagged` is false (nothing recorded at all) or when it is true but
    the policy declared no tag (recorded, untagged -- `count_over` still
    matches it by `action_type` alone)."""
    decision_ref: DecisionRef | None = None
    """A reference to this intent's own `exec_intent` row (ruling on joining a
    onedoor decision to a onetrace run), `verdict="permit"`. Present iff
    `EngineConfigLike` declares a non-empty `issuer`; a deployment that has not
    configured one gets no reference, never a guessed value. `report_result`
    copies this same reference onto the final `ActionResult` unchanged -- a
    connector failure after this permit is granted does not change what was
    decided."""
    plan_ref: int | None = None
    """The plan (onedoor 0.11) whose match satisfied this
    permit's own approval step -- `None` when no plan decided this call.
    Surfaced here (unlike the untrusted/sequence receipt fields, which a live
    caller reads back from the audit row or a later terminal `ActionResult`)
    because a caller presenting `plan_ref` needs to know, at the moment of
    the call, how much of the plan it just spent."""
    plan_consumed_count_after: int | None = None
    """The matched plan's own `consumed_count` immediately after this call --
    `None` unless `plan_ref` is set."""
    plan_consumed_amount_after: Decimal | None = None
    """The matched plan's own `consumed_amount` immediately after this call --
    `None` unless `plan_ref` is set, or the matched action name declares no
    `amount_param`."""


def decide_and_reserve(
    request: ActionRequest,
    *,
    conn: Connection,
    config: EngineConfigLike,
    now: datetime,
    policy_store: PolicyStore | None = None,
    approved_override: bool = False,
    resumes_audit_id: int | None = None,
    principal: str | None = None,
    consumes_approval: int | None = None,
    thread_id: str | None = None,
    tool_call_id: str | None = None,
) -> ActionResult | PermittedIntent:
    """Phase A: evaluate the ordered checks; reserve caps; record intent.

    Returns an :class:`ActionResult` when the decision is terminal (nothing to
    enforce), or a :class:`PermittedIntent` when the action may proceed and the
    caller owns execution + :func:`report_result`.

    `resumes_audit_id`: set by a resumption (an approval or a mandate
    ratification resuming through :func:`evaluate_and_execute`) to the
    audit id of the proposal it resumes -- the row this call's own audit row
    names as what it resumes, so an evidence reader is not left assuming a
    link that no row actually carries. `None` for an ordinary, non-resumed
    evaluation, and for every row written before this parameter existed.

    `principal`: who is asking, as authenticated by the caller of this function --
    never read from `request`, which the asker writes. Recorded on any approval this
    decision creates, so that principal can never approve it. `None` when the caller
    authenticates nobody.

    `consumes_approval`: the approval a resumption resumes. It is consumed first,
    inside this decision's own transaction, so the decision uses it up whatever the
    verdict; an approval that is no longer `approved` raises `ApprovalError` before
    anything is evaluated. The approval is then linked to this decision's audit row --
    as is an approval a presented `request.approval_ref` resumes.

    `thread_id`/`tool_call_id`: a caller's resume key (e.g. LangGraph's own
    `configurable.thread_id` and the tool call being answered), when it has one. A
    Tier-3 propose with both set is checked against `onedoor.guardrail.approvals`'s
    resume-key index before creating a new approval -- see `_decide_and_reserve`.
    `None`/`None` (every caller before this parameter existed, and every caller with
    no such concept) behaves exactly as before: an ordinary, unconditional create.
    """
    consumed: list[int] = []
    outcome = _decide_and_reserve(
        request,
        conn=conn,
        config=config,
        now=now,
        policy_store=policy_store,
        approved_override=approved_override,
        resumes_audit_id=resumes_audit_id,
        principal=principal,
        consumes_approval=consumes_approval,
        consumed=consumed,
        thread_id=thread_id,
        tool_call_id=tool_call_id,
    )
    audit_id = outcome.intent_audit_id if isinstance(outcome, PermittedIntent) else outcome.audit_id
    for approval_id in consumed:
        approvals.record_result(conn, approval_id, audit_id)
    if (
        isinstance(outcome, ActionResult)
        and outcome.decision.approvers is None
        and approved_override
    ):
        # A bare override `_decide_and_reserve` resolves to a TERMINAL
        # outcome directly (denied, proposed, awaiting a mandate -- anything
        # that never becomes a `PermittedIntent` for `report_result` to
        # report on later): the decision it built and already wrote to its
        # own audit row carries no approvers, matching the executed-path
        # row's own normal shape for a bare override. Mark only the
        # in-memory copy a caller is handed back --
        # never the row, already written -- the same way `report_result`
        # marks its own returned decision for the executed path. Without
        # this, a bare override that is denied before anything executes is
        # indistinguishable here from a decision that never resumed
        # anything.
        outcome = outcome.model_copy(
            update={"decision": outcome.decision.model_copy(update={"approvers": []})}
        )
    return outcome


def _decide_and_reserve(
    request: ActionRequest,
    *,
    conn: Connection,
    config: EngineConfigLike,
    now: datetime,
    policy_store: PolicyStore | None,
    approved_override: bool,
    resumes_audit_id: int | None,
    principal: str | None,
    consumes_approval: int | None,
    consumed: list[int],
    thread_id: str | None = None,
    tool_call_id: str | None = None,
) -> ActionResult | PermittedIntent:
    """The body of :func:`decide_and_reserve`, which documents every parameter.

    `consumed` collects the approvals this decision uses up, for the caller to link."""

    def _decision(**kwargs: object) -> PolicyDecision:
        """The one place every `PolicyDecision` this function returns is built --
        so `approvers`/`escalated_to`/`escalated_at`
        are read once, from whichever approval row this call resumes (if any),
        and applied to every decision this function returns, rather than
        edited into each construction site individually. `setdefault` rather
        than an unconditional set: no call site here ever passes these three
        itself, but a future one that did would not be silently overridden.
        """
        kwargs.setdefault("approvers", resumed_approvers)
        kwargs.setdefault("escalated_to", resumed_escalated_to)
        kwargs.setdefault("escalated_at", resumed_escalated_at)
        return PolicyDecision(**kwargs)  # type: ignore[arg-type]

    store = policy_store or PolicyStore()
    undo_of = request.parent_audit_id if request.source == Source.UNDO else None

    # --- Idempotency / replay guard (no transaction) ---
    prior = audit.result_for_request_id(
        conn,
        request.request_id,
        issuer=getattr(config, "issuer", None),
        approved_override=approved_override,
    )
    if prior is not None:
        return prior

    # Reclaim any reservation abandoned past its deadline before evaluating, so
    # budget a never-reported permit is still holding is freed for this request.
    reclaim_expired_reservations(conn, config, now)

    with tx(conn):
        # AADP -03 §10: the ordered list of checks actually evaluated
        # for this verdict. Built inline with the pipeline, never after the fact --
        # an entry for a check the pipeline never reached would be exactly the "never
        # appear, least of all as pass" defect the MUST exists to prevent.
        trace = Trace()

        # 1. KILL-SWITCH FIRST (invariant: before policy lookup).
        kill = killswitch.is_engaged(conn)

        # 1b. APPROVAL REF (ND-009). Resolved inside this transaction because
        #     consumption is a CAS and `BEGIN IMMEDIATE` is what makes it race-free.
        #     A ref that does not authorise is NOT an error and NOT a denial: it
        #     evaluates as absent, and the action re-evaluates on its own merits, so a
        #     Tier-3 action simply proposes again. A bad ref never grants.
        #
        #     The kill switch is read FIRST and clamps below regardless: a valid ref
        #     resumes an approval, it does not overrule a stop (§invariants #1).
        resolution = approval_ref.resolve(
            conn,
            approval_ref=request.approval_ref,
            presented=request,
            now=now,
            principal=principal,
            escalation_resolver=getattr(config, "escalation_resolver", None),
        )
        ref_status = resolution.status.value
        if resolution.authorised:
            approved_override = True
            # A presented approval resumes a proposal exactly as a PDP-driven
            # resumption does, so the evidence names the proposal it resumes.
            assert request.approval_ref is not None
            if resumes_audit_id is None:
                resumes_audit_id = approvals.proposed_audit_id(conn, request.approval_ref)
            consumed.append(request.approval_ref)

        # 1c. CONSUME the approval a resumption resumes, first and in this same
        #     transaction: whatever the verdict below, this decision has used it up.
        if consumes_approval is not None:
            approvals.consume(conn, consumes_approval)
            consumed.append(consumes_approval)

        # 1d. TWO-PERSON RECEIPT. Read once, from whichever
        #     approval row this call resumes -- by a presented ref (`resolution.
        #     authorised`) or by `consumes_approval` (an admin resume) -- never
        #     both, since the resumed request `resume_approval`/`resume_ratification`
        #     build carries no `approval_ref` of its own. `_decision()` applies these
        #     to every decision this call returns. `None` stays `None` when this call
        #     does not resume an approval at all; a row that IS resumed gets a real
        #     value, even `[]` for a mandate-only resumption that no approver acted
        #     on (`cas_resume_ratified` never writes `approvers_json`, so it reads
        #     back as the column's own `'[]'` default) -- the same "never None on a
        #     decision that did, even with only one approver" rule the model's own
        #     `approvers` docstring states.
        resumed_approval_id = request.approval_ref if resolution.authorised else consumes_approval
        resumed_approvers: list[str] | None = None
        resumed_escalated_to: str | None = None
        resumed_escalated_at: datetime | None = None
        if resumed_approval_id is not None:
            approval_row = conn.execute(
                "SELECT approvers_json, backup_approver, escalated_at FROM approvals WHERE id=?",
                (resumed_approval_id,),
            ).fetchone()
            if approval_row is not None:
                resumed_approvers = json.loads(approval_row["approvers_json"] or "[]")
                resumed_escalated_to = approval_row["backup_approver"]
                resumed_escalated_at = (
                    from_iso(approval_row["escalated_at"]) if approval_row["escalated_at"] else None
                )

        # 2. POLICY LOOKUP / DEFAULT-DENY.
        policy = store.get(conn, request.action_type)
        nominal_tier = policy.tier

        # 2b. EFFECT RESOLUTION — declared labels plus deterministic parameter
        #     rules (a generic tool's effect can depend on its arguments).
        effects: list[str] = list(policy.effects)
        # Which declared opaque class, if any, made a rule fire (U4). Recorded in
        # evidence rather than in the reason code, because "we could not tell where
        # this goes" is a fact about the target, not a new kind of verdict.
        opaque_class: str | None = None
        for rule in policy.param_effects:
            value = request.params.get(rule.param)
            if value is None:
                continue
            if rule.url is None:
                # The original semantics, untouched. A rule without a `url` block
                # matches exactly what it matched before ND-040 -- opt-in, never a
                # silent reinterpretation of a deployed policy.
                matched = re.fullmatch(rule.pattern or "", str(value)) is not None
            else:
                # Outside the try on purpose: an `extra` entry that will not
                # canonicalize is a POLICY error, and policy_loader rejects it when
                # the policy is written. If one ever reached here it must surface as
                # the bug it is, not be reported as a malformed request -- blaming
                # the caller for the deployer's typo would send an operator hunting
                # in exactly the wrong place.
                extra_members = (
                    opaque_hosts.declared_members(rule.url.opaque.extra)
                    if rule.url.opaque is not None
                    else frozenset()
                )
                try:
                    matched, canon = url_rule_matches(rule.url, value)
                    if not matched and rule.url.opaque is not None and not canon.is_ip:
                        # U4. The host canonicalizes perfectly and is simply not the
                        # declared one -- but if the policy has declared it a host
                        # whose target cannot be known without a network call, then
                        # the engine cannot rule out that it IS the declared target.
                        # Treat it as though it were: the rule's effects apply, and
                        # the effect's floor and caps decide. Strictly conservative,
                        # since an effect can only raise a floor or add a cap.
                        klass = opaque_hosts.classify(
                            canon.host,
                            builtin=rule.url.opaque.builtin,
                            extra=extra_members,
                        )
                        if klass is not None:
                            matched = True
                            opaque_class = klass
                except CanonicalizationError as exc:
                    # A target this cannot interpret at least as strictly as the
                    # networking stack will is refused, so a parse differential is a
                    # denial and never a bypass (scopegate). Reason code is the
                    # EXISTING `malformed` -- no new wire vocabulary -- with
                    # the failure recorded distinctly in evidence so an operator can
                    # tell a probe of the effect matcher from a broken client.
                    decision = _decision(
                        decision=Decision.DENIED,
                        effective_tier=Tier.CONFIRM,
                        nominal_tier=nominal_tier,
                        reason_code=CheckId.MALFORMED,
                        detail=f"param {rule.param!r} is not an interpretable URL: {exc}",
                    )
                    aid = audit.append(
                        conn,
                        request,
                        decision,
                        kind="decision",
                        now=now,
                        approval_ref_status=ref_status,
                        undo_of=undo_of,
                        malformed_kind="url_canonicalization",
                        canon_schema=CANON_SCHEMA,
                        # No check in the ordered pipeline ran yet -- this fails
                        # during effect resolution, before tier/bounds/caps -- so an
                        # honestly empty trace is correct here, not an omission.
                        evaluation_trace_json=trace.to_json(),
                        resumes_audit_id=resumes_audit_id,
                    )
                    bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                    return ActionResult(
                        request_id=request.request_id,
                        decision=decision,
                        audit_id=aid,
                        decision_ref=_decision_ref(
                            conn,
                            audit_id=aid,
                            request_id=request.request_id,
                            decision=decision.decision,
                            config=config,
                        ),
                    )
            if matched:
                effects.extend(e for e in rule.add_effects if e not in effects)
        effect_policies = [ep for e in effects if (ep := store.get_effect(conn, e)) is not None]

        # 3/4. Resolve effective tier (+ Tier-1 integrity, kill-switch clamp).
        reason_confirm = CheckId.TIER_CONFIRM
        confirm_detail = ""
        untrusted_matched_hold: list[str] = []
        sequence_rule_matched_hold: str | None = None
        sequence_events_considered = 0
        sequence_history_incomplete = False
        # The kill switch is exempt for OBSERVE (reads are exempt from it entirely,
        # by the same rule §5 below states), so recording a fail/pass for it there
        # would assert a check ran against a request the switch never gates.
        if not (not approved_override and policy.tier == Tier.OBSERVE):
            trace.add(
                "kill_switch",
                "an engaged kill switch requires human approval for anything but an exempt read",
                "engaged == false",
                kill,
                "fail" if kill else "pass",
            )
        # 3a. DEFAULT-DENY: an action type no policy declares is refused. Absence of
        #     policy is a denial, never a permission and never a question for a human,
        #     so it creates no approval, and an approval cannot resume it either. The
        #     rule text is the one the pass entry below has always carried.
        if policy.is_default_deny:
            trace.add(
                "default_deny",
                "an action type must be declared to a policy to auto-execute or be proposed",
                "policy.is_default_deny == false",
                request.action_type,
                "fail",
            )
            decision = _decision(
                decision=Decision.DENIED,
                effective_tier=Tier.CONFIRM,
                nominal_tier=nominal_tier,
                reason_code=CheckId.DEFAULT_DENY,
                detail=(
                    f"action type {request.action_type!r} is declared by no policy, so it "
                    f"is refused; declare it in the policy set (at tier 3 to require a "
                    f"human's approval) to allow it"
                ),
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )
        if approved_override:
            # Default-deny was evaluated above for this resumption too, and passed.
            trace.add(
                "default_deny",
                "an action type must be declared to a policy to auto-execute or be proposed",
                "policy.is_default_deny == false",
                request.action_type,
                "pass",
            )
            if kill:
                decision = _decision(
                    decision=Decision.DENIED,
                    effective_tier=Tier.CONFIRM,
                    nominal_tier=nominal_tier,
                    reason_code=CheckId.KILL_SWITCH,
                    detail="kill switch engaged; approved action blocked",
                )
                aid = audit.append(
                    conn,
                    request,
                    decision,
                    kind="decision",
                    now=now,
                    approval_ref_status=ref_status,
                    undo_of=undo_of,
                    opaque_class=opaque_class,
                    evaluation_trace_json=trace.to_json(),
                    resumes_audit_id=resumes_audit_id,
                )
                bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                return ActionResult(
                    request_id=request.request_id,
                    decision=decision,
                    audit_id=aid,
                    decision_ref=_decision_ref(
                        conn,
                        audit_id=aid,
                        request_id=request.request_id,
                        decision=decision.decision,
                        config=config,
                    ),
                )
            effective_tier = Tier.AUTO
        elif policy.tier == Tier.OBSERVE:
            effective_tier = Tier.OBSERVE  # reads are exempt from the kill switch
        elif kill:
            effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.KILL_SWITCH
        else:
            effective_tier = policy.tier
            trace.add(
                "default_deny",
                "an action type must be declared to a policy to auto-execute or be proposed",
                "policy.is_default_deny == false",
                request.action_type,
                "fail" if policy.is_default_deny else "pass",
            )
            # Effect tier floors: an action inherits the strictest floor of its
            # effects — aliasing-resistant escalation ("moves money" is Tier 3
            # no matter which tool name moved it).
            effect_floor_fired = False
            for ep in effect_policies:
                if ep.min_tier is not None and int(ep.min_tier) > int(effective_tier):
                    effective_tier = ep.min_tier
                    effect_floor_fired = True
                    if effective_tier == Tier.CONFIRM:
                        reason_confirm = CheckId.EFFECT_FLOOR
            trace.add(
                "effect_floor",
                "an action inherits the strictest tier floor of its resolved effects",
                "no resolved effect's min_tier exceeds the nominal tier",
                ",".join(effects) if effects else "none",
                "fail" if effect_floor_fired else "pass",
            )

        # OPAQUE-HOST INVARIANT. Stated as an invariant, never left to
        # emerge from tier arithmetic: **a host in a declared opaque class can never
        # resolve to auto-execution.** A human decides, or policy denies.
        #
        # This is not the same as the effect floor above, and relying on that floor
        # was a real hole -- found by probing this exact condition rather than by
        # reading the code. A policy could declare `opaque` and point at an effect
        # with `min_tier: null`, and a declared redirector would then auto-execute
        # silently: the deployer asked for the protection, the engine took the
        # declaration, and nothing escalated. The whole mechanism was one YAML line
        # away from being decorative.
        #
        # The founding rule is that an action whose
        # consequences cannot be VERIFIED must not be auto-executed -- not that it can
        # never happen. A redirector's true destination is unknowable without the
        # network call determinism forbids, and the honest answer to *unknowable* is
        # "a human decides", not "nobody decides". So the floor is the human-approval
        # tier, and a policy that offers no approver ends in denial rather than in
        # execution.
        opaque_fired = (
            opaque_class is not None and not approved_override and effective_tier != Tier.OBSERVE
        )
        if opaque_fired:
            # OBSERVE is exempt because it never executes at all: a read returns an
            # audited no-op, never a permit. The invariant is about execution.
            if int(effective_tier) < int(Tier.CONFIRM):
                effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.EFFECT_FLOOR
            # The class is in `opaque_class`; the REASON rides here, so an operator
            # reading the row can tell this escalation from an ordinary tier floor
            # without knowing what the class means.
            confirm_detail = (
                f"destination unverifiable without a network call; host is in the "
                f"declared opaque class {opaque_class}"
            )
        # An approval is the human this escalation asks for, so a resumption does not
        # evaluate it -- and a check that was not evaluated is not in the trace.
        if not approved_override:
            trace.add(
                "opaque_host",
                "a declared opaque host class can never resolve to auto-execution; a human decides",
                "opaque_class is None, already overridden, or the request is exempt",
                opaque_class,
                "fail" if opaque_fired else "pass",
            )

        # Reversibility precondition: ANY tier that may execute without a human
        # (auto and auto_capped alike) requires a registered means of reversal.
        # Scoping this to Tier.AUTO alone let an irreversible action auto-execute
        # merely because it also carried a budget.
        no_compensation_fired = (
            effective_tier in (Tier.AUTO, Tier.AUTO_CAPPED)
            and not approved_override
            and not policy.compensating_command
        )
        if no_compensation_fired:
            effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.NO_COMPENSATION
        # Likewise not evaluated on resumption: the approval is the human it asks for.
        if not approved_override:
            trace.add(
                "reversibility",
                "an auto-executing tier requires a registered compensating command",
                "effective_tier not in (auto, auto_capped) or a compensating_command is set",
                policy.compensating_command,
                "fail" if no_compensation_fired else "pass",
            )

        # 4b. EXTERNAL AUTHORIZATION -- mandate-layer deferral (AADP -03 §8.1).
        #     Consulted only for a policy that declares it, and only when
        #     a deployment has actually configured a resolver -- an unconfigured
        #     mandate check is a check that was never evaluated, and must not appear
        #     in the trace at all, let alone as pass.
        #
        #     A DENY is unconditional and immediate (checked here, after the tier
        #     arithmetic above so its trace entry is provably the LAST fail when it
        #     fires, matching every escalation's reason_confirm precedence). A
        #     PENDING never returns early: it only escalates the tier, exactly like
        #     opaque_host/reversibility above, so a LATER denial (bounds, caps) still
        #     takes precedence over merely proposing -- "unless another check
        #     already denies the action" is this ordering, not special-cased logic.
        #
        #     Never re-consulted when `approved_override` is set: that flag IS the
        #     proof this exact resumption was already authorised (by a mandate
        #     ratification or an onedoor admin), and re-asking the same external
        #     resolver on resumption would re-litigate a settled deferral rather than
        #     re-evaluate onedoor's OWN checks -- which is what "resumption
        #     re-evaluates fully" (-03 §8.1) means: bounds, caps, kill switch, not a
        #     second round of mandate consultation.
        mandate_core_digest_value: str | None = None
        mandate_combined = False
        mandate_resolver = getattr(config, "mandate_resolver", None)
        if (
            policy.requires_external_authorization
            and mandate_resolver is not None
            and not approved_override
        ):
            mandate_verdict = mandate_resolver(request)
            trace.add(
                "external_authorization",
                "a mandate-layer authority's verdict is consulted before any other check runs",
                "mandate_verdict == permit",
                mandate_verdict.value,
                "pass" if mandate_verdict is mandate.MandateVerdict.PERMIT else "fail",
            )
            if mandate_verdict is mandate.MandateVerdict.DENY:
                decision = _decision(
                    decision=Decision.DENIED,
                    effective_tier=effective_tier,
                    nominal_tier=nominal_tier,
                    reason_code=CheckId.EXTERNAL_AUTHORIZATION,
                    detail="denied by the mandate-layer authority",
                )
                aid = audit.append(
                    conn,
                    request,
                    decision,
                    kind="decision",
                    now=now,
                    approval_ref_status=ref_status,
                    undo_of=undo_of,
                    opaque_class=opaque_class,
                    evaluation_trace_json=trace.to_json(),
                    resumes_audit_id=resumes_audit_id,
                )
                bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                return ActionResult(
                    request_id=request.request_id,
                    decision=decision,
                    audit_id=aid,
                    decision_ref=_decision_ref(
                        conn,
                        audit_id=aid,
                        request_id=request.request_id,
                        decision=decision.decision,
                        config=config,
                    ),
                )
            if mandate_verdict is mandate.MandateVerdict.PENDING:
                # Combined: onedoor's own checks already send this action to a human.
                # One proposal, with onedoor's own reason, and one approval that needs
                # both the mandate authority's ratification and an approver.
                mandate_combined = int(effective_tier) >= int(Tier.CONFIRM)
                if mandate_combined:
                    confirm_detail = (
                        f"{confirm_detail}; " if confirm_detail else ""
                    ) + "also pending the mandate-layer authority's ratification"
                else:
                    effective_tier = Tier.CONFIRM
                    reason_confirm = CheckId.EXTERNAL_AUTHORIZATION
                    confirm_detail = "pending the mandate-layer authority's ratification"
                mandate_core_digest_value = mandate.core_digest(
                    request.request_id, request.action_type, request.params
                )

        # 5c. UNTRUSTED-INPUT — checked before bounds and caps, and before step 5
        #     (observe) exits: a refusal here is about where a value came from, not
        #     what it is, or what tier the action nominally runs at, and a
        #     denied-for-provenance call should never execute, not even a tier-0
        #     read -- step 5's own early return used to run before this and 5d,
        #     so a tier-0 read with a marked, denied path executed unchecked. A
        #     path named in `deny` wins over the same path named in `hold`; a
        #     path named in neither has no effect, whether or not the caller
        #     marked it.
        untrusted_denied_matched: list[str] = []
        if policy.untrusted_params is not None:
            untrusted_denied_matched = [
                p for p in request.untrusted if p in policy.untrusted_params.deny
            ]
            untrusted_held_matched = [
                p for p in request.untrusted if p in policy.untrusted_params.hold
            ]
        else:
            untrusted_held_matched = []
        trace.add(
            "untrusted_input",
            "a caller-marked path matching this policy's own deny/hold list is "
            "stopped before bounds and caps are ever consulted",
            "no caller-marked path matches this policy's own untrusted_params",
            ",".join(request.untrusted) if request.untrusted else "none marked",
            "fail" if (untrusted_denied_matched or untrusted_held_matched) else "pass",
        )
        if untrusted_denied_matched:
            decision = _decision(
                decision=Decision.DENIED,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=CheckId.UNTRUSTED_INPUT,
                detail=(
                    f"caller-marked path(s) {', '.join(untrusted_denied_matched)} "
                    "match this policy's own untrusted_params.deny"
                ),
                untrusted_matched=untrusted_denied_matched,
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )
        if untrusted_held_matched and int(effective_tier) < int(Tier.CONFIRM):
            effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.UNTRUSTED_INPUT
            untrusted_matched_hold = untrusted_held_matched
            confirm_detail = (
                f"caller-marked path(s) {', '.join(untrusted_held_matched)} match "
                "this policy's own untrusted_params.hold"
            )
        elif untrusted_held_matched:
            # Already at or past CONFIRM for another reason (kill switch, effect
            # floor, ...) -- still worth recording on the receipt even though it
            # did not itself need to escalate anything.
            untrusted_matched_hold = untrusted_held_matched

        # 5d. SEQUENCE_RULE — checked before bounds and caps, the same placement
        #     as untrusted-input: a stop here is about what already happened in
        #     this session, not this action's own value.
        seq_result = sequence.evaluate(conn, request, policy, now=now)
        sequence_events_considered = seq_result.events_considered
        sequence_history_incomplete = seq_result.history_incomplete
        trace.add(
            "sequence_rule",
            "a policy's own sequence.rules must not match this session's prior settled history",
            "no rule matches, or the policy declares none",
            "no session_id presented"
            if seq_result.no_session
            else (seq_result.matched_rule or "no match"),
            "fail" if (seq_result.matched_effect or seq_result.no_session) else "pass",
        )
        if seq_result.no_session:
            # Reason set unconditionally (not only when it has to RAISE the
            # tier): a policy whose own nominal tier is already 3 must still
            # report this as the reason, not fall silent behind
            # `tier_confirm`, the same way `opaque_host`'s own escalation
            # already does above.
            if int(effective_tier) < int(Tier.CONFIRM):
                effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.SEQUENCE_NO_SESSION
            confirm_detail = (
                "policy.sequence.rules is non-empty and no session_id was presented; "
                "declare sequence.session_optional: true to allow this"
            )
        elif seq_result.matched_effect == "deny":
            decision = _decision(
                decision=Decision.DENIED,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=CheckId.SEQUENCE_RULE,
                detail=(
                    f"sequence rule {seq_result.matched_rule} matched this "
                    "session's prior settled history"
                ),
                sequence_events_considered=sequence_events_considered,
                sequence_rule_matched=seq_result.matched_rule,
                sequence_history_incomplete=sequence_history_incomplete,
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )
        if seq_result.matched_effect == "hold" and int(effective_tier) < int(Tier.CONFIRM):
            effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.SEQUENCE_RULE
            sequence_rule_matched_hold = seq_result.matched_rule
            confirm_detail = (
                f"sequence rule {seq_result.matched_rule} matched this session's "
                "prior settled history"
            )
        elif seq_result.matched_effect == "hold":
            sequence_rule_matched_hold = seq_result.matched_rule

        # 5. OBSERVE — audit a no-op read and return. Reached only when 5c/5d
        #    above did not themselves deny the call or raise effective_tier past
        #    OBSERVE (a hold from either still applies to a tier-0 read) -- a
        #    nominal tier-0 action that passes both still records its own
        #    `sequence.tag_as` here, since it has no later settlement step (no
        #    `PermittedIntent`, no `report_result` call) the
        #    way a tier-1+ permit's own tagging rides on.
        if effective_tier == Tier.OBSERVE:
            decision = _decision(
                decision=Decision.EXECUTED,
                effective_tier=Tier.OBSERVE,
                nominal_tier=nominal_tier,
                reason_code=CheckId.OBSERVE,
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(conn, "action.observed", {"request_id": str(request.request_id)})
            if policy.sequence is not None and request.session_id is not None:
                sequence.record_event(
                    conn,
                    session_id=request.session_id,
                    action_type=request.action_type,
                    tag=policy.sequence.tag_as,
                    at=now,
                    audit_id=aid,
                    max_events_per_session=config.sequence_max_events_per_session,
                )
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )

        # 6. BOUNDS — validated for every tier that could execute OR be proposed,
        #    so a human never approves an out-of-bounds action.
        bounds_result = bounds.validate(policy.bounds, request.params)
        trace.add(
            "bounds",
            "declared parameter bounds (numeric ranges, enum membership, required "
            "keys) must be satisfied",
            "bounds.validate(policy.bounds, request.params).ok",
            bounds_result.detail or "within bounds",
            "pass" if bounds_result.ok else "fail",
        )
        if not bounds_result.ok:
            decision = _decision(
                decision=Decision.DENIED,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=CheckId.BOUNDS,
                detail=bounds_result.detail,
                # A hold from 5c/5d is kept in the receipt even though a later,
                # different check is the one that actually denies -- the record
                # of what already matched should not disappear just because
                # something else denied the call first.
                untrusted_matched=(
                    untrusted_matched_hold if policy.untrusted_params is not None else None
                ),
                sequence_events_considered=(
                    sequence_events_considered if policy.sequence is not None else None
                ),
                sequence_rule_matched=sequence_rule_matched_hold,
                sequence_history_incomplete=(
                    sequence_history_incomplete if policy.sequence is not None else None
                ),
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )

        # 6b. PRESENT_BOUND (AADP -03 §6): the permit may be exercised only by
        #     presenting it to the declared audience. Consulted only for a policy
        #     that declares one -- an unset bound is a check that never runs, and must
        #     not appear in the trace at all. Checked before Tier 3 propose/confirm
        #     for the same reason bounds is: a human must never approve, and the
        #     engine must never propose, an action whose audience is already wrong.
        if policy.present_bound is not None:
            audience_matches = request.presented_audience == policy.present_bound
            trace.add(
                "present_bound",
                "the permit may be exercised only by presenting it to the declared audience",
                "request.presented_audience == policy.present_bound",
                request.presented_audience,
                "pass" if audience_matches else "fail",
            )
            if not audience_matches:
                decision = _decision(
                    decision=Decision.DENIED,
                    effective_tier=effective_tier,
                    nominal_tier=nominal_tier,
                    reason_code=CheckId.PRESENT_BOUND,
                    detail=(
                        f"presented_audience {request.presented_audience!r} does not "
                        f"match the declared audience {policy.present_bound!r}"
                    ),
                    untrusted_matched=(
                        untrusted_matched_hold if policy.untrusted_params is not None else None
                    ),
                    sequence_events_considered=(
                        sequence_events_considered if policy.sequence is not None else None
                    ),
                    sequence_rule_matched=sequence_rule_matched_hold,
                    sequence_history_incomplete=(
                        sequence_history_incomplete if policy.sequence is not None else None
                    ),
                )
                aid = audit.append(
                    conn,
                    request,
                    decision,
                    kind="decision",
                    now=now,
                    approval_ref_status=ref_status,
                    undo_of=undo_of,
                    opaque_class=opaque_class,
                    evaluation_trace_json=trace.to_json(),
                    resumes_audit_id=resumes_audit_id,
                )
                bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                return ActionResult(
                    request_id=request.request_id,
                    decision=decision,
                    audit_id=aid,
                    decision_ref=_decision_ref(
                        conn,
                        audit_id=aid,
                        request_id=request.request_id,
                        decision=decision.decision,
                        config=config,
                    ),
                )

        # 6c. BOUND PERMIT ISSUANCE PRECONDITIONS (bound-permit profile §§3-4).
        #     Checked here, before any caps reservation, for the same reason 6b is:
        #     a policy that asks for a bound permit but cannot get one issued must
        #     not reserve budget for an action it is about to deny. Actually signing
        #     the permit happens later, once the intent row exists to name as `jti`
        #     -- these are exactly the two preconditions `bound_permit.issue` itself
        #     checks, verified early so a failure here can still deny before caps.
        if policy.bound_permit_action_type is not None:
            issuer_configured = (
                getattr(config, "permit_issuer", None) is not None
                and getattr(config, "permit_issuer_key_id", None) is not None
                and getattr(config, "permit_issuer_private_key", None) is not None
            )
            issuance_ok = (
                policy.present_bound is not None
                and issuer_configured
                and request.presenter_key_thumbprint is not None
            )
            trace.add(
                "bound_permit_issuance",
                "a policy requiring a bound permit must have one to issue -- "
                "present_bound configured, an issuer configured, and a presenter "
                "key thumbprint on the request",
                "present_bound set, issuer configured, and request.presenter_key_thumbprint is set",
                request.presenter_key_thumbprint,
                "pass" if issuance_ok else "fail",
            )
            if not issuance_ok:
                if policy.present_bound is None:
                    unmet = (
                        "bound_permit_action_type is set with no present_bound to issue it under"
                    )
                elif not issuer_configured:
                    unmet = "no issuer is configured for this deployment"
                else:
                    unmet = "the request carries no presenter key thumbprint"
                decision = _decision(
                    decision=Decision.DENIED,
                    effective_tier=effective_tier,
                    nominal_tier=nominal_tier,
                    reason_code=CheckId.PRESENT_BOUND,
                    detail=f"policy requires a bound permit (bound-permit profile §§3-4) but {unmet}",
                    untrusted_matched=(
                        untrusted_matched_hold if policy.untrusted_params is not None else None
                    ),
                    sequence_events_considered=(
                        sequence_events_considered if policy.sequence is not None else None
                    ),
                    sequence_rule_matched=sequence_rule_matched_hold,
                    sequence_history_incomplete=(
                        sequence_history_incomplete if policy.sequence is not None else None
                    ),
                )
                aid = audit.append(
                    conn,
                    request,
                    decision,
                    kind="decision",
                    now=now,
                    approval_ref_status=ref_status,
                    undo_of=undo_of,
                    opaque_class=opaque_class,
                    evaluation_trace_json=trace.to_json(),
                    resumes_audit_id=resumes_audit_id,
                )
                bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                return ActionResult(
                    request_id=request.request_id,
                    decision=decision,
                    audit_id=aid,
                    decision_ref=_decision_ref(
                        conn,
                        audit_id=aid,
                        request_id=request.request_id,
                        decision=decision.decision,
                        config=config,
                    ),
                )

        # 7. TIER 3 — propose and confirm, UNLESS the kill switch is why we are
        #    here. Proposing during an incident still fills the approval
        #    queue; the switch must deny, not ask a human to look at it later.
        #    `reason_confirm` can only still read `KILL_SWITCH` at this point if
        #    nothing stronger (bounds, a mandate DENY, a malformed request) already
        #    returned above, and nothing weaker (effect_floor, opaque_host,
        #    no_compensation, a mandate PENDING) could have overwritten it either --
        #    every one of those guards only escalates when the tier is currently
        #    *below* CONFIRM, and CONFIRM is the ceiling, so once the switch sets it
        #    it is the reason all the way to here. The tier-0 read exemption above
        #    is unaffected: an OBSERVE action never reaches this branch engaged.
        if effective_tier == Tier.CONFIRM and reason_confirm is CheckId.KILL_SWITCH:
            decision = _decision(
                decision=Decision.DENIED,
                effective_tier=Tier.CONFIRM,
                nominal_tier=nominal_tier,
                reason_code=CheckId.KILL_SWITCH,
                detail="kill switch engaged; not proposed",
                untrusted_matched=(
                    untrusted_matched_hold if policy.untrusted_params is not None else None
                ),
                sequence_events_considered=(
                    sequence_events_considered if policy.sequence is not None else None
                ),
                sequence_rule_matched=sequence_rule_matched_hold,
                sequence_history_incomplete=(
                    sequence_history_incomplete if policy.sequence is not None else None
                ),
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )
        # 7a. PLAN_REF (onedoor 0.11) — resolved only at the one
        #     point a plan can ever matter: the ordinary Tier-3 propose this
        #     action's own nominal tier would otherwise require, with nothing
        #     else (a hold, the kill switch, a mandate deferral) having already
        #     raised the tier for its own reason -- those are occasions for a
        #     human beyond what any plan was ever scoped to answer. A match
        #     satisfies exactly this one approval step; every other check above
        #     and below still decided (or still will) fully on its own merits.
        #     `reason_confirm is TIER_CONFIRM` alone is not a strong enough
        #     guard for a policy whose own NOMINAL tier is already 3: an
        #     untrusted-input or sequence hold only overwrites `reason_confirm`
        #     when it has to RAISE the tier to reach CONFIRM, which a nominal
        #     Tier-3 policy is already at -- so a hold match or a no-session
        #     stop on a Tier-3 policy would otherwise leave `reason_confirm`
        #     unchanged at `TIER_CONFIRM` even though it fired. Checked
        #     explicitly here rather than trusted to the tier arithmetic alone.
        plan_match: plan_ref_mod.PlanMatch | None = None
        if (
            effective_tier == Tier.CONFIRM
            and reason_confirm is CheckId.TIER_CONFIRM
            and not untrusted_matched_hold
            and sequence_rule_matched_hold is None
            and not seq_result.no_session
            and request.plan_ref is not None
        ):
            plan_match = plan_ref_mod.resolve_match(
                conn, plan_ref=request.plan_ref, request=request, now=now, policy_store=store
            )
            if plan_match is not None:
                effective_tier = Tier.AUTO

        if effective_tier == Tier.CONFIRM:
            # A resume (matched by thread_id/tool_call_id) is CHECKED against the
            # approval row it would reuse, never trusted to match just because the
            # keys do. Absent either key, this is skipped entirely and behaves
            # exactly as it always has.
            reused_approval_id: int | None = None
            if thread_id is not None and tool_call_id is not None:
                existing = approvals.find_by_resume_key(conn, thread_id, tool_call_id, now)
                if existing is not None:
                    expected_digest = existing["request_digest"]
                    actual_digest = approvals.resume_digest(request.action_type, request.params)
                    if expected_digest == actual_digest:
                        reused_approval_id = int(existing["id"])
                    else:
                        decision = _decision(
                            decision=Decision.DENIED,
                            effective_tier=Tier.CONFIRM,
                            nominal_tier=nominal_tier,
                            reason_code=CheckId.RESUME_REQUEST_MISMATCH,
                            detail=(
                                "resumed request does not match the approval this "
                                "resume key would have reused"
                            ),
                        )
                        aid = audit.append(
                            conn,
                            request,
                            decision,
                            kind="decision",
                            now=now,
                            approval_ref_status=ref_status,
                            undo_of=undo_of,
                            opaque_class=opaque_class,
                            evaluation_trace_json=trace.to_json(),
                            resumes_audit_id=resumes_audit_id,
                            resume_digest_expected=expected_digest,
                            resume_digest_actual=actual_digest,
                        )
                        bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                        return ActionResult(
                            request_id=request.request_id,
                            decision=decision,
                            audit_id=aid,
                            decision_ref=_decision_ref(
                                conn,
                                audit_id=aid,
                                request_id=request.request_id,
                                decision=decision.decision,
                                config=config,
                            ),
                        )
            approval_id = reused_approval_id or approvals.create(
                conn,
                request,
                config.approval_ttl_seconds,
                now,
                mandate_core_digest=mandate_core_digest_value,
                mandate_combined=mandate_combined,
                proposed_by=principal,
                thread_id=thread_id,
                tool_call_id=tool_call_id,
                policy_store=store,
            )
            decision = _decision(
                decision=Decision.PROPOSED,
                effective_tier=Tier.CONFIRM,
                nominal_tier=nominal_tier,
                reason_code=reason_confirm,
                requires_approval=True,
                compensating_command=policy.compensating_command,
                detail=confirm_detail,
                untrusted_matched=(
                    untrusted_matched_hold if policy.untrusted_params is not None else None
                ),
                sequence_events_considered=(
                    sequence_events_considered if policy.sequence is not None else None
                ),
                sequence_rule_matched=sequence_rule_matched_hold,
                sequence_history_incomplete=(
                    sequence_history_incomplete if policy.sequence is not None else None
                ),
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                approval_id=approval_id,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(
                conn,
                "action.proposed",
                {"request_id": str(request.request_id), "approval_id": approval_id},
            )
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                approval_id=approval_id,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )

        # --- Auto path (Tier 1, Tier 2, or approved override) ---

        # 8. DRY-RUN — before caps (a rehearsal must not spend a real budget). An
        #    approval does not turn a rehearsal into an execution.
        is_dry = policy.dry_run or (policy.dry_run_until is not None and now < policy.dry_run_until)
        trace.add(
            "dry_run",
            "a policy in dry-run rehearses rather than executes",
            "not dry_run and (dry_run_until is None or now >= dry_run_until)",
            "dry_run" if is_dry else "live",
            "fail" if is_dry else "pass",
        )
        if is_dry:
            decision = _decision(
                decision=Decision.DRY_RUN,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=CheckId.DRY_RUN,
                dry_run=True,
                detail="would have executed",
                # A dry run never spends a plan's own ceilings -- it reports what
                # resolve_match already found room for, without ever calling
                # apply_match, the same "rehearsal must not spend a real budget"
                # reasoning this step already applies to caps.
                plan_ref=plan_match.plan_id if plan_match is not None else None,
                plan_consumed_count_after=(
                    plan_match.consumed_count_after if plan_match is not None else None
                ),
                plan_consumed_amount_after=(
                    plan_match.consumed_amount_after if plan_match is not None else None
                ),
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(conn, "action.dry_run", {"request_id": str(request.request_id)})
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )

        # 9. CAPS — action caps AND effect-shared caps, all-or-nothing.
        cap_result = caps.check_and_reserve(
            conn,
            policy,
            request,
            now,
            config.tz,
            effect_caps=[(ep.effect, ep.caps) for ep in effect_policies],
        )
        if cap_result.exceeded:
            assert cap_result.reason is not None
            trace.add(
                cap_result.reason.value,
                # A budget denial's rule IS the counter's own name -- `Budget.name`
                # and this trace entry's `rule` name the same counter on purpose,
                # so a reader can join a budget object to the check that produced
                # it without guessing. `cost_unknown` carries no budget (the cost
                # could not be resolved, so no specific counter was ever checked
                # against), so it keeps the general description instead.
                (
                    cap_result.budget.name
                    if cap_result.budget is not None
                    else "budget caps (rate and/or value) must not be exceeded by this action"
                ),
                (
                    "cost is resolvable"
                    if cap_result.reason == CheckId.COST_UNKNOWN
                    else "already-reserved + this action's cost <= the declared cap"
                ),
                cap_result.detail,
                "unresolved" if cap_result.reason == CheckId.COST_UNKNOWN else "fail",
            )
            decision = _decision(
                decision=Decision.DENIED,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=cap_result.reason,
                detail=cap_result.detail,
                # ND-003: present iff the verdict is deny and the reason is a cap.
                # `cost_unknown` also arrives here and carries no budget -- there is
                # no budget state to report when the amount could not be resolved.
                budget=cap_result.budget,
                untrusted_matched=(
                    untrusted_matched_hold if policy.untrusted_params is not None else None
                ),
                sequence_events_considered=(
                    sequence_events_considered if policy.sequence is not None else None
                ),
                sequence_rule_matched=sequence_rule_matched_hold,
                sequence_history_incomplete=(
                    sequence_history_incomplete if policy.sequence is not None else None
                ),
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_ref_status=ref_status,
                undo_of=undo_of,
                opaque_class=opaque_class,
                evaluation_trace_json=trace.to_json(),
                resumes_audit_id=resumes_audit_id,
            )
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(
                request_id=request.request_id,
                decision=decision,
                audit_id=aid,
                decision_ref=_decision_ref(
                    conn,
                    audit_id=aid,
                    request_id=request.request_id,
                    decision=decision.decision,
                    config=config,
                ),
            )
        trace.add(
            "caps",
            "budget caps (rate and/or value) must not be exceeded by this action",
            "already-reserved + this action's cost <= every declared cap",
            "within caps",
            "pass",
        )

        # A plan is spent only once the call is actually going to execute --
        # not a dry run (already returned above), not then denied by caps
        # (already returned above either). This is the first point reached
        # only by a call that passed everything a plan does not itself
        # decide; `apply_match` writes back exactly what `resolve_match`
        # already computed at 7a, inside this same transaction.
        if plan_match is not None:
            plan_ref_mod.apply_match(conn, plan_match)

        # 10. INTENT — record that we are about to execute. Set the undo window
        #     for reversible Tier-1 actions.
        undo_until = None
        if effective_tier == Tier.AUTO and not approved_override and policy.compensating_command:
            undo_until = now + timedelta(seconds=policy.undo_window_seconds)
        intent_decision = _decision(
            decision=Decision.EXECUTED,
            effective_tier=effective_tier,
            nominal_tier=nominal_tier,
            reason_code=CheckId.PLAN_REF if plan_match is not None else CheckId.PASSED,
            compensating_command=policy.compensating_command,
            # A decision records what a check found, including "nothing",
            # wherever the policy actually uses it -- `None` (not an empty/
            # zero/false value) is reserved for a policy that carries no
            # `untrusted_params`/`sequence` block at all, the one case
            # neither check ever ran. By this point in the pipeline both
            # untrusted_matched_hold and sequence_rule_matched_hold are
            # guaranteed empty/None -- a non-empty hold would already have
            # escalated to CONFIRM and returned through the propose branch
            # above, never reaching here.
            untrusted_matched=(
                untrusted_matched_hold if policy.untrusted_params is not None else None
            ),
            sequence_events_considered=(
                sequence_events_considered if policy.sequence is not None else None
            ),
            sequence_rule_matched=sequence_rule_matched_hold,
            sequence_history_incomplete=(
                sequence_history_incomplete if policy.sequence is not None else None
            ),
            plan_ref=plan_match.plan_id if plan_match is not None else None,
            plan_consumed_count_after=(
                plan_match.consumed_count_after if plan_match is not None else None
            ),
            plan_consumed_amount_after=(
                plan_match.consumed_amount_after if plan_match is not None else None
            ),
        )
        # Minted here, independently of the row it is about to be stamped on:
        # a bound permit's `jti` must not be guessable from, or reducible to,
        # the intent's own audit id. 128 random bits, URL-safe (bound-permit
        # profile -00 §3.2 treats `jti` as an opaque nonce).
        permit_jti = (
            secrets.token_urlsafe(16) if policy.bound_permit_action_type is not None else None
        )
        intent_id = audit.append(
            conn,
            request,
            intent_decision,
            kind="exec_intent",
            now=now,
            approval_ref_status=ref_status,
            undo_until=undo_until,
            undo_of=undo_of,
            opaque_class=opaque_class,
            evaluation_trace_json=trace.to_json(),
            resumes_audit_id=resumes_audit_id,
            decide_principal=principal,
            permit_jti=permit_jti,
        )

        # 10b. RESERVATION LEDGER — if this permit reserved budget, record the
        #      exact deltas and a deadline so the reservation can be reclaimed
        #      (AADP section 6) should the permit never be reported. No caps
        #      reserved (tier-1, unbudgeted) means nothing to reclaim.
        ttl = int(getattr(config, "reservation_ttl_seconds", 3600) or 0)
        if cap_result.deltas and ttl > 0:
            deadline = now + timedelta(seconds=ttl)
            conn.execute(
                "INSERT INTO cap_reservations "
                "(intent_audit_id, request_id, deadline_utc, deltas_json, status, created_utc) "
                "VALUES (?, ?, ?, ?, 'held', ?)",
                (
                    intent_id,
                    str(request.request_id),
                    to_iso(deadline),
                    json.dumps([list(d) for d in cap_result.deltas]),
                    to_iso(now),
                ),
            )
    # ==== Tx A committed: caps reserved + intent recorded ====

    bound_permit_token = None
    if policy.bound_permit_action_type is not None:
        # Preconditions already verified at 6c, before caps were reserved; this
        # signs the permit now, naming the independently-minted `permit_jti`
        # already stamped on the intent row above -- never `intent_id` itself,
        # which is sequential and would make `jti` guessable.
        from onedoor.guardrail import bound_permit as bound_permit_mod

        assert permit_jti is not None
        bound_permit_token = bound_permit_mod.issue(
            request=request,
            policy=policy,
            action_object=request.params,
            permit_id=permit_jti,
            issuer=getattr(config, "permit_issuer"),
            issuer_key_id=getattr(config, "permit_issuer_key_id"),
            issuer_private_key=getattr(config, "permit_issuer_private_key"),
            nominal_tier=nominal_tier,
            effective_tier=effective_tier,
            policy_version=None,
            now=now,
        )

    return PermittedIntent(
        request=request,
        intent_audit_id=intent_id,
        effective_tier=effective_tier,
        nominal_tier=nominal_tier,
        compensating_command=policy.compensating_command,
        undo_until=undo_until,
        undo_of=undo_of,
        present_bound=policy.present_bound,
        bound_permit=bound_permit_token,
        sequence_tagged=policy.sequence is not None,
        sequence_tag=policy.sequence.tag_as if policy.sequence is not None else None,
        plan_ref=plan_match.plan_id if plan_match is not None else None,
        plan_consumed_count_after=(
            plan_match.consumed_count_after if plan_match is not None else None
        ),
        plan_consumed_amount_after=(
            plan_match.consumed_amount_after if plan_match is not None else None
        ),
        decision_ref=_decision_ref(
            conn,
            audit_id=intent_id,
            request_id=request.request_id,
            decision=Decision.EXECUTED,
            config=config,
        ),
    )


def reclaim_expired_reservations(conn: Connection, config: EngineConfigLike, now: datetime) -> int:
    """Release the budget of every permit past its deadline with no report.

    A permit that reserved budget but was never reported holds that budget until
    reclaimed. Once the reservation's deadline (``execute_within``) has passed,
    this subtracts the reserved deltas back out of the cap counters, appends a
    ``reservation_expired`` row to the audit log, and voids the reservation.
    Per AADP section 6 the release is an audited event, not a silent timeout.

    Returns the number of reservations reclaimed. Safe to call on every decide
    (the open-reservation lookup is indexed and normally empty) or from a
    maintenance loop. A deadline in the future, or a reservation already settled
    or expired, is left untouched.
    """
    ttl = int(getattr(config, "reservation_ttl_seconds", 3600) or 0)
    if ttl <= 0:
        return 0
    now_iso = to_iso(now)
    reclaimed = 0
    with tx(conn):
        rows = conn.execute(
            "SELECT intent_audit_id, deltas_json FROM cap_reservations "
            "WHERE status='held' AND deadline_utc <= ? ORDER BY intent_audit_id",
            (now_iso,),
        ).fetchall()
        for r in rows:
            rid = int(r["intent_audit_id"])
            intent_row = conn.execute("SELECT * FROM actions_audit WHERE id=?", (rid,)).fetchone()
            if intent_row is not None:
                caps.release(
                    conn,
                    [tuple(d) for d in json.loads(r["deltas_json"], parse_float=Decimal)],
                )
                audit.append_expiry(
                    conn,
                    intent_row,
                    now,
                    detail="reservation reclaimed: deadline passed with no report",
                )
                bus.publish(
                    conn,
                    "action.reservation_expired",
                    {"request_id": intent_row["request_id"], "intent_audit_id": rid},
                )
            conn.execute(
                "UPDATE cap_reservations SET status='expired' WHERE intent_audit_id=?",
                (rid,),
            )
            reclaimed += 1
    return reclaimed


def report_result(
    intent: PermittedIntent | RebuiltIntent,
    *,
    conn: Connection,
    config: EngineConfigLike | None = None,
    outcome: Outcome,
    payload: dict[str, JsonValue] | None,
    error: str | None,
    no_effect: bool = False,
    approved_override: bool = False,
    now: datetime,
) -> ActionResult:
    """Phase B: append the linked execution result for a permitted intent.

    The executed decision this RETURNS carries `approvers`/`escalated_to`/
    `escalated_at` read back from the intent's own audit row -- whatever
    resumption the intent itself resolved is still true of the action this
    call is reporting for, and a caller holding this result (or anything,
    like `onedoor.guardrail.shadow`, comparing against it later) must see
    the same resumption facts the intent's own decision already carried,
    not a fresh decision with them stripped out.

    **This never changes what gets WRITTEN.** The `exec_result` row this
    appends carries none of those three fields -- exactly as it always has
    -- because this call reports an outcome, not a resumption; a
    resumption's own facts are already durable on the intent's own row, and
    writing them a second time here would be recording the same fact twice,
    under a second row whose own digest was never meant to carry it.
    `approved_override`, when true and the intent's own row carries no
    `approvers` to read back (a bare admin override with no approval row to
    look up), marks the RETURNED decision `[]` the same way a resumption
    with no approver on record already reads -- recognized from the call,
    never written as a stored `[]` the digest would then carry.

    Must be called exactly once per :class:`PermittedIntent`, whatever happened.
    The audit log stays append-only: this adds a second row linked to the intent,
    never edits it.

    `outcome` is the four-value vocabulary, not a boolean (ND-039). The disposition
    of the budget reservation depends on it -- see :class:`Outcome`.

    Neither `not_attempted` nor a `failure` reported with `no_effect=True` ever
    releases the rate-dimension delta (AADP -03 §4.1). A rate budget tracks calls
    made, and both of these dispositions still represent one call having
    happened -- releasing it would let a caller cycle decide and
    not_attempted/no_effect without bound. Only the value-dimension deltas
    (eur_day/eur_month) go back.

    `no_effect` (AADP -03 §4.1): on a `failure` report, a positive
    assertion that the action had NO effect at all -- not "it did not succeed" but
    "it is known to have touched nothing". The reservation releases the value
    dimension the same way as `not_attempted` (rate excluded either way, as above).
    Asserted on any outcome other than `failure`, it is **accepted rather than
    refused**: AADP -03 §4.1 requires a PDP to ignore it there, not reject the
    report, so the disposition proceeds exactly as it would with `no_effect`
    absent, and the exec_result row's own `detail` records that it was asserted
    and ignored -- nothing is silently dropped.

    Accepts a :class:`~onedoor.guardrail.rebuild.RebuiltIntent` as well, so a permit
    that outlived the process that issued it can still be reported (ND-010). The
    rebuilt case writes **the same durable rows** and re-reserves nothing -- the
    reservation is already held -- and it carries the intent row's frozen bytes and
    provenance rather than re-serialising them.

    **The result row's `created_at` is `now`, in both cases**: the
    ledger records when it LEARNED the outcome. A rebuilt report arriving after a
    restart is learned now, however long ago the action was requested. Backdating it
    would be the ledger testifying to a moment it did not witness.
    """
    # AADP -03 §4.1: a PDP MUST ignore no_effect on any outcome but failure,
    # never refuse the report over it -- it is not a softer not_attempted, and
    # asserting it against success/timeout/not_attempted would contradict the
    # outcome itself, but the contradiction is dropped, not the report.
    no_effect_ignored = no_effect and outcome is not Outcome.FAILURE
    rebuilt = isinstance(intent, RebuiltIntent)
    row_source: RowSource = intent if rebuilt else intent.request  # type: ignore[assignment,union-attr]
    frozen: tuple[str | bytes, str | None] | None = (
        (intent.params_json, intent.params_provenance) if rebuilt else None  # type: ignore[union-attr]
    )
    no_effect_release = outcome is Outcome.FAILURE and no_effect
    settles = outcome is not Outcome.NOT_ATTEMPTED and not no_effect_release
    released_deltas: list[tuple[str, str, str, int, str]] = []

    with tx(conn):
        if settles:
            # Settle so the reclaimer leaves the budget spent. If the permit was
            # already reclaimed (deadline passed before this report), the reservation
            # is 'expired', this matches nothing, and the released budget stays
            # released: the permit was void, and a late report is recorded for audit
            # but does not silently re-charge the counter.
            conn.execute(
                "UPDATE cap_reservations SET status='settled' "
                "WHERE intent_audit_id=? AND status='held'",
                (intent.intent_audit_id,),
            )
        else:
            # not_attempted: a POSITIVE assertion that the action did not happen, so
            # the value budget it reserved must go back. Settling here is the A4b
            # defect -- permanently charging for an action that never occurred.
            # Only a held reservation is released; one already reclaimed stays
            # reclaimed.
            #
            # Neither disposition ever releases the rate dimension (AADP -03
            # §4.1): a call happened either way -- an attempt
            # was made for `no_effect` by definition, and even `not_attempted`
            # would let a caller cycle decide and not_attempted without bound if
            # its call-count slot came back too. Only the value-dimension deltas
            # (eur_day/eur_month) go back, since those track an effect that is now
            # known not to have occurred.
            row = conn.execute(
                "SELECT deltas_json FROM cap_reservations "
                "WHERE intent_audit_id=? AND status='held'",
                (intent.intent_audit_id,),
            ).fetchone()
            if row is not None:
                all_deltas = [tuple(d) for d in json.loads(row["deltas_json"], parse_float=Decimal)]
                released_deltas = [d for d in all_deltas if d[1] != "rate"]
                if released_deltas:
                    caps.release(conn, released_deltas)
                conn.execute(
                    "UPDATE cap_reservations SET status='released' WHERE intent_audit_id=?",
                    (intent.intent_audit_id,),
                )
                # The release is an AUDITED event, symmetric with reclamation
                # expiry -- never a silent adjustment. Same shape, different kind, so
                # an evidence reader can tell "deadline passed unreported" from "the
                # PEP said it never happened".
                intent_row = conn.execute(
                    "SELECT * FROM actions_audit WHERE id=?", (intent.intent_audit_id,)
                ).fetchone()
                if intent_row is not None:
                    reason = "not_attempted" if outcome is Outcome.NOT_ATTEMPTED else "no_effect"
                    audit.append_expiry(
                        conn,
                        intent_row,
                        now,
                        detail=f"reservation released: report asserted {reason}",
                        kind="reservation_released",
                    )

    # The intent's own decision carried `approvers`/`escalated_to`/`escalated_at`,
    # read back from its audit row, never recomputed, since the
    # resumption this executed decision is reporting for is whatever the intent
    # itself already resolved, not something this call re-derives. Without this,
    # the decision a caller is handed looks exactly like one that never resumed
    # anything, for every resumption this engine actually has.
    intent_decision_row = conn.execute(
        "SELECT approvers_json, escalated_to, escalated_at FROM actions_audit WHERE id=?",
        (intent.intent_audit_id,),
    ).fetchone()
    result_approvers = (
        json.loads(intent_decision_row["approvers_json"])
        if intent_decision_row is not None and intent_decision_row["approvers_json"] is not None
        else None
    )
    result_escalated_to = intent_decision_row["escalated_to"] if intent_decision_row else None
    result_escalated_at = (
        from_iso(intent_decision_row["escalated_at"])
        if intent_decision_row and intent_decision_row["escalated_at"]
        else None
    )

    # `stored_decision` is what the `exec_result` row records -- exactly the
    # executed-path row's own shape, with no resumption facts on it. Those facts are
    # not this row's to carry a second time: the intent's own row already
    # carries them durably, and writing them again here would change this
    # row's `decision_digest` for a fact this row never asserted.
    stored_decision = PolicyDecision(
        decision=Decision.EXECUTED if outcome is Outcome.SUCCESS else Decision.FAILED,
        effective_tier=intent.effective_tier,
        nominal_tier=intent.nominal_tier,
        reason_code=CheckId.PASSED,
        detail=(
            f"no_effect asserted on outcome={outcome.value!r}: ignored, AADP -03 "
            f"§4.1 restricts it to a failure report"
            if no_effect_ignored
            else ""
        ),
    )
    # `returned_decision` is what the caller gets back. It carries the same
    # facts `stored_decision` does, plus the resumption facts read above --
    # in memory only, never written to any row. `approved_override`, when
    # the intent's own row had no approvers to read back, marks this one
    # `[]` the same way a resumption with no approver on record already
    # reads, so a bare override is not indistinguishable from a decision
    # that never resumed anything -- recognised from the call, not stored.
    returned_approvers = result_approvers
    if returned_approvers is None and approved_override:
        returned_approvers = []
    result_decision = stored_decision.model_copy(
        update={
            "approvers": returned_approvers,
            "escalated_to": result_escalated_to,
            "escalated_at": result_escalated_at,
        }
    )
    topic = "action.executed" if outcome is Outcome.SUCCESS else "action.failed"
    event: dict[str, object] = {
        "request_id": str(row_source.request_id),
        "outcome": outcome.value,
    }
    # connector_ok is NULL for not_attempted: there was no connector call to succeed
    # or fail. Recording False would assert an attempt that never happened, which is
    # the first half of the A4b defect.
    ok: bool | None = None if outcome is Outcome.NOT_ATTEMPTED else outcome is Outcome.SUCCESS
    batch = int(getattr(config, "audit_group_commit", 0) or 0)

    if batch > 0:
        # Buffered path: the row is queued and written with its neighbours. A crash
        # before the flush leaves an intent with no result — the recoverable state
        # invariant 9 already requires — never a permit that looks discharged.
        audit.append_buffered(
            conn,
            row_source,
            stored_decision,
            kind="exec_result",
            now=now,
            parent_id=intent.intent_audit_id,
            connector_ok=ok,
            error=error,
            payload=payload,
            undo_of=intent.undo_of,
            frozen=frozen,
            event_topic=topic,
            event_payload=json.dumps(event, default=str),
            outcome=outcome.value,
        )
        if audit.buffered_len(conn) >= batch:
            audit.flush(conn)
    else:
        with tx(conn):
            audit.append(
                conn,
                row_source,
                stored_decision,
                kind="exec_result",
                now=now,
                parent_id=intent.intent_audit_id,
                connector_ok=ok,
                error=error,
                payload=payload,
                undo_of=intent.undo_of,
                outcome=outcome.value,
                frozen=frozen,
            )
            bus.publish(conn, topic, event)

    if (
        outcome is Outcome.SUCCESS
        and isinstance(intent, PermittedIntent)
        and intent.sequence_tagged
        and intent.request.session_id is not None
    ):
        # A rebuilt intent (ND-010) carries no `session_id` of its own to key
        # this on -- not recorded for that case, a narrow, disclosed gap, not
        # an oversight (a restart-surviving permit's settlement still releases
        # its budget correctly; only this table's own view of it is missed).
        sequence.record_event(
            conn,
            session_id=intent.request.session_id,
            action_type=intent.request.action_type,
            tag=intent.sequence_tag,
            at=now,
            audit_id=intent.intent_audit_id,
            max_events_per_session=int(getattr(config, "sequence_max_events_per_session", 500)),
        )

    return ActionResult(
        request_id=UUID(str(row_source.request_id)),
        decision=result_decision,
        executed=ok,
        connector_ok=ok,
        connector_payload=payload,
        error=error,
        audit_id=intent.intent_audit_id,
        undo_available_until=intent.undo_until if ok else None,
        # The reference to the ORIGINAL permit, unchanged -- a connector outcome
        # (success, failure, timeout) never revises what was decided. Propagated
        # from the intent, never recomputed here: `result_decision.decision` can
        # be FAILED, which has no defined decision_ref verdict on purpose.
        decision_ref=intent.decision_ref,
        bound_permit=intent.bound_permit,
    )


NIL_REQUEST_ID = UUID(int=0)


def decide_raw(
    raw: Mapping[str, object],
    *,
    conn: Connection,
    config: EngineConfigLike,
    now: datetime,
    policy_store: PolicyStore | None = None,
) -> ActionResult | PermittedIntent:
    """Total form of :func:`decide_and_reserve` — never raises on a malformed request.

    ``decide_and_reserve`` takes a validated :class:`ActionRequest`, so a caller
    that hands it attacker-shaped input gets a ``ValidationError`` rather than a
    verdict. Fail-closed behaviour then depends on whether *that caller* wraps the
    call, i.e. on code the decision point does not own.

    ``decide_raw`` accepts the unvalidated mapping and turns a validation failure
    into an ordinary denial with reason ``malformed``, so the guarantee belongs to
    the decision point.

    Internal errors are deliberately **not** swallowed: an exception from the
    policy store, the database or the cap ledger propagates, because converting a
    bug into a routine denial would hide it. From an enforcement point's view an
    unreachable or erroring PDP is already governed by its configured
    unreachability behaviour.
    """
    try:
        request = ActionRequest.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - any validation failure is a denial
        request_id = raw.get("request_id") if isinstance(raw, Mapping) else None
        try:
            resolved = UUID(str(request_id))
        except (TypeError, ValueError):
            resolved = NIL_REQUEST_ID
        return ActionResult(
            request_id=resolved,
            decision=PolicyDecision(
                decision=Decision.DENIED,
                # No policy was resolved, so no tier applies; report the most
                # restrictive one rather than inventing a permissive default.
                effective_tier=Tier.CONFIRM,
                nominal_tier=Tier.CONFIRM,
                reason_code=CheckId.MALFORMED,
                detail=f"request failed validation: {type(exc).__name__}",
            ),
        )
    return decide_and_reserve(request, conn=conn, config=config, now=now, policy_store=policy_store)
