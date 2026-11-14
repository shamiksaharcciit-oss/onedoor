"""An approved mapped-tool call is retried with the tool's own original argument
shape, not onedoor's mapped param names. `approved.params`
is the decision's own projection (`payee`, `amount_eur`); the downstream tool
never heard of those names and expects `to`, `amount.value`, and whatever else
the call carried that no mapping names at all (`memo`)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from onedoor.guardrail import approvals
from onedoor.mcp.proxy import Proxy
from onedoor.store.clock import now_utc
from onedoor.store.db import Database, tx

ROOT = Path(__file__).parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
DOWNSTREAM = f'"{sys.executable}" -m tests.mcp.fixtures.mismatched_demo_server'

CALL = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "wire_transfer",
        "arguments": {
            "to": "acme",
            "amount": {"value": 250.0, "currency": "EUR"},
            "memo": "invoice 42",
        },
    },
}


def _policies(tmp_path: Path) -> Path:
    path = tmp_path / "policies.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "policies": [
                    {
                        "action_type": "mcp.send_payment",
                        "tier": 3,
                        "dry_run": False,
                        "bounds": {
                            "strict_params": False,
                            "numeric": {"amount_eur": {"max": 1000}},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def _proxy(tmp_path: Path) -> Proxy:
    return Proxy(
        DOWNSTREAM,
        _policies(tmp_path),
        str(tmp_path / "proxy.db"),
        mapping=FIXTURES / "mismatched_mapping.yaml",
    )


def _serve(proxy: Proxy, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    lines = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    out = io.StringIO()
    proxy.serve(lines, out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def _with_ref(msg: dict[str, Any], approval_id: int) -> dict[str, Any]:
    retried = json.loads(json.dumps(msg))
    retried["params"]["_meta"] = {"onedoor/approval_ref": approval_id}
    return retried


def test_the_downstream_tool_receives_the_original_argument_shape_on_an_approved_retry(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "proxy.db"
    proxy = _proxy(tmp_path)
    resp = _serve(proxy, CALL)[0]
    assert "approval" in str(resp["result"]["content"][0]["text"])

    approval_id = int(
        proxy.conn.execute("SELECT id FROM approvals WHERE state='pending'").fetchone()[0]
    )
    operator = Database(str(db_path)).connect()
    with tx(operator) as conn:
        approvals.cas_approve(conn, approval_id, "operator", now_utc())

    resp = _serve(proxy, _with_ref(CALL, approval_id))[0]
    text = str(resp["result"]["content"][0]["text"])
    assert resp["result"]["isError"] is False, text

    received = json.loads(text.split("received_arguments=", 1)[1])
    assert received == {
        "to": "acme",
        "amount": {"value": 250.0, "currency": "EUR"},
        "memo": "invoice 42",
    }
