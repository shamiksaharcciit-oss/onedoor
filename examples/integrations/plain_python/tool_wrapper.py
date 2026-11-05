"""Wrap any plain Python tool function so it calls onedoor before acting and
reports what happened after. No framework: this is the shape every other
integration in this folder builds on.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from sqlite3 import Connection
from uuid import uuid4

from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Outcome, Source
from onedoor.guardrail.policy import PolicyStore


def guarded(
    action_type: str, *, conn: Connection, config: EngineConfig, now: Callable[[], datetime]
) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """A decorator: ``fn(**params) -> dict`` becomes a tool onedoor governs.
    Returns ``{"status": "denied"|"held"|"dry_run", "reason": ...}`` instead of
    calling ``fn`` when onedoor does not permit it; calls ``fn`` and reports
    its outcome otherwise."""

    def decorate(fn: Callable[..., dict]) -> Callable[..., dict]:
        def wrapped(**params: object) -> dict:
            request = ActionRequest(
                request_id=uuid4(),
                action_type=action_type,
                params=params,  # type: ignore[arg-type]
                source=Source.LLM,
                rationale="plain-python example",
                created_at=now(),
            )
            outcome = decide_and_reserve(
                request, conn=conn, config=config, now=now(), policy_store=PolicyStore()
            )
            if not isinstance(outcome, PermittedIntent):
                return {
                    "status": outcome.decision.decision.value,
                    "reason": outcome.decision.reason_code.value,
                }
            try:
                result = fn(**params)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                report_result(
                    outcome,
                    conn=conn,
                    config=config,
                    outcome=Outcome.FAILURE,
                    payload=None,
                    error=str(exc),
                    now=now(),
                )
                raise
            report_result(
                outcome,
                conn=conn,
                config=config,
                outcome=Outcome.SUCCESS,
                payload=result,
                error=None,
                now=now(),
            )
            return {"status": "executed", "result": result}

        return wrapped

    return decorate
