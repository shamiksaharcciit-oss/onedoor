"""Runs one scenario's script of actions, without onedoor and with it, and
records what happened for each action in both modes.

Without onedoor: a plain executor carries out every proposed action against
the simulated tool, with the same scripted tool outcomes as the with-onedoor
side -- there is no gate, so nothing is held or denied.

With onedoor: every category but ``permits`` goes through the running local
service (decide, then report once permitted); ``permits`` goes through the
library directly (see ``permits.py`` for why). A kill-switch action toggles
the switch through the service's admin endpoint first; an approval action
answers (or leaves pending) the resulting approval the same way.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from eval.harness import permits as permits_mod
from eval.harness.scenario import Action, Scenario
from eval.harness.service import RunningService
from eval.harness.tool import SimulatedTool

# Called once per action that reaches the simulated tool, only when recording
# (eval/harness/record.py): (scenario, action_index, action, decision_ref,
# bound_permit, the zero-arg tool call to make) -> the tool's outcome string.
# ``None`` (the default, everywhere outside --record) means "call the tool
# directly, record nothing."
RecordHook = Callable[
    [Scenario, int, Action, dict[str, Any] | None, str | None, Callable[[], str]], str
]

HELD = "held"
DENIED = "denied"
EXECUTED = "executed"  # a terminal row the service already settled (tier-0 reads)
PERMITTED = "permitted"  # needs a tool call, then one report, to settle
DRY_RUN = "dry_run"
REFUSED = "refused"  # permits category: recipient-side verification refused
_SETTLES_WITH_A_TOOL_CALL = (EXECUTED, PERMITTED)


@dataclass(frozen=True)
class ActionOutcome:
    scenario: str
    category: str
    action_index: int
    action_type: str
    ground_truth: str
    mode: str  # "without" | "with"
    decision: str
    reason: str
    effect_happened: bool
    held_for_person: bool = False
    approval_id: int | None = None
    decision_ref: dict[str, Any] | None = None
    bound_permit: str | None = None


def run_without(scenario: Scenario) -> list[ActionOutcome]:
    tool = SimulatedTool()
    outcomes = []
    for i, action in enumerate(scenario.actions):
        result = tool.call(action.action_type, action.params, tool_outcome=action.tool_outcome)
        outcomes.append(
            ActionOutcome(
                scenario=scenario.name,
                category=scenario.category,
                action_index=i,
                action_type=action.action_type,
                ground_truth=action.ground_truth,
                mode="without",
                decision=EXECUTED,
                reason="no_gate",
                effect_happened=(result != "failure"),
            )
        )
    return outcomes


def run_with(
    scenario: Scenario,
    *,
    svc: RunningService | None,
    db_path: str,
    now: datetime,
    record_hook: RecordHook | None = None,
) -> list[ActionOutcome]:
    if scenario.category == "permits":
        return _run_with_permits(scenario, db_path=db_path, now=now, record_hook=record_hook)
    assert svc is not None, "every category but permits runs through a started service"
    tool = SimulatedTool()
    outcomes: list[ActionOutcome] = []
    for i, action in enumerate(scenario.actions):
        if action.wait_seconds:
            time.sleep(action.wait_seconds)
        approval_ref = None
        if action.approval_ref_from is not None:
            approval_ref = outcomes[action.approval_ref_from].approval_id
        outcomes.append(
            _run_one_with_service(
                scenario,
                i,
                action,
                svc=svc,
                tool=tool,
                approval_ref=approval_ref,
                record_hook=record_hook,
            )
        )
    return outcomes


def _classify_reply(reply: dict[str, object]) -> tuple[str, str]:
    decision = reply["decision"]
    if decision == "permitted":
        return PERMITTED, reply["reason"]
    if decision == "executed":
        return EXECUTED, reply["reason"]
    if decision == "dry_run":
        return DRY_RUN, reply["reason"]
    if decision == "proposed":
        return HELD, reply["reason"]
    return DENIED, reply["reason"]


def _run_one_with_service(
    scenario: Scenario,
    index: int,
    action: Action,
    *,
    svc: RunningService,
    tool: SimulatedTool,
    approval_ref: int | None = None,
    record_hook: RecordHook | None = None,
) -> ActionOutcome:
    if action.kill_switch is not None:
        svc.admin_set_killswitch(action.kill_switch)

    body = {"action_type": action.action_type, "params": action.params}
    if approval_ref is not None:
        body["approval_ref"] = approval_ref
    reply = svc.decide.decide(body)
    decision, reason = _classify_reply(reply)
    held_for_person = False
    approval_id = reply.get("approval_id")

    if decision == HELD:
        if action.approve == "grant" and approval_id is not None:
            resumed = svc.admin_approve(approval_id)
            decision, reason = _classify_reply(resumed)
            reply = resumed
        elif action.approve == "deny" and approval_id is not None:
            svc.admin_deny(approval_id)
            decision, reason = DENIED, "operator_denied"
        else:
            held_for_person = True

    effect_happened = False
    decision_ref = reply.get("decision_ref")
    bound_permit = reply.get("bound_permit")
    if decision in _SETTLES_WITH_A_TOOL_CALL:
        intent_audit_id = reply.get("intent_audit_id")

        def _call_tool() -> str:
            return tool.call(action.action_type, action.params, tool_outcome=action.tool_outcome)

        if record_hook is not None:
            outcome = record_hook(scenario, index, action, decision_ref, bound_permit, _call_tool)
        else:
            outcome = _call_tool()
        effect_happened = outcome != "failure"
        if decision == PERMITTED and intent_audit_id is not None:
            svc.decide.report(
                {"intent_audit_id": intent_audit_id, "outcome": outcome},
                request_id=str(intent_audit_id),
            )

    return ActionOutcome(
        scenario=scenario.name,
        category=scenario.category,
        action_index=index,
        action_type=action.action_type,
        ground_truth=action.ground_truth,
        mode="with",
        decision=decision,
        reason=reason,
        effect_happened=effect_happened,
        held_for_person=held_for_person,
        approval_id=approval_id,
        decision_ref=decision_ref,
        bound_permit=bound_permit,
    )


def _run_with_permits(
    scenario: Scenario, *, db_path: str, now: datetime, record_hook: RecordHook | None = None
) -> list[ActionOutcome]:
    run = permits_mod.start(db_path, now=now)
    tool = SimulatedTool()
    outcomes = []
    for i, action in enumerate(scenario.actions):
        shape = action.permit or "fresh"
        verified, detail, decision_ref, bound_permit = permits_mod.present(
            run, shape=shape, now=now
        )
        if verified:

            def _call_tool() -> str:
                return tool.call(
                    action.action_type, action.params, tool_outcome=action.tool_outcome
                )

            if record_hook is not None:
                outcome = record_hook(scenario, i, action, decision_ref, bound_permit, _call_tool)
            else:
                outcome = _call_tool()
            effect_happened = outcome != "failure"
            decision = EXECUTED
        else:
            effect_happened = False
            decision = REFUSED
        outcomes.append(
            ActionOutcome(
                scenario=scenario.name,
                category=scenario.category,
                action_index=i,
                action_type=action.action_type,
                ground_truth=action.ground_truth,
                mode="with",
                decision=decision,
                reason=detail,
                effect_happened=effect_happened,
                decision_ref=decision_ref,
                bound_permit=bound_permit,
            )
        )
    return outcomes
