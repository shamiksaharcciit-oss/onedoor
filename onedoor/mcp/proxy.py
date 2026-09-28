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
import os
import shlex
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from onedoor.guardrail import approvals, killswitch, policy_loader
from onedoor.guardrail.audit import dumps_json_value
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Decision,
    DecisionRef,
    JsonValue,
    Outcome,
    Source,
)
from onedoor.guardrail.received import extract_raw_member
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

ACTION_PREFIX = "mcp."


def _tool_error(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _tool_text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def split_command(cmd: str, *, windows: bool | None = None) -> list[str] | str:
    """Turn a command line into whatever Popen wants on this platform.

    ``shlex.split`` is POSIX by default, which treats a backslash as an escape
    character -- so a Windows path like ``C:\\Python\\python.exe`` is silently
    mangled into ``C:Pythonpython.exe`` and the spawn fails with "file not
    found". On Windows, hand the raw string to Popen and let CreateProcess do
    the parsing it defines.
    """
    if windows is None:
        windows = os.name == "nt"
    return cmd if windows else shlex.split(cmd)


class Downstream:
    """The real MCP server, spawned and spoken to over pipes."""

    def __init__(self, cmd: str) -> None:
        self.proc = subprocess.Popen(
            split_command(cmd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def request(self, msg: dict[str, Any]) -> dict[str, Any]:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(dumps_json_value(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        parsed: dict[str, Any] = json.loads(line, parse_float=Decimal)
        return parsed

    def notify(self, msg: dict[str, Any]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(dumps_json_value(msg) + "\n")
        self.proc.stdin.flush()


class Proxy:
    def __init__(
        self, downstream_cmd: str, policies: Path, db_path: str, *, issuer: str | None = None
    ) -> None:
        self.down = Downstream(downstream_cmd)
        db = Database(db_path)
        db.init()
        self.conn: Connection = db.connect()
        policy_loader.load_file(self.conn, policies)
        self.config = EngineConfig(
            approval_ttl_seconds=3600,
            connector_timeout_seconds=15.0,
            tz=ZoneInfo("UTC"),
            issuer=issuer,
        )
        self.last_decision_ref: DecisionRef | None = None
        """The reference to the most recent decision this proxy acted on --
        `None` before any call, or if no `issuer` was configured. The
        documented hook by which whatever wraps this proxy (a onetrace stage
        around its stdio process, a test harness) reads the reference: this
        proxy speaks MCP's own wire format on both sides and does not own the
        shape of what it forwards, so the reference cannot be embedded in a
        downstream tool's own JSON-RPC response without conflating two
        different messages' content.

        Safe under concurrent calls because there is no such thing here: this
        one mutable attribute, with no lock, would be unsafe if two calls
        could be in flight together, but `serve` below handles exactly one
        call at a time -- a plain synchronous loop over one stdin stream,
        where deciding, forwarding to the downstream subprocess, reporting
        the outcome, and writing the response all block the same thread in
        order before the next line is even read. Nothing in this module
        imports threading or asyncio. A caller that needs the reference must
        still read it before starting its NEXT call through this same proxy,
        same as it must already do to read the ordinary MCP response for the
        one it just made."""

    # --- the interception ---------------------------------------------------

    def _forward_and_report(
        self, msg: dict[str, Any], intent: PermittedIntent, now: datetime
    ) -> dict[str, Any]:
        try:
            resp = self.down.request(msg)
        except Exception as exc:  # downstream died mid-call
            report_result(
                intent,
                conn=self.conn,
                # The downstream died mid-call: attempted, did not succeed.
                outcome=Outcome.FAILURE,
                payload=None,
                error=str(exc)[:200],
                now=now,
            )
            raise
        result = resp.get("result", {})
        ok = not result.get("isError", False) and "error" not in resp
        payload: dict[str, JsonValue] = {"mcp_result": dumps_json_value(result)[:2000]}
        report_result(
            intent,
            conn=self.conn,
            outcome=Outcome.SUCCESS if ok else Outcome.FAILURE,
            payload=payload,
            error=None if ok else "downstream tool error",
            now=now,
        )
        return resp

    def handle_tools_call(self, msg: dict[str, Any], raw_line: str | None = None) -> dict[str, Any]:
        params = msg.get("params", {})
        tool = params.get("name", "")
        args = params.get("arguments", {}) or {}
        now = now_utc()
        # Freeze the arguments exactly as the host sent them (E10). They sit at
        # params.arguments, so the extractor composes: the top-level member first,
        # then the member inside it. If either step cannot be done exactly, the
        # result is None and the row records `serialized` rather than claiming
        # bytes it does not have.
        raw_args = None
        if raw_line is not None:
            outer = extract_raw_member(raw_line, "params")
            raw_args = extract_raw_member(outer, "arguments") if outer else None
        request = ActionRequest(
            request_id=uuid4(),
            action_type=f"{ACTION_PREFIX}{tool}",
            params=args,
            params_raw=raw_args,
            source=Source.LLM,
            rationale=f"mcp tools/call {tool}",
            created_at=now,
        )
        outcome = decide_and_reserve(request, conn=self.conn, config=self.config, now=now)
        self.last_decision_ref = outcome.decision_ref

        if isinstance(outcome, PermittedIntent):
            if outcome.present_bound is not None:
                # AADP -03 §6's fail-closed rule: this proxy forwards
                # to the downstream tool directly -- it does not implement audience
                # presentation -- so a permit bound to an audience must be refused
                # rather than forwarded, and reported not_attempted.
                report_result(
                    outcome,
                    conn=self.conn,
                    outcome=Outcome.NOT_ATTEMPTED,
                    payload=None,
                    error=(
                        f"permit is bound to audience {outcome.present_bound!r}; this "
                        f"proxy does not implement presentation and refuses to forward"
                    ),
                    now=now,
                )
                result = _tool_error(
                    f"onedoor: '{tool}' is bound to audience {outcome.present_bound!r} "
                    f"and cannot be forwarded by this proxy; not attempted."
                )
                return {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
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
        proposal_audit_id = approvals.proposed_audit_id(self.conn, approval_id)
        # Fresh request id: the approval resumes as a new pipeline entry, so the
        # idempotency guard doesn't return the original PROPOSED decision.
        approved_req = approved_req.model_copy(update={"request_id": uuid4(), "created_at": now})
        outcome = decide_and_reserve(
            approved_req,
            conn=self.conn,
            config=self.config,
            now=now,
            approved_override=True,
            resumes_audit_id=proposal_audit_id,
        )
        self.last_decision_ref = outcome.decision_ref
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
        report = killswitch.set_engaged(self.conn, engaged, origin="mcp-proxy")
        text = f"onedoor: kill switch {'ENGAGED' if engaged else 'released'}"
        if report is not None and report.state != killswitch.UNCHANGED:
            # The lift is the loud moment, and it is loud in every surface that
            # can lift -- an operator who releases through the proxy learns the same
            # thing as one who releases through the API.
            text = f"{text}. {report.sentence()}"
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "result": _tool_text(text),
        }

    # --- main loop ----------------------------------------------------------

    def serve(self, lines: Any, out: Any) -> None:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line, parse_float=Decimal)
            method = msg.get("method")
            if method == "tools/call":
                resp = self.handle_tools_call(msg, raw_line=line)
            elif method == "onedoor/approve":
                resp = self.handle_approve(msg)
            elif method == "onedoor/kill":
                resp = self.handle_kill(msg)
            elif method and "id" not in msg:
                self.down.notify(msg)  # forward notifications
                continue
            else:
                resp = self.down.request(msg)  # initialize, tools/list, everything else
            out.write(dumps_json_value(resp) + "\n")
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
