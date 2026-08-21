"""The LiteLLM example must honour the two-phase contract (ND-021).

Until 0.3.6 this example called `report_result(ok=True)` inside the pre-call
hook — asserting an action had succeeded before the gateway had done anything.
It was published, documented, and cited in the draft's Implementation Status as
a demonstration that the gateway hook point is viable but not conformant.

The first test below is the one that would have caught it, and is the point of
the ticket: after the pre-call hook, the audit holds an intent and **no result**.
The rest hold the other half — that a result does arrive, exactly once, on both
the success and failure paths, and against the right permit under concurrency.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from examples.litellm_guardrail import OneDoorGuardrail, OneDoorRejection

POLICIES = Path(__file__).resolve().parents[2] / "examples" / "litellm_policies.yaml"


class FakeUsage:
    total_tokens = 42


class FakeResponse:
    model = "gpt-4o-mini"
    usage = FakeUsage()


@pytest.fixture
def guardrail(tmp_path: Path) -> Iterator[OneDoorGuardrail]:
    g = OneDoorGuardrail(
        policies=str(POLICIES),
        db_path=str(tmp_path / "litellm.db"),
        guardrail_name="onedoor",
    )
    yield g
    g.conn.close()


def audit(g: OneDoorGuardrail, kind: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM actions_audit"
    params: tuple[Any, ...] = ()
    if kind is not None:
        sql += " WHERE kind=?"
        params = (kind,)
    return list(g.conn.execute(sql + " ORDER BY id", params))


def call(model: str = "gpt-4o-mini", call_id: str = "call-1") -> dict[str, Any]:
    return {"model": model, "litellm_call_id": call_id}


async def test_pre_call_hook_reports_nothing_before_the_act(guardrail: OneDoorGuardrail) -> None:
    """THE regression test for ND-021: a permit is not a result."""
    data = call()
    await guardrail.async_pre_call_hook(None, None, data, "completion")

    kinds = [r["kind"] for r in audit(guardrail)]
    assert "exec_intent" in kinds, "the intent must be durable before the gateway acts"
    assert "exec_result" not in kinds, (
        "the pre-call hook reported an outcome before the gateway had done anything "
        "-- this is the two-phase contract violation ND-021 exists to fix"
    )


async def test_success_hook_reports_exactly_one_result_linked_to_the_intent(
    guardrail: OneDoorGuardrail,
) -> None:
    data = call()
    await guardrail.async_pre_call_hook(None, None, data, "completion")
    intent = audit(guardrail, "exec_intent")[0]

    await guardrail.async_post_call_success_hook(data, None, FakeResponse())

    results = audit(guardrail, "exec_result")
    assert len(results) == 1
    assert results[0]["parent_id"] == intent["id"]
    assert results[0]["connector_ok"] == 1
    assert "gpt-4o-mini" in results[0]["payload_json"]
    assert "42" in results[0]["payload_json"], "real outcome data, not a placeholder"


async def test_failure_hook_reports_the_failure_and_the_error(
    guardrail: OneDoorGuardrail,
) -> None:
    data = call()
    await guardrail.async_pre_call_hook(None, None, data, "completion")

    await guardrail.async_post_call_failure_hook(data, RuntimeError("upstream 503"), None)

    results = audit(guardrail, "exec_result")
    assert len(results) == 1
    assert results[0]["connector_ok"] == 0
    assert "upstream 503" in results[0]["error"]


async def test_a_permit_is_reported_at_most_once(guardrail: OneDoorGuardrail) -> None:
    """Popping the pending map is what makes 'exactly once' true."""
    data = call()
    await guardrail.async_pre_call_hook(None, None, data, "completion")
    await guardrail.async_post_call_success_hook(data, None, FakeResponse())
    await guardrail.async_post_call_success_hook(data, None, FakeResponse())
    await guardrail.async_post_call_failure_hook(data, RuntimeError("late"), None)

    assert len(audit(guardrail, "exec_result")) == 1


async def test_interleaved_calls_report_against_their_own_permits(
    guardrail: OneDoorGuardrail,
) -> None:
    """Concurrency: no 'last intent' global would survive this."""
    first = call(call_id="call-a")
    second = call(call_id="call-b")

    await guardrail.async_pre_call_hook(None, None, first, "completion")
    await guardrail.async_pre_call_hook(None, None, second, "completion")
    # second finishes first, and fails; first then succeeds
    await guardrail.async_post_call_failure_hook(second, RuntimeError("b failed"), None)
    await guardrail.async_post_call_success_hook(first, None, FakeResponse())

    intents = audit(guardrail, "exec_intent")
    results = audit(guardrail, "exec_result")
    assert len(intents) == 2 and len(results) == 2

    by_parent = {r["parent_id"]: r for r in results}
    assert by_parent[intents[0]["id"]]["connector_ok"] == 1, "call-a succeeded"
    assert by_parent[intents[1]["id"]]["connector_ok"] == 0, "call-b failed"
    assert "b failed" in by_parent[intents[1]["id"]]["error"]


@pytest.mark.parametrize(
    ("call_type", "data", "why"),
    [
        ("completion", {"model": "gpt-4o-experimental"}, "model outside the enum: denied"),
        (
            "call_mcp_tool",
            {"name": "send_payment", "arguments": {"payee": "shop", "amount_eur": 10}},
            "tier 3: proposed, awaiting a human",
        ),
        ("call_mcp_tool", {"name": "delete_everything", "arguments": {}}, "unlisted: default-deny"),
    ],
)
async def test_refused_calls_raise_and_write_no_result(
    guardrail: OneDoorGuardrail, call_type: str, data: dict[str, Any], why: str
) -> None:
    payload = {**data, "litellm_call_id": "call-x"}
    with pytest.raises(OneDoorRejection):
        await guardrail.async_pre_call_hook(None, None, payload, call_type)

    assert audit(guardrail, "exec_result") == [], f"nothing executed, so nothing to report ({why})"
    assert guardrail._pending == {}, "a refused call must not leave a permit pending"


async def test_missing_call_id_refuses_before_any_permit_is_issued(
    guardrail: OneDoorGuardrail,
) -> None:
    """No correlation key means no way to report, so nothing is authorized.

    The ticket suggested falling back to `id(data)`. That is unsound here: the
    post-call hook receives a dict *derived* from the pre-call one, so object
    identity does not survive the round trip. Refusing before `decide_and_reserve`
    runs means no budget is reserved and no orphan permit exists to reclaim.
    """
    with pytest.raises(OneDoorRejection, match="litellm_call_id"):
        await guardrail.async_pre_call_hook(None, None, {"model": "gpt-4o-mini"}, "completion")

    assert audit(guardrail) == [], "refused before deciding, so the audit stays empty"


async def test_ungoverned_call_types_pass_through_untouched(
    guardrail: OneDoorGuardrail,
) -> None:
    data = {"litellm_call_id": "call-z"}
    assert await guardrail.async_pre_call_hook(None, None, data, "embeddings") is data
    assert audit(guardrail) == []
    # and a post-call hook for a call we never permitted must not invent a report
    await guardrail.async_post_call_success_hook(data, None, FakeResponse())
    assert audit(guardrail) == []
