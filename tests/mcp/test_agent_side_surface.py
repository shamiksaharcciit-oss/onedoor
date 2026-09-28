"""The proxy's host side is the agent. Nothing the agent sends approves an action or
moves the kill switch: those are operator acts, taken outside the agent's channel.

Driven through `Proxy.serve`, the public surface, with the real demo downstream --
the way an MCP host would reach the proxy, including as a notification with no `id`.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from onedoor.guardrail import approvals, killswitch
from onedoor.guardrail.errors import ApprovalError
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
