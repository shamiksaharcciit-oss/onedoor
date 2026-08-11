"""onedoor MCP proxy — the guardrail engine installed between an agent and its tools.

The proxy speaks MCP's stdio transport (newline-delimited JSON-RPC) on both
sides: an MCP host connects to the proxy as if it were the tool server; the
proxy spawns the real downstream server as a subprocess. Everything except
`tools/call` is forwarded verbatim. Every `tools/call` becomes an
`ActionRequest` (`mcp.<tool>`) and runs the full decision pipeline:

- permitted  -> forwarded downstream, result reported to the audit log (Tx B)
- denied     -> a tool error result naming the reason (bounds, caps, ...)
- proposed   -> a tool error result carrying the approval id; the call is
                waiting for a human (default-deny covers unknown tools)
- dry-run    -> a tool result saying "would have executed", nothing forwarded

Demo conveniences (clearly non-standard, prefixed `onedoor/`):
- `onedoor/approve` {"approval_id": N}  — approve + execute a pending proposal
- `onedoor/kill`    {"engaged": bool}   — flip the kill switch

The proxy is a Policy Enforcement Point: `decide_and_reserve` (Tx A) is the
judgment, the downstream forward is the act, `report_result` (Tx B) is the
receipt. One door — installed on someone else's doorway.

Run:
    python -m onedoor.mcp.proxy --downstream "python -m onedoor.mcp.demo_server" \
        --policies config/mcp_policies.yaml --db /tmp/onedoor-mcp.db
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from onedoor.guardrail import approvals, killswitch, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Decision, Source
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

ACTION_PREFIX = "mcp."


def _tool_error(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _tool_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


class Downstream:
    """The real MCP server, spawned and spoken to over pipes."""

    def __init__(self, cmd: str) -> None:
        self.proc = subprocess.Popen(
            shlex.split(cmd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def request(self, msg: dict[str, Any]) -> dict[str, Any]:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

    def notify(self, msg: dict[str, Any]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()


class Proxy:
    def __init__(self, downstream_cmd: str, policies: Path, db_path: str) -> None:
        self.down = Downstream(downstream_cmd)
        db = Database(db_path)
        db.init()
        self.conn: Connection = db.connect()
        policy_loader.load_file(self.conn, policies)
        self.config = EngineConfig(
            approval_ttl_seconds=3600,
            connector_timeout_seconds=15.0,
            tz=ZoneInfo("UTC"),
        )

    # --- the interception ---------------------------------------------------

    def _forward_and_report(
        self, msg: dict[str, Any], intent: PermittedIntent, now: datetime
    ) -> dict[str, Any]:
        try:
            resp = self.down.request(msg)
        except Exception as exc:  # downstream died mid-call
            report_result(
                intent, conn=self.conn, ok=False, payload=None, error=str(exc)[:200], now=now
            )
            raise
        result = resp.get("result", {})
        ok = not result.get("isError", False) and "error" not in resp
        payload = {"mcp_result": json.dumps(result)[:2000]}
        report_result(
            intent,
            conn=self.conn,
            ok=ok,
            payload=payload,
            error=None if ok else "downstream tool error",
            now=now,
        )
        return resp

    def handle_tools_call(self, msg: dict[str, Any]) -> dict[str, Any]:
        params = msg.get("params", {})
        tool = params.get("name", "")
        args = params.get("arguments", {}) or {}
        now = now_utc()
        request = ActionRequest(
            request_id=uuid4(),
            action_type=f"{ACTION_PREFIX}{tool}",
            params=args,
            source=Source.LLM,
            rationale=f"mcp tools/call {tool}",
            created_at=now,
        )
        outcome = decide_and_reserve(request, conn=self.conn, config=self.config, now=now)

        if isinstance(outcome, PermittedIntent):
            return self._forward_and_report(msg, outcome, now)

        d = outcome.decision
        if d.decision == Decision.PROPOSED:
            result = _tool_error(
                f"onedoor: '{tool}' requires approval "
                f"(tier 3, reason: {d.reason_code.value}; approval_id={outcome.approval_id}). "
                f"A human can release it; the call has not been forwarded."
            )
        elif d.decision == Decision.DRY_RUN:
            result = _tool_text(
                f"onedoor: '{tool}' is in dry-run — would have executed, nothing forwarded."
            )
        else:
            result = _tool_error(
                f"onedoor: '{tool}' denied (reason: {d.reason_code.value}"
                + (f" — {d.detail}" if d.detail else "")
                + "). The call was not forwarded."
            )
        return {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}

    # --- demo conveniences --------------------------------------------------

    def handle_approve(self, msg: dict[str, Any]) -> dict[str, Any]:
        approval_id = int(msg.get("params", {}).get("approval_id"))
        now = now_utc()
        approved_req = approvals.cas_approve(self.conn, approval_id, "mcp-proxy-demo", now)
        # Fresh request id: the approval resumes as a new pipeline entry, so the
        # idempotency guard doesn't return the original PROPOSED decision.
        approved_req = approved_req.model_copy(update={"request_id": uuid4(), "created_at": now})
        outcome = decide_and_reserve(
            approved_req, conn=self.conn, config=self.config, now=now, approved_override=True
        )
        if not isinstance(outcome, PermittedIntent):
            return {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": _tool_error(
                    f"onedoor: approved action did not execute "
                    f"(reason: {outcome.decision.reason_code.value})"
                ),
            }
        tool = approved_req.action_type.removeprefix(ACTION_PREFIX)
        forward = {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "method": "tools/call",
            "params": {"name": tool, "arguments": approved_req.params},
        }
        resp = self._forward_and_report(forward, outcome, now)
        approvals.mark_executed(self.conn, approval_id, outcome.intent_audit_id)
        return resp

    def handle_kill(self, msg: dict[str, Any]) -> dict[str, Any]:
        engaged = bool(msg.get("params", {}).get("engaged"))
        killswitch.set_engaged(self.conn, engaged, origin="mcp-proxy")
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "result": _tool_text(f"onedoor: kill switch {'ENGAGED' if engaged else 'released'}"),
        }

    # --- main loop ----------------------------------------------------------

    def serve(self, lines: Any, out: Any) -> None:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line)
            method = msg.get("method")
            if method == "tools/call":
                resp = self.handle_tools_call(msg)
            elif method == "onedoor/approve":
                resp = self.handle_approve(msg)
            elif method == "onedoor/kill":
                resp = self.handle_kill(msg)
            elif method and "id" not in msg:
                self.down.notify(msg)  # forward notifications
                continue
            else:
                resp = self.down.request(msg)  # initialize, tools/list, everything else
            out.write(json.dumps(resp) + "\n")
            out.flush()


def main() -> None:
    ap = argparse.ArgumentParser(description="onedoor MCP guardrail proxy")
    ap.add_argument("--downstream", required=True, help="command for the real MCP server")
    ap.add_argument("--policies", required=True, type=Path)
    ap.add_argument("--db", default="onedoor-mcp.db")
    args = ap.parse_args()
    Proxy(args.downstream, args.policies, args.db).serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
