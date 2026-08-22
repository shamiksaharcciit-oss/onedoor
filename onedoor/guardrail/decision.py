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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from sqlite3 import Connection
from uuid import UUID

from onedoor.guardrail import approvals, audit, bounds, caps, killswitch, opaque_hosts
from onedoor.guardrail.audit import RowSource
from onedoor.guardrail.models import (
    ActionRequest,
    ActionResult,
    CheckId,
    Decision,
    EngineConfigLike,
    JsonValue,
    Outcome,
    PolicyDecision,
    Source,
    Tier,
)
from onedoor.guardrail.policy import PolicyStore
from onedoor.guardrail.rebuild import RebuiltIntent
from onedoor.guardrail.urlcanon import (
    CANON_SCHEMA,
    CanonicalizationError,
    url_rule_matches,
)
from onedoor.store import bus
from onedoor.store.clock import to_iso
from onedoor.store.db import tx

# EngineConfig lives in executor.py for backwards compatibility; import lazily
# to avoid a circular import at module load.


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


def decide_and_reserve(
    request: ActionRequest,
    *,
    conn: Connection,
    config: EngineConfigLike,
    now: datetime,
    policy_store: PolicyStore | None = None,
    approved_override: bool = False,
) -> ActionResult | PermittedIntent:
    """Phase A: evaluate the ordered checks; reserve caps; record intent.

    Returns an :class:`ActionResult` when the decision is terminal (nothing to
    enforce), or a :class:`PermittedIntent` when the action may proceed and the
    caller owns execution + :func:`report_result`.
    """
    store = policy_store or PolicyStore()
    undo_of = request.parent_audit_id if request.source == Source.UNDO else None

    # --- Idempotency / replay guard (no transaction) ---
    prior = audit.result_for_request_id(conn, request.request_id)
    if prior is not None:
        return prior

    # Reclaim any reservation abandoned past its deadline before evaluating, so
    # budget a never-reported permit is still holding is freed for this request.
    reclaim_expired_reservations(conn, config, now)

    with tx(conn):
        # 1. KILL-SWITCH FIRST (invariant: before policy lookup).
        kill = killswitch.is_engaged(conn)

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
                    # EXISTING `malformed` -- no new wire vocabulary (R013) -- with
                    # the failure recorded distinctly in evidence so an operator can
                    # tell a probe of the effect matcher from a broken client.
                    decision = PolicyDecision(
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
                        undo_of=undo_of,
                        malformed_kind="url_canonicalization",
                        canon_schema=CANON_SCHEMA,
                    )
                    bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                    return ActionResult(
                        request_id=request.request_id, decision=decision, audit_id=aid
                    )
            if matched:
                effects.extend(e for e in rule.add_effects if e not in effects)
        effect_policies = [ep for e in effects if (ep := store.get_effect(conn, e)) is not None]

        # 3/4. Resolve effective tier (+ Tier-1 integrity, kill-switch clamp).
        reason_confirm = CheckId.TIER_CONFIRM
        confirm_detail = ""
        if approved_override:
            if kill:
                decision = PolicyDecision(
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
                    undo_of=undo_of,
                    opaque_class=opaque_class,
                )
                bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
                return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)
            effective_tier = Tier.AUTO
        elif policy.tier == Tier.OBSERVE:
            effective_tier = Tier.OBSERVE  # reads are exempt from the kill switch
        elif kill:
            effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.KILL_SWITCH
        else:
            effective_tier = policy.tier
            if policy.is_default_deny:
                reason_confirm = CheckId.DEFAULT_DENY
            # Effect tier floors: an action inherits the strictest floor of its
            # effects — aliasing-resistant escalation ("moves money" is Tier 3
            # no matter which tool name moved it).
            for ep in effect_policies:
                if ep.min_tier is not None and int(ep.min_tier) > int(effective_tier):
                    effective_tier = ep.min_tier
                    if effective_tier == Tier.CONFIRM:
                        reason_confirm = CheckId.EFFECT_FLOOR

        # OPAQUE-HOST INVARIANT (R027 §1). Stated as an invariant, never left to
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
        # The reasoning core settled it on: the founding rule is that an action whose
        # consequences cannot be VERIFIED must not be auto-executed -- not that it can
        # never happen. A redirector's true destination is unknowable without the
        # network call determinism forbids, and the honest answer to *unknowable* is
        # "a human decides", not "nobody decides". So the floor is the human-approval
        # tier, and a policy that offers no approver ends in denial rather than in
        # execution.
        if opaque_class is not None and not approved_override and effective_tier != Tier.OBSERVE:
            # OBSERVE is exempt because it never executes at all: a read returns an
            # audited no-op, never a permit. The invariant is about execution.
            if int(effective_tier) < int(Tier.CONFIRM):
                effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.EFFECT_FLOOR
            # The class is in `opaque_class`; the REASON rides here, so an operator
            # reading the row can tell this escalation from an ordinary tier floor
            # without knowing what the class means (R027 §1, second condition).
            confirm_detail = (
                f"destination unverifiable without a network call; host is in the "
                f"declared opaque class {opaque_class}"
            )

        # Reversibility precondition: ANY tier that may execute without a human
        # (auto and auto_capped alike) requires a registered means of reversal.
        # Scoping this to Tier.AUTO alone let an irreversible action auto-execute
        # merely because it also carried a budget.
        if (
            effective_tier in (Tier.AUTO, Tier.AUTO_CAPPED)
            and not approved_override
            and not policy.compensating_command
        ):
            effective_tier = Tier.CONFIRM
            reason_confirm = CheckId.NO_COMPENSATION

        # 5. OBSERVE — audit a no-op read and return.
        if effective_tier == Tier.OBSERVE:
            decision = PolicyDecision(
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
                undo_of=undo_of,
                opaque_class=opaque_class,
            )
            bus.publish(conn, "action.observed", {"request_id": str(request.request_id)})
            return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)

        # 6. BOUNDS — validated for every tier that could execute OR be proposed,
        #    so a human never approves an out-of-bounds action.
        bounds_result = bounds.validate(policy.bounds, request.params)
        if not bounds_result.ok:
            decision = PolicyDecision(
                decision=Decision.DENIED,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=CheckId.BOUNDS,
                detail=bounds_result.detail,
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                undo_of=undo_of,
                opaque_class=opaque_class,
            )
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)

        # 7. TIER 3 — propose and confirm.
        if effective_tier == Tier.CONFIRM:
            approval_id = approvals.create(conn, request, config.approval_ttl_seconds, now)
            decision = PolicyDecision(
                decision=Decision.PROPOSED,
                effective_tier=Tier.CONFIRM,
                nominal_tier=nominal_tier,
                reason_code=reason_confirm,
                requires_approval=True,
                compensating_command=policy.compensating_command,
                detail=confirm_detail,
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                approval_id=approval_id,
                undo_of=undo_of,
                opaque_class=opaque_class,
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
            )

        # --- Auto path (Tier 1, Tier 2, or approved override) ---

        # 8. DRY-RUN — before caps (a rehearsal must not spend a real budget).
        is_dry = not approved_override and (
            policy.dry_run or (policy.dry_run_until is not None and now < policy.dry_run_until)
        )
        if is_dry:
            decision = PolicyDecision(
                decision=Decision.DRY_RUN,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=CheckId.DRY_RUN,
                dry_run=True,
                detail="would have executed",
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                undo_of=undo_of,
                opaque_class=opaque_class,
            )
            bus.publish(conn, "action.dry_run", {"request_id": str(request.request_id)})
            return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)

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
            decision = PolicyDecision(
                decision=Decision.DENIED,
                effective_tier=effective_tier,
                nominal_tier=nominal_tier,
                reason_code=cap_result.reason,
                detail=cap_result.detail,
                # ND-003: present iff the verdict is deny and the reason is a cap.
                # `cost_unknown` also arrives here and carries no budget -- there is
                # no budget state to report when the amount could not be resolved.
                budget=cap_result.budget,
            )
            aid = audit.append(
                conn,
                request,
                decision,
                kind="decision",
                now=now,
                undo_of=undo_of,
                opaque_class=opaque_class,
            )
            bus.publish(conn, "action.denied", {"request_id": str(request.request_id)})
            return ActionResult(request_id=request.request_id, decision=decision, audit_id=aid)

        # 10. INTENT — record that we are about to execute. Set the undo window
        #     for reversible Tier-1 actions.
        undo_until = None
        if effective_tier == Tier.AUTO and not approved_override and policy.compensating_command:
            undo_until = now + timedelta(seconds=policy.undo_window_seconds)
        intent_decision = PolicyDecision(
            decision=Decision.EXECUTED,
            effective_tier=effective_tier,
            nominal_tier=nominal_tier,
            reason_code=CheckId.PASSED,
            compensating_command=policy.compensating_command,
        )
        intent_id = audit.append(
            conn,
            request,
            intent_decision,
            kind="exec_intent",
            now=now,
            undo_until=undo_until,
            undo_of=undo_of,
            opaque_class=opaque_class,
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

    return PermittedIntent(
        request=request,
        intent_audit_id=intent_id,
        effective_tier=effective_tier,
        nominal_tier=nominal_tier,
        compensating_command=policy.compensating_command,
        undo_until=undo_until,
        undo_of=undo_of,
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
    now: datetime,
) -> ActionResult:
    """Phase B: append the linked execution result for a permitted intent.

    Must be called exactly once per :class:`PermittedIntent`, whatever happened.
    The audit log stays append-only: this adds a second row linked to the intent,
    never edits it.

    `outcome` is the four-value vocabulary, not a boolean (ND-039). The disposition
    of the budget reservation depends on it, per R005 -- see :class:`Outcome`.

    Accepts a :class:`~onedoor.guardrail.rebuild.RebuiltIntent` as well, so a permit
    that outlived the process that issued it can still be reported (ND-010). The
    rebuilt case writes **the same durable rows** and re-reserves nothing -- the
    reservation is already held -- and it carries the intent row's frozen bytes and
    provenance rather than re-serialising them.

    **The result row's `created_at` is `now`, in both cases, and that is R033 §3**: the
    ledger records when it LEARNED the outcome. A rebuilt report arriving after a
    restart is learned now, however long ago the action was requested. Backdating it
    would be the ledger testifying to a moment it did not witness.
    """
    rebuilt = isinstance(intent, RebuiltIntent)
    row_source: RowSource = intent if rebuilt else intent.request  # type: ignore[assignment,union-attr]
    frozen: tuple[str | bytes, str | None] | None = (
        (intent.params_json, intent.params_provenance) if rebuilt else None  # type: ignore[union-attr]
    )
    settles = outcome is not Outcome.NOT_ATTEMPTED
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
            # the budget it reserved must go back. Settling here is the A4b defect --
            # permanently charging for an action that never occurred. Only a held
            # reservation is released; one already reclaimed stays reclaimed.
            row = conn.execute(
                "SELECT deltas_json FROM cap_reservations "
                "WHERE intent_audit_id=? AND status='held'",
                (intent.intent_audit_id,),
            ).fetchone()
            if row is not None:
                released_deltas = [
                    tuple(d) for d in json.loads(row["deltas_json"], parse_float=Decimal)
                ]
                caps.release(conn, released_deltas)
                conn.execute(
                    "UPDATE cap_reservations SET status='released' WHERE intent_audit_id=?",
                    (intent.intent_audit_id,),
                )
                # R005: the release is an AUDITED event, symmetric with reclamation
                # expiry -- never a silent adjustment. Same shape, different kind, so
                # an evidence reader can tell "deadline passed unreported" from "the
                # PEP said it never happened".
                intent_row = conn.execute(
                    "SELECT * FROM actions_audit WHERE id=?", (intent.intent_audit_id,)
                ).fetchone()
                if intent_row is not None:
                    audit.append_expiry(
                        conn,
                        intent_row,
                        now,
                        detail="reservation released: report asserted not_attempted",
                        kind="reservation_released",
                    )

    result_decision = PolicyDecision(
        decision=Decision.EXECUTED if outcome is Outcome.SUCCESS else Decision.FAILED,
        effective_tier=intent.effective_tier,
        nominal_tier=intent.nominal_tier,
        reason_code=CheckId.PASSED,
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
            result_decision,
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
                result_decision,
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

    return ActionResult(
        request_id=UUID(str(row_source.request_id)),
        decision=result_decision,
        executed=ok,
        connector_ok=ok,
        connector_payload=payload,
        error=error,
        audit_id=intent.intent_audit_id,
        undo_available_until=intent.undo_until if ok else None,
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
