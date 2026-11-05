"""No model, no network: calls the tool handler through the framework
directly, exactly as the server's own dispatch would."""

from __future__ import annotations

import tempfile

from guarded_server import PAID, configure, send_payment


def test_a_permitted_call_executes() -> None:
    PAID.clear()
    configure(tempfile.mktemp(suffix=".db"))
    result = send_payment(payee="acme", amount_eur=25.0)
    assert result == "paid 25.0 to acme"
    assert PAID == [25.0]


def test_an_unlisted_tool_action_is_denied() -> None:
    PAID.clear()
    configure(tempfile.mktemp(suffix=".db"))
    # A second server with no policy for this action type at all denies by default.
    from uuid import uuid4
    from zoneinfo import ZoneInfo

    from onedoor.guardrail.decision import decide_and_reserve
    from onedoor.guardrail.executor import EngineConfig
    from onedoor.guardrail.models import ActionRequest, Source
    from onedoor.store.clock import now_utc
    from onedoor.store.db import Database

    db = Database(tempfile.mktemp(suffix=".db"))
    db.init()
    conn = db.connect()
    config = EngineConfig(
        approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC")
    )
    now = now_utc()
    result = decide_and_reserve(
        ActionRequest(
            request_id=uuid4(),
            action_type="tool.unmapped",
            params={},
            source=Source.LLM,
            rationale="test",
            created_at=now,
        ),
        conn=conn,
        config=config,
        now=now,
    )
    assert result.decision.decision.value == "denied"
