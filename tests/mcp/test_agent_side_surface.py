"""The proxy's host side is the agent. Nothing the agent sends approves an action or
moves the kill switch: those are operator acts, taken outside the agent's channel.

Driven through `Proxy.serve`, the public surface, with the real demo downstream --
the way an MCP host would reach the proxy, including as a notification with no `id`.
"""

from __future__ import annotations

import io
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from onedoor.guardrail import approvals, killswitch
from onedoor.guardrail.errors import ApprovalError
from onedoor.mcp.proxy import PRINCIPAL as PROXY_PRINCIPAL
from onedoor.mcp.proxy import Proxy
from onedoor.store.clock import now_utc
from onedoor.store.db import Database, tx

ROOT = Path(__file__).parent.parent.parent

PAY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "send_payment", "arguments": {"payee": "webshop", "amount_eur": 49.99}},
}


def _proxy(db_path: Path) -> Proxy:
    return Proxy(
        f'"{sys.executable}" -m onedoor.mcp.demo_server',
        ROOT / "config" / "mcp_policies.yaml",
        str(db_path),
    )


def _serve(proxy: Proxy, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    lines = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    out = io.StringIO()
    proxy.serve(lines, out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def _text(response: dict[str, Any]) -> str:
    return str(response["result"]["content"][0]["text"])


def _operator(db_path: Path):  # type: ignore[no-untyped-def]
    """The operator's own connection to the store -- a channel the agent cannot reach."""
    return Database(str(db_path)).connect()


def _pending_approval(proxy: Proxy) -> int:
    return int(proxy.conn.execute("SELECT id FROM approvals WHERE state='pending'").fetchone()[0])


def test_the_agent_cannot_approve_its_own_proposal(tmp_path: Path) -> None:
    db_path = tmp_path / "proxy.db"
    proxy = _proxy(db_path)
    proposed = _serve(proxy, PAY)
    assert "requires approval" in _text(proposed[0])
    approval_id = _pending_approval(proxy)

    replies = _serve(
        proxy,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "onedoor/approve",
            "params": {"approval_id": approval_id},
        },
        {"jsonrpc": "2.0", "method": "onedoor/approve", "params": {"approval_id": approval_id}},
    )

    assert len(replies) == 1, "a notification gets no reply"
    assert "error" in replies[0] and "result" not in replies[0]
    state = proxy.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert state[0] == "pending"
    intents = proxy.conn.execute("SELECT COUNT(*) FROM actions_audit WHERE kind='exec_intent'")
    assert intents.fetchone()[0] == 0


def test_the_agent_cannot_release_the_kill_switch(tmp_path: Path) -> None:
    db_path = tmp_path / "proxy.db"
    proxy = _proxy(db_path)
    operator = _operator(db_path)
    with tx(operator):
        killswitch.set_engaged(operator, True, origin="operator")

    replies = _serve(
        proxy,
        {"jsonrpc": "2.0", "id": 2, "method": "onedoor/kill", "params": {"engaged": False}},
        {"jsonrpc": "2.0", "method": "onedoor/kill", "params": {}},
    )

    assert len(replies) == 1, "a notification gets no reply"
    assert "error" in replies[0] and "result" not in replies[0]
    assert killswitch.is_engaged(operator) is True


@pytest.mark.parametrize(
    "method", ["onedoor/approve", "onedoor/kill", "onedoor/deny", "onedoor/anything"]
)
def test_every_onedoor_method_is_refused_by_the_proxy_itself(tmp_path: Path, method: str) -> None:
    """Refused by the proxy, in its own words -- not handled, and not forwarded to the
    downstream server, which would answer an unknown method in words of its own."""
    proxy = _proxy(tmp_path / "proxy.db")
    replies = _serve(proxy, {"jsonrpc": "2.0", "id": 7, "method": method, "params": {}})

    assert replies[0]["id"] == 7
    assert replies[0]["error"]["code"] == -32601
    assert "operator" in replies[0]["error"]["message"]


def test_an_operator_approval_releases_the_call_when_the_agent_presents_it(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "proxy.db"
    proxy = _proxy(db_path)
    _serve(proxy, PAY)
    approval_id = _pending_approval(proxy)
    operator = _operator(db_path)
    with tx(operator):
        approvals.cas_approve(operator, approval_id, "operator", now_utc())

    retried = json.loads(json.dumps(PAY))
    retried["id"] = 3
    retried["params"]["_meta"] = {"onedoor/approval_ref": approval_id}
    replies = _serve(proxy, retried)

    assert replies[0]["result"]["isError"] is False
    assert "Sent €49.99 to webshop" in _text(replies[0])
    state = proxy.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert state[0] not in ("pending", "approved")


def test_the_proxy_cannot_approve_what_it_proposed_even_through_the_store(
    tmp_path: Path,
) -> None:
    """The rule lives in the engine, so it holds for any caller that presents the
    proxy's identity -- not only for the methods the proxy no longer offers."""
    db_path = tmp_path / "proxy.db"
    proxy = _proxy(db_path)
    _serve(proxy, PAY)
    approval_id = _pending_approval(proxy)
    proposer = proxy.conn.execute(
        "SELECT proposed_by FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()[0]
    assert proposer

    operator = _operator(db_path)
    with pytest.raises(ApprovalError), tx(operator):
        approvals.cas_approve(operator, approval_id, proposer, now_utc())
    state = operator.execute("SELECT state FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert state[0] == "pending"


def test_a_presented_approval_is_consumed_even_when_the_retry_is_denied(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "proxy.db"
    proxy = _proxy(db_path)
    _serve(proxy, PAY)
    approval_id = _pending_approval(proxy)
    operator = _operator(db_path)
    with tx(operator):
        approvals.cas_approve(operator, approval_id, "operator", now_utc())
        killswitch.set_engaged(operator, True, origin="operator")

    retried = json.loads(json.dumps(PAY))
    retried["params"]["_meta"] = {"onedoor/approval_ref": approval_id}
    denied = _serve(proxy, retried)
    assert denied[0]["result"]["isError"] is True
    state = proxy.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,))
    assert state.fetchone()[0] == "consumed"

    with tx(operator):
        killswitch.set_engaged(operator, False, origin="operator")
    again = _serve(proxy, retried)
    assert "Sent" not in _text(again[0]), "a consumed approval releases nothing"


def _spy_downstream(proxy: Proxy) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Record every message the proxy sends to the downstream server."""
    forwarded: list[dict[str, Any]] = []
    notified: list[dict[str, Any]] = []
    real_request, real_notify = proxy.down.request, proxy.down.notify

    def request(msg: dict[str, Any]) -> dict[str, Any]:
        forwarded.append(msg)
        return real_request(msg)

    def notify(msg: dict[str, Any]) -> None:
        notified.append(msg)
        real_notify(msg)

    proxy.down.request = request  # type: ignore[method-assign]
    proxy.down.notify = notify  # type: ignore[method-assign]
    return forwarded, notified


def _with_ref(call: dict[str, Any], ref: object) -> dict[str, Any]:
    retried = json.loads(json.dumps(call))
    retried["params"]["_meta"] = {"onedoor/approval_ref": ref}
    return retried


def test_onedoor_notifications_are_not_forwarded(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    forwarded, notified = _spy_downstream(proxy)
    _serve(
        proxy,
        {"jsonrpc": "2.0", "method": "onedoor/kill", "params": {}},
        {"jsonrpc": "2.0", "method": "onedoor/approve", "params": {"approval_id": 1}},
    )
    assert forwarded == [] and notified == []


def test_the_proxy_records_its_own_principal_on_what_it_proposes(tmp_path: Path) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    _serve(proxy, PAY)
    recorded = proxy.conn.execute("SELECT proposed_by FROM approvals").fetchone()[0]
    assert recorded == PROXY_PRINCIPAL


def test_the_agent_cannot_release_its_own_pending_proposal_by_presenting_it(
    tmp_path: Path,
) -> None:
    """Presenting a reference nobody has approved releases nothing, and does not park
    a second approval for the same call: the agent is told the first is still waiting."""
    proxy = _proxy(tmp_path / "proxy.db")
    _serve(proxy, PAY)
    approval_id = _pending_approval(proxy)
    forwarded, _ = _spy_downstream(proxy)

    reply = _serve(proxy, _with_ref(PAY, approval_id))

    assert reply[0]["result"]["isError"] is True
    assert "still waiting" in _text(reply[0])
    assert [m for m in forwarded if m.get("method") == "tools/call"] == []
    assert proxy.conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1
    state = proxy.conn.execute("SELECT state FROM approvals WHERE id=?", (approval_id,))
    assert state.fetchone()[0] == "pending"


def test_a_released_call_forwards_the_approved_arguments_not_the_retry(tmp_path: Path) -> None:
    """What reaches the tool is what the operator approved. A retry whose arguments
    merely compare equal after canonicalization does not substitute its own bytes."""
    db_path = tmp_path / "proxy.db"
    proxy = _proxy(db_path)
    _serve(proxy, PAY)
    approval_id = _pending_approval(proxy)
    with tx(_operator(db_path)) as operator:
        approvals.cas_approve(operator, approval_id, "operator", now_utc())
    forwarded, _ = _spy_downstream(proxy)

    retry = _with_ref(PAY, approval_id)
    line = json.dumps(retry).replace("49.99", "49.990000000000000000000000000001")
    out = io.StringIO()
    proxy.serve(io.StringIO(line + "\n"), out)

    calls = [m for m in forwarded if m.get("method") == "tools/call"]
    assert len(calls) == 1
    assert calls[0]["params"]["arguments"]["amount_eur"] == Decimal("49.99")


def test_a_released_call_is_linked_to_its_approval_and_proposal(tmp_path: Path) -> None:
    db_path = tmp_path / "proxy.db"
    proxy = _proxy(db_path)
    _serve(proxy, PAY)
    approval_id = _pending_approval(proxy)
    proposal = proxy.conn.execute(
        "SELECT id FROM actions_audit WHERE approval_id=? AND kind='decision'", (approval_id,)
    ).fetchone()[0]
    with tx(_operator(db_path)) as operator:
        approvals.cas_approve(operator, approval_id, "operator", now_utc())
    _serve(proxy, _with_ref(PAY, approval_id))

    intent = proxy.conn.execute(
        "SELECT id, resumes_audit_id FROM actions_audit WHERE kind='exec_intent'"
    ).fetchone()
    assert intent["resumes_audit_id"] == proposal
    linked = proxy.conn.execute(
        "SELECT resulting_audit_id FROM approvals WHERE id=?", (approval_id,)
    ).fetchone()[0]
    assert linked == intent["id"]


@pytest.mark.parametrize("ref", [2**63, -(2**63) - 1, 10**30])
def test_an_out_of_range_reference_is_evaluated_as_absent_and_the_proxy_keeps_serving(
    tmp_path: Path, ref: int
) -> None:
    proxy = _proxy(tmp_path / "proxy.db")
    weather = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_weather", "arguments": {"city": "Amsterdam"}},
    }
    replies = _serve(proxy, _with_ref(weather, ref), {**weather, "id": 2})
    assert [r["id"] for r in replies] == [1, 2]
    assert all("Amsterdam" in _text(r) for r in replies)
