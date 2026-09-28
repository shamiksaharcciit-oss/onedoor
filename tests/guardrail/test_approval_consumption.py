"""An approval is consumed when a resumption is decided against it, whatever the verdict.

One human decision authorises one decision, not a standing permission. A resumption the
engine denies -- the kill switch, the budget -- still uses the approval up, and nothing
brings it back to `approved`, where a later caller could present it again.
"""

from __future__ import annotations

from sqlite3 import Connection

import pytest

from onedoor.connectors import mock
from onedoor.guardrail import approval_ref, killswitch, policy_loader
from onedoor.guardrail.approval_ref import ApprovalRefStatus
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute, resume_approval
from onedoor.guardrail.models import (
    Bounds,
    Caps,
    CheckId,
    Decision,
    Policy,
    Tier,
)
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _state(conn: Connection, approval_id: int) -> str:
    return str(conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()[0])


def _propose(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig, action: str
) -> int:
    result = evaluate_and_execute(
        make_request(action), conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert result.approval_id is not None
    return result.approval_id


def test_a_resumption_denied_by_the_budget_still_consumes_the_approval(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.confirm_once",
            tier=Tier.CONFIRM,
            dry_run=False,
            caps=Caps(daily_rate=1),
            bounds=Bounds(strict_params=False),
        ),
    )
    registry.register("demo.confirm_once", mock.act_ok)
    first = _propose(conn, registry, config, "demo.confirm_once")
    second = _propose(conn, registry, config, "demo.confirm_once")

    ran = resume_approval(
        first, "operator", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert ran.executed is True
    refused = resume_approval(
        second, "operator", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert refused.decision.decision == Decision.DENIED
    assert refused.decision.reason_code == CheckId.RATE_EXHAUSTED

    assert _state(conn, first) == "consumed"
    assert _state(conn, second) == "consumed"
    with pytest.raises(ApprovalError):
        resume_approval(
            second, "operator", conn=conn, registry=registry, config=config, now=FROZEN_NOW
        )


def test_a_resumption_denied_by_the_kill_switch_cannot_be_presented_again(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    approval_id = _propose(conn, registry, config, "demo.confirm")
    with tx(conn):
        killswitch.set_engaged(conn, True, origin="operator")
    refused = resume_approval(
        approval_id, "operator", conn=conn, registry=registry, config=config, now=FROZEN_NOW
    )
    assert refused.decision.reason_code == CheckId.KILL_SWITCH
    assert _state(conn, approval_id) == "consumed"

    with tx(conn):
        killswitch.set_engaged(conn, False, origin="operator")
    later = make_request("demo.confirm").model_copy(update={"approval_ref": approval_id})
    outcome = decide_and_reserve(later, conn=conn, config=config, now=FROZEN_NOW)
    assert not isinstance(outcome, PermittedIntent), "a consumed approval grants nothing"


def test_a_consumed_approval_is_reported_as_consumed_when_presented(
    conn: Connection, registry: ConnectorRegistry, config: EngineConfig
) -> None:
    approval_id = _propose(conn, registry, config, "demo.confirm")
    with tx(conn):
        conn.execute("UPDATE approvals SET state='consumed' WHERE id=?", (approval_id,))
        resolution = approval_ref.resolve(
            conn, approval_ref=approval_id, presented=make_request("demo.confirm"), now=FROZEN_NOW
        )
    assert resolution.authorised is False
    assert resolution.status == ApprovalRefStatus.CONSUMED
