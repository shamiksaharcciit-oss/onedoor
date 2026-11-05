"""A gate node before an acting node: onedoor decides first; a Tier-3 action
holds the graph as a real LangGraph interrupt, resumed when a person
approves through onedoor.
"""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import uuid4
from zoneinfo import ZoneInfo

from langgraph.types import interrupt

from onedoor.guardrail import approvals, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Outcome, Source
from onedoor.store.clock import now_utc
from onedoor.store.db import Database


class PayState(TypedDict):
    payee: str
    amount_eur: float
    result: str


def build_engine(db_path: str, *, require_approval: bool) -> tuple[Any, EngineConfig]:
    from onedoor.guardrail.models import Bounds, Policy, Tier

    db = Database(db_path)
    db.init()
    conn = db.connect(check_same_thread=False)
    policy_loader.upsert(
        conn,
        Policy(
            action_type="tool.send_payment",
            tier=Tier.CONFIRM if require_approval else Tier.AUTO,
            dry_run=False,
            compensating_command="tool.send_payment" if not require_approval else None,
            bounds=Bounds(strict_params=False),
        ),
    )
    config = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=30.0, tz=ZoneInfo("UTC")
    )
    return conn, config


def make_pay_node(conn: Any, config: EngineConfig):
    def pay_node(state: PayState) -> PayState:
        now = now_utc()
        request = ActionRequest(
            request_id=uuid4(),
            action_type="tool.send_payment",
            params={"payee": state["payee"], "amount_eur": state["amount_eur"]},
            source=Source.LLM,
            rationale="langgraph example",
            created_at=now,
        )
        outcome = decide_and_reserve(request, conn=conn, config=config, now=now)
        if isinstance(outcome, PermittedIntent):
            report_result(
                outcome,
                conn=conn,
                config=config,
                outcome=Outcome.SUCCESS,
                payload={},
                error=None,
                now=now_utc(),
            )
            return {**state, "result": f"paid {state['amount_eur']} to {state['payee']}"}

        decision = outcome.decision
        if decision.decision.value != "proposed":
            return {
                **state,
                "result": f"onedoor: {decision.decision.value} ({decision.reason_code.value})",
            }

        resume = interrupt(
            {
                "approval_id": outcome.approval_id,
                "payee": state["payee"],
                "amount_eur": state["amount_eur"],
            }
        )
        if resume != "approved":
            return {**state, "result": f"onedoor: not approved ({resume})"}

        resume_now = now_utc()
        original = approvals.cas_approve(conn, outcome.approval_id, "langgraph-human", resume_now)
        resumed_request = original.model_copy(
            update={"request_id": uuid4(), "created_at": resume_now}
        )
        resumed = decide_and_reserve(
            resumed_request,
            conn=conn,
            config=config,
            now=resume_now,
            approved_override=True,
            resumes_audit_id=approvals.proposed_audit_id(conn, outcome.approval_id),
            consumes_approval=outcome.approval_id,
        )
        if isinstance(resumed, PermittedIntent):
            report_result(
                resumed,
                conn=conn,
                config=config,
                outcome=Outcome.SUCCESS,
                payload={},
                error=None,
                now=now_utc(),
            )
            return {**state, "result": f"paid {state['amount_eur']} to {state['payee']} (approved)"}
        return {**state, "result": f"onedoor: {resumed.decision.decision.value}"}

    return pay_node
