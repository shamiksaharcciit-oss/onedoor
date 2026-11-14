"""Policy tests: which decisions a policy change moves.

Given an old policy and a candidate, and a batch of requests, :func:`compare`
answers one question for each: does the candidate decide this differently
from the old policy, right now? Built on `onedoor.guardrail.shadow.evaluate`,
so a policy test and a shadow-mode run agree about what a policy decides by
construction, not by two implementations kept in step by hand.

This is a comparison tool, not a decision point: nothing here is reserved,
denied, or recorded as a real decision. A caller wanting a durable record of
one side or the other already has `shadow.record` for that.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from onedoor.guardrail import shadow
from onedoor.guardrail.models import ActionRequest, Policy


@dataclass(frozen=True)
class PolicyTestCase:
    """One request whose decision the candidate policy moves."""

    request: ActionRequest
    old: shadow.ShadowDecision
    candidate: shadow.ShadowDecision


@dataclass(frozen=True)
class PolicyTestReport:
    """`coverage` names what every case in `moved` was actually checked
    against -- the same id `shadow.evaluate` stamped onto each decision, not
    a second, independently-typed description of it."""

    coverage: str
    moved: list[PolicyTestCase]


def compare(
    conn: sqlite3.Connection,
    old_policy: Policy,
    candidate_policy: Policy,
    requests: list[ActionRequest],
    *,
    now: datetime,
    tz: ZoneInfo,
    kill_switch_engaged: bool,
) -> PolicyTestReport:
    """Which of `requests` the candidate policy decides differently.

    Evaluates every request against both policies and keeps only the cases
    where the decision, the effective tier, or the reason differs -- a
    request both policies deny for the SAME reason is not a case the
    candidate moves, even though it is still a denial under both. Order is
    the order `requests` was given, so a caller comparing against a fixed
    sample sees a stable report.
    """
    moved: list[PolicyTestCase] = []
    for request in requests:
        old_result = shadow.evaluate(
            conn, old_policy, request, now=now, tz=tz, kill_switch_engaged=kill_switch_engaged
        )
        candidate_result = shadow.evaluate(
            conn,
            candidate_policy,
            request,
            now=now,
            tz=tz,
            kill_switch_engaged=kill_switch_engaged,
        )
        if (
            old_result.decision != candidate_result.decision
            or old_result.effective_tier != candidate_result.effective_tier
            or old_result.reason_code != candidate_result.reason_code
        ):
            moved.append(PolicyTestCase(request, old_result, candidate_result))
    return PolicyTestReport(coverage=shadow.COVERAGE_ID, moved=moved)
