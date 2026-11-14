"""onedoor MCP proxy — the guardrail engine installed between an agent and its tools.

The proxy speaks MCP's stdio transport (newline-delimited JSON-RPC) on both
sides: an MCP host connects to the proxy as if it were the tool server; the
proxy spawns the real downstream server as a subprocess. Everything except
`tools/call` and `onedoor/*` is forwarded verbatim. Every `tools/call` becomes an
`ActionRequest` (`mcp.<tool>`) and runs the full decision pipeline:

- permitted  -> forwarded downstream, result reported to the audit log (Tx B)
- denied     -> a tool error result naming the reason (bounds, caps, ...)
- proposed   -> a tool error result carrying the approval id; the call is
                waiting for a human (unknown tools are denied, not proposed)
- dry-run    -> a tool result saying "would have executed", nothing forwarded

The host side of this proxy is the agent, so no operator act is reachable from it.
An operator approves a parked call on their own connection to the proxy's store
(`approvals.cas_approve`); the kill switch is operated there too, or through the
decision service's admin route when it shares the store. Every `onedoor/*` method
an agent sends is refused by the proxy itself, as a request or as a notification,
and never forwarded.

An approved call is released when the agent sends it again with the approval
reference in the request's `_meta`: `{"onedoor/approval_ref": N}`. When the
reference names an approved call equivalent to this one, the proxy evaluates and
forwards the arguments the operator approved -- never the retry's own bytes. The
engine honours the reference once, and the store has refused any approval by this
proxy's own identity. A reference to a call still waiting for approval is answered
as such and parks nothing new; any other reference evaluates as if it were absent.

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
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from onedoor.guardrail import approval_ref as approval_ref_mod
from onedoor.guardrail import approvals, policy_loader
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
from onedoor.mcp.mapping import (
    Mapping,
    ToolMapping,
    apply_mapping,
    load_mapping,
    resolve_untrusted_paths,
)
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

ACTION_PREFIX = "mcp."
PRINCIPAL = "mcp-proxy"
"""Who this proxy is when it asks. Recorded on every approval it proposes, so the
store refuses an approval made under this identity."""
OPERATOR_METHOD_PREFIX = "onedoor/"
APPROVAL_REF_META = "onedoor/approval_ref"
PRESENTED_AUDIENCE_META = "onedoor/presented_audience"
UNTRUSTED_META = "onedoor/untrusted"
SESSION_META = "onedoor/session_id"
"""Same field as `ActionRequest.session_id` (onedoor 0.11) --
an MCP host's own conversation id, most naturally. Absent means no sequence
tracking for that call, the same opt-in default as every other feature here.
Overridden by the gateway's own per-connection assignment when the mapping
file sets `session: per_connection` -- see `Proxy._resolve_session_id`."""
PLAN_REF_META = "onedoor/plan_ref"
"""Same field as `ActionRequest.plan_ref` (onedoor 0.11),
the same shape `onedoor/approval_ref` already has. Absent, invalid, expired,
exhausted or mismatched all evaluate as absent."""
"""The caller marks a path in the TOOL's own argument shape (e.g.
`"arguments.to"`), never in onedoor's own `params` shape -- the proxy resolves
each one to the onedoor param name the mapping already maps that same path
onto (the mapping's own `{onedoor_name: path}` table, read in reverse) before
building the `ActionRequest`. A marked path absent from the mapping (an
unmapped tool, or a tool argument the mapping does not name) is inert, the
same way an unrecognised policy path already is -- nothing to translate it
onto."""
"""Same declaration the HTTP service's `DecideBody.presented_audience` accepts
from its own caller -- a caller that knows which audience it will present a
bound permit to may declare it here, the same way. It does not make this
proxy able to forward an audience-bound permit itself (AADP -03 section 6: a
PEP that does not implement presentation MUST refuse to exercise it, which is
exactly what forwarding straight to a downstream tool would be) -- it only
lets the engine's own `present_bound` match succeed, so the refusal that
follows reports the real, specific reason instead of a request that could
never have matched in the first place."""
_STORE_INTEGERS = range(-(2**63), 2**63)


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
        self,
        downstream_cmd: str,
        policies: Path,
        db_path: str,
        *,
        issuer: str | None = None,
        mapping: Path | None = None,
    ) -> None:
        self.down = Downstream(downstream_cmd)
        db = Database(db_path)
        db.init()
        self.conn: Connection = db.connect(check_same_thread=False)
        self.lock = threading.Lock()
        """Serializes every call into this proxy's own store, the same pattern
        `onedoor.service.app` uses: `check_same_thread=False` alone only lifts
        sqlite3's same-thread check, it does not make concurrent access safe.
        The stdio transport is already single-threaded by construction (one
        line read at a time) and never contends; the streamable-HTTP transport
        can receive genuinely concurrent requests, and this lock is what makes
        that safe rather than merely silent about the risk."""
        policy_loader.load_file(self.conn, policies)
        self.mapping: Mapping | None = load_mapping(mapping) if mapping is not None else None
        """Tool-to-action mapping. `None` is the 0.10.x behaviour:
        every tool is implicitly mapped to `mcp.<tool>`, params passed through
        verbatim. When set, a tool absent from it is denied before any decision is
        made -- a gateway-level guarantee, not contingent on how any policy reads."""
        self._stdio_session_id: str | None = (
            str(uuid4())
            if self.mapping is not None and self.mapping.session == "per_connection"
            else None
        )
        """One `Proxy` instance IS one stdio connection, by construction (it owns
        one downstream subprocess and reads one line at a time) -- so `session:
        per_connection` over stdio is simply this instance's own lifetime, fixed
        once here rather than recomputed per call. `None` when the mapping does
        not ask for it, or there is no mapping at all."""
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

        self.last_bound_permit: str | None = None
        """The most recent decision's bound permit (compact JWS), iff the policy
        issued one -- `None` before any call, if the action was proposed/denied
        rather than permitted, or if the policy declares no bound-permit action
        type. Same hook, same concurrency argument as `last_decision_ref` above;
        read together, since both describe the one decision `last_decision_ref`
        already names."""

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

    def _resolve_session_id(self, meta: object, *, http_session_id: str | None) -> str | None:
        """Onedoor 0.11. The gateway's own assignment, when
        the mapping asks for `session: per_connection`, takes priority over a
        caller-supplied `_meta["onedoor/session_id"]` -- that is the whole
        point of not depending on a `_meta` value a host may not send: a
        caller that happens to send one anyway should not silently fragment
        the one session the gateway already guarantees. Falls back to the
        caller's own declaration only when the gateway assigns nothing (no
        mapping, `session: none`, or HTTP with no token configured -- nothing
        stable to key on over that transport without one)."""
        if self._stdio_session_id is not None:
            return self._stdio_session_id
        if http_session_id is not None:
            return http_session_id
        declared = meta.get(SESSION_META) if isinstance(meta, dict) else None
        return declared if isinstance(declared, str) else None

    def handle_tools_call(
        self,
        msg: dict[str, Any],
        raw_line: str | None = None,
        *,
        http_session_id: str | None = None,
    ) -> dict[str, Any]:
        params = msg.get("params", {})
        if not isinstance(params, dict):
            return {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32602, "message": "invalid params: not a JSON object"},
            }
        tool = params.get("name", "")
        if not isinstance(tool, str):
            # A non-string "name" is unhashable against the mapping's own
            # dict lookup (a list, a dict) or simply the wrong shape (a
            # number, null) -- refused by name here rather than raising
            # from inside whatever happens to read it next.
            return {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32602, "message": 'invalid params: "name" must be a string'},
            }
        args = params.get("arguments", {}) or {}

        unmapped = False
        mapped_entry: ToolMapping | None = None
        if self.mapping is not None:
            entry = self.mapping.tools.get(tool)
            mapped_entry = entry
            if entry is None:
                # Namespaced so it can never collide with a real mapped action type,
                # and so no policy anyone writes for a real action accidentally
                # covers it. Still routed through the ordinary decision pipeline
                # below -- this stays audited, exactly like any other action onedoor
                # ever decides, rather than a silent short-circuit before the audit
                # log even opens. `unmapped` is checked again after the decision
                # (never-forward is a gateway guarantee, not contingent on how any
                # policy happens to read).
                unmapped = True
                action_type = f"mcp.unmapped.{tool}"
                resolved_params = dict(args)
                rationale = f"mcp tools/call {tool} (not in the gateway's mapping)"
                raw_args = None
            else:
                action_type = entry.action_type
                resolved_params = apply_mapping(entry, args)
                rationale = f"mcp tools/call {tool} (effect: {entry.effect})"
                # A mapped call's `params` is a PROJECTION of the tool's own arguments,
                # not the bytes the host sent -- claiming verbatim-received bytes for a
                # computed dict would be exactly the "PDP serialization wearing the
                # label 'received'" `ActionRequest.params_raw`'s own docstring warns
                # against. Left None; the audit row serialises the resolved params
                # instead, honestly marked as not an ingress-received value.
                raw_args = None
        else:
            action_type = f"{ACTION_PREFIX}{tool}"
            resolved_params = args
            rationale = f"mcp tools/call {tool}"
            # Freeze the arguments exactly as the host sent them (E10). They sit at
            # params.arguments, so the extractor composes: the top-level member first,
            # then the member inside it. If either step cannot be done exactly, the
            # result is None and the row records `serialized` rather than claiming
            # bytes it does not have.
            raw_args = None
            if raw_line is not None:
                outer = extract_raw_member(raw_line, "params")
                raw_args = extract_raw_member(outer, "arguments") if outer else None

        meta = params.get("_meta") or {}
        ref = meta.get(APPROVAL_REF_META) if isinstance(meta, dict) else None
        # Only a plain integer the store can hold is a reference; anything else
        # evaluates as absent, exactly as an invalid reference does inside the engine.
        is_int = isinstance(ref, int) and not isinstance(ref, bool)
        approval_ref = ref if is_int and ref in _STORE_INTEGERS else None
        if unmapped and approval_ref is not None:
            # `mcp.unmapped.<tool>` is always refused, never forwarded -- so a
            # presented ref must never be resolved for it either.
            # `approval_ref.resolve` consumes a matching ref the moment it finds
            # one (CAS, before this request's own verdict is known), so merely
            # calling `decide_and_reserve` with it set would burn a human's
            # granted approval on a call that then never executes. Cleared here,
            # before it is used for anything, so an unmapped tool can never
            # consume an approval regardless of what any policy later decides.
            approval_ref = None
        plan_ref_raw = meta.get(PLAN_REF_META) if isinstance(meta, dict) else None
        is_plan_int = isinstance(plan_ref_raw, int) and not isinstance(plan_ref_raw, bool)
        plan_ref = plan_ref_raw if is_plan_int and plan_ref_raw in _STORE_INTEGERS else None
        audience = meta.get(PRESENTED_AUDIENCE_META) if isinstance(meta, dict) else None
        presented_audience = audience if isinstance(audience, str) else None
        marked = meta.get(UNTRUSTED_META) if isinstance(meta, dict) else None
        if marked is not None and (
            not isinstance(marked, list) or not all(isinstance(p, str) for p in marked)
        ):
            # A malformed mark is refused outright, never silently dropped --
            # dropping it would make a caller's own marks inert exactly when
            # they are malformed, the opposite of fail-closed.
            return {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {
                    "code": -32602,
                    "message": (
                        f"onedoor: {UNTRUSTED_META!r} must be a list of strings; got {marked!r}"
                    ),
                },
            }
        marked_paths: list[str] = marked if marked is not None else []
        if mapped_entry is not None:
            untrusted = resolve_untrusted_paths(mapped_entry, marked_paths)
        elif self.mapping is None:
            # No mapping file at all (0.10's own default): params ARE the
            # tool's own arguments, verbatim, so a mark on "arguments.<path>"
            # applies to <path> directly -- there is no mapping table to
            # resolve it through, and none is needed.
            untrusted = [
                p[len("arguments.") :] if p.startswith("arguments.") else p for p in marked_paths
            ]
        else:
            # A configured mapping, but this tool is unmapped: refused as
            # mcp.unmapped.<tool> regardless, so a mark here is inert either way.
            untrusted = []
        session_id = self._resolve_session_id(meta, http_session_id=http_session_id)
        now = now_utc()
        request = ActionRequest(
            request_id=uuid4(),
            action_type=action_type,
            params=resolved_params,
            params_raw=raw_args,
            forward_arguments=args,
            untrusted=untrusted,
            session_id=session_id,
            source=Source.LLM,
            rationale=rationale,
            approval_ref=approval_ref,
            presented_audience=presented_audience,
            plan_ref=plan_ref,
            created_at=now,
        )
        forward = msg
        if approval_ref is not None:
            presented = self._presented_approval(approval_ref, request)
            if presented is not None:
                state, proposed_by, approved = presented
                if state == "pending" and proposed_by == PRINCIPAL:
                    result = _tool_error(
                        f"onedoor: '{tool}' is still waiting for approval {approval_ref}, "
                        f"which has not been given yet; the call has not been forwarded."
                    )
                    return {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
                if state == "approved":
                    # Evaluate and forward what the operator approved, not the retry.
                    request = request.model_copy(
                        update={"params": approved.params, "params_raw": approved.params_raw}
                    )
                    # The tool's own original argument shape, as first proposed --
                    # never the mapped decision params (`approved.params`), which can
                    # drop or rename arguments a mapping doesn't carry. Falls back to
                    # `approved.params` only for an approval proposed before this field
                    # existed.
                    forward_args = (
                        approved.forward_arguments
                        if approved.forward_arguments is not None
                        else approved.params
                    )
                    forward = {
                        "jsonrpc": "2.0",
                        "id": msg.get("id"),
                        "method": "tools/call",
                        "params": {"name": tool, "arguments": forward_args},
                    }
        outcome = decide_and_reserve(
            request, conn=self.conn, config=self.config, now=now, principal=PRINCIPAL
        )
        self.last_decision_ref = outcome.decision_ref
        self.last_bound_permit = (
            outcome.bound_permit if isinstance(outcome, PermittedIntent) else None
        )

        if isinstance(outcome, PermittedIntent):
            if unmapped:
                # Belt and suspenders: `mcp.unmapped.<tool>` should never match a
                # policy rule, so this should be unreachable -- but "never
                # forwarded" is the gateway's own guarantee, not one that should
                # depend on nobody ever writing a wildcard rule that happens to
                # catch it. Refused here regardless of what the engine decided.
                report_result(
                    outcome,
                    conn=self.conn,
                    outcome=Outcome.NOT_ATTEMPTED,
                    payload=None,
                    error="tool is not in the gateway's mapping; refused to forward",
                    now=now,
                )
                result = _tool_error(f"onedoor: '{tool}' refused: not in the gateway's mapping.")
                return {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
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
            return self._forward_and_report(forward, outcome, now)

        d = outcome.decision
        if unmapped:
            # The same guarantee the `PermittedIntent` branch above already
            # enforces, extended to every decision kind -- `mcp.unmapped.<tool>`
            # should never match a policy rule at all, but if one somehow does
            # (a policy literally naming that exact synthesized action type),
            # the caller-facing answer must still never say "would have
            # executed" or "requires approval", and the call must never be
            # forwarded, whatever the engine decided.
            result = _tool_error(f"onedoor: '{tool}' refused: not in the gateway's mapping.")
            return {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
        if d.decision == Decision.EXECUTED:
            # A tier-0 OBSERVE read (CONFORMANCE.md step 5): "audited and
            # returned, never a proposal or a reservation" -- there is no
            # intent to settle, so this forwards and returns the downstream's
            # own result directly, with no `report_result` call at all (the
            # one-shot audit row above is already the complete record). A
            # pre-existing gap, found by this round's own test for a tier-0
            # read through the gateway -- no earlier test routed one this far
            # (every demo policy that reached here before was tier 1 or
            # above, going through `PermittedIntent` instead); every such
            # call was previously misreported as a generic denial.
            return self.down.request(forward)
        if d.decision == Decision.PROPOSED:
            result = _tool_error(
                f"onedoor: '{tool}' requires approval "
                f"(tier 3, reason: {d.reason_code.value}; approval_id={outcome.approval_id}). "
                f"The call has not been forwarded. Once an operator approves it, send it "
                f'again with _meta {{"{APPROVAL_REF_META}": {outcome.approval_id}}}.'
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

    def _presented_approval(
        self, approval_id: int, presented: ActionRequest
    ) -> tuple[str, str | None, ActionRequest] | None:
        """(state, proposer, approved request) of the approval a retry presents, when
        that approval is for a call equivalent to this one; otherwise None."""
        row = self.conn.execute(
            "SELECT state, proposed_by, request_json FROM approvals WHERE id=?", (approval_id,)
        ).fetchone()
        if row is None:
            return None
        approved = approvals.loads_request(row["request_json"])
        if not approval_ref_mod.equivalent(approved, presented):
            return None
        return str(row["state"]), row["proposed_by"], approved

    # --- operator acts are not on this side --------------------------------

    @staticmethod
    def refuse_operator_method(msg: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "error": {
                "code": -32601,
                "message": (
                    f"onedoor: '{msg.get('method')}' is an operator act; it is not "
                    f"available on the agent side of this proxy"
                ),
            },
        }

    # --- main loop ----------------------------------------------------------

    def _handle_tools_list(self, msg: dict[str, Any]) -> dict[str, Any]:
        """`tools/list` passed through, optionally filtered to the mapping's own
        tool names -- never the engine's decision: an operator's own choice of
        what the gateway admits to having, set once in the mapping file."""
        resp = self.down.request(msg)
        if self.mapping is None or not self.mapping.tools_list_filter:
            return resp
        result = resp.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            return resp
        mapped_names = set(self.mapping.tools)
        filtered = [t for t in result["tools"] if t.get("name") in mapped_names]
        return {**resp, "result": {**result, "tools": filtered}}

    def handle_message(
        self,
        msg: Any,
        raw_line: str | None = None,
        *,
        http_session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """One JSON-RPC message in, at most one reply out -- `None` for a
        notification, which gets no reply on any transport. Transport-agnostic:
        stdio's `serve` and the streamable-HTTP transport both call this and
        differ only in how a message arrives and how a reply (or its absence)
        is written back.

        `msg` is `Any`, not `dict[str, Any]`: it is whatever `json.loads`
        parsed, and valid JSON need not be a JSON object (an array, a bare
        number or string, `null`...) -- refused below as its own JSON-RPC
        error, never trusted to be a dict just because a real request
        usually is one.

        `http_session_id` (onedoor 0.11): the streamable-HTTP
        transport's own resolution of `session: per_connection` -- a hash of
        the bearer token identifying the caller, computed there because only
        that transport knows the token at all. `None` on stdio, and on HTTP
        whenever no token is configured (nothing stable to key on over that
        transport without one -- the design note's own stated boundary).

        Held under `self.lock` for its whole body, not just the store: the one
        downstream subprocess pipe (`self.down`) is shared, mutable state too,
        and two threads writing a request to it at once would interleave their
        bytes on the wire -- the stdio transport never contends this because it
        is already one line at a time by construction; the HTTP transport can
        receive genuinely concurrent requests, where this is the only thing
        keeping one call's bytes from landing inside another's."""
        if not isinstance(msg, dict):
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "invalid request: not a JSON object"},
            }
        with self.lock:
            method = msg.get("method")
            if isinstance(method, str) and method.startswith(OPERATOR_METHOD_PREFIX):
                # Refused here whatever its form; a notification gets no reply at all.
                if "id" not in msg:
                    return None
                return self.refuse_operator_method(msg)
            if method == "tools/call":
                return self.handle_tools_call(
                    msg, raw_line=raw_line, http_session_id=http_session_id
                )
            if method and "id" not in msg:
                self.down.notify(msg)  # forward notifications
                return None
            if method == "tools/list":
                return self._handle_tools_list(msg)
            return self.down.request(msg)  # initialize, everything else

    def serve(self, lines: Any, out: Any) -> None:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            msg = json.loads(line, parse_float=Decimal)
            resp = self.handle_message(msg, raw_line=line)
            if resp is None:
                continue
            out.write(dumps_json_value(resp) + "\n")
            out.flush()


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="onedoor MCP guardrail proxy")
    ap.add_argument("--downstream", required=True, help="command for the real MCP server")
    ap.add_argument("--policies", required=True, type=Path)
    ap.add_argument("--db", default="onedoor-mcp.db")
    ap.add_argument("--mapping", type=Path, default=None, help="tool-to-action mapping file")
    ap.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="how the host reaches this gateway",
    )
    ap.add_argument(
        "--host", default="127.0.0.1", help="--transport http only; never beyond 127.0.0.1"
    )
    ap.add_argument("--port", type=int, default=8765, help="--transport http only")
    ap.add_argument(
        "--origin-allow",
        action="append",
        default=None,
        metavar="ORIGIN",
        help="--transport http only; repeatable. Empty by default -- any request carrying an "
        "Origin header is then refused outright, which is the safe default for a non-browser "
        "caller. Allowing one or more origins requires --token-file too.",
    )
    ap.add_argument(
        "--token-file",
        type=Path,
        default=None,
        help="--transport http only; a bearer token read from this file, required whenever "
        "--origin-allow names anything",
    )
    return ap


MIN_TOKEN_LENGTH = 16


def resolve_http_security(args: argparse.Namespace) -> tuple[frozenset[str], str | None]:
    """`--origin-allow`/`--token-file` validated: a non-empty allow-list without a
    token file is a configuration error, refused before anything binds a port.

    An empty or whitespace-only token file reads back as `""`, which is not `None` --
    `hmac.compare_digest("", "")` is true for a request carrying no `Authorization`
    header at all, so a blank file would silently turn the token check off rather
    than configure it. A short file is refused for the same reason a weak password
    would be: a token under `MIN_TOKEN_LENGTH` characters is cheap enough to guess
    that configuring it gives little real protection. Both are refused at start-up,
    naming the file, rather than accepted and failing open at request time."""
    origin_allow = frozenset(args.origin_allow or ())
    token = args.token_file.read_text(encoding="utf-8").strip() if args.token_file else None
    if args.token_file is not None and not token:
        raise SystemExit(f"--token-file {args.token_file}: the file is empty")
    if token is not None and len(token) < MIN_TOKEN_LENGTH:
        raise SystemExit(
            f"--token-file {args.token_file}: the token is shorter than "
            f"{MIN_TOKEN_LENGTH} characters"
        )
    if origin_allow and token is None:
        raise SystemExit("--origin-allow requires --token-file")
    return origin_allow, token


def main() -> None:
    args = build_arg_parser().parse_args()
    proxy = Proxy(args.downstream, args.policies, args.db, mapping=args.mapping)
    if args.transport == "stdio":
        proxy.serve(sys.stdin, sys.stdout)
    else:
        # Local import: http_transport imports Proxy from this module, so a
        # top-level import here would be circular.
        from onedoor.mcp.http_transport import run

        origin_allow, token = resolve_http_security(args)
        run(proxy, args.host, args.port, origin_allow=origin_allow, token=token)


if __name__ == "__main__":
    main()
