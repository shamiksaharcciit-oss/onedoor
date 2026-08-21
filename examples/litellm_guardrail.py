"""onedoor as a LiteLLM custom guardrail — EXPERIMENTAL EXAMPLE.

LiteLLM's proxy loads custom guardrails (subclasses of ``CustomGuardrail``)
and calls ``async_pre_call_hook`` before every call — including, notably,
``call_type="call_mcp_tool"`` for tool calls routed through LiteLLM's MCP
gateway. That hook is a natural Policy Enforcement Point: this adapter turns
each call into a onedoor ``ActionRequest`` and consults the decision engine.

What this adds over LiteLLM's built-in MCP permission ACLs (allowed/blocked
tools, allowed param *names*): value-level bounds (amount <= 500, model in an
allow-list), daily caps reserved race-free, default-deny for unlisted tools,
dry-run, a kill switch, tier-3 *defer* (the call is refused with an approval
id a human can release), and an append-only decision audit with reasons.

The two-phase contract, and why it needs two hooks
--------------------------------------------------
AADP splits authorization from execution: ``decide_and_reserve`` records the
*intent* and reserves budget, then the enforcement point acts, then
``report_result`` records what actually happened. The permit is a promise to
report, not a report.

So the pre-call hook decides and holds the permit; the post-call hooks report
the real outcome. Reporting success from the pre-call hook — which this example
did until ND-021 — asserts an action succeeded before the gateway has done
anything, which is the exact violation the standard exists to define.

Correlation between the hooks is by ``data["litellm_call_id"]``, which LiteLLM
sets on every governed request before guardrails run (verified against litellm
1.97.0: ``proxy/common_request_processing.py`` assigns it while building the
request, ahead of the pre-call hook dispatch, on the ``completion`` and
``call_mcp_tool`` paths alike). If it is ever absent the adapter **refuses the
call before deciding**, so no permit is issued that it could not report on.
Note it does not fall back to ``id(data)``: the post-call hook receives a dict
*derived* from the pre-call one, not the same object, so object identity does
not survive the round trip and a "last intent" global is simply wrong under
concurrency.

Example-grade simplifications, stated honestly:
- The engine is synchronous SQLite; a busy proxy should offload to a thread
  and use one guardrail instance per worker.
- **The pending-intent map is in process memory.** A gateway restart between
  the pre-call and post-call hooks strands the permit — the audit keeps the
  honest "intended, unconfirmed" row and the reservation reclaimer (0.3.4)
  releases its budget at the deadline. This is the same limitation the PDP
  service carries (``ND-010``), recorded rather than papered over.
- Approvals are released out-of-band (any process with the DB can call
  ``resume``-style logic); wiring a UI/webhook is the integrator's choice.

Proxy config sketch (config.yaml):
    guardrails:
      - guardrail_name: onedoor
        litellm_params:
          guardrail: examples.litellm_guardrail.OneDoorGuardrail
          mode: pre_call
          policies: examples/litellm_policies.yaml
          db_path: /var/lib/onedoor/gateway.db

Install:  pip install "onedoor[examples]"
Self-test (no proxy needed):  python -m examples.litellm_guardrail
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from litellm.integrations.custom_guardrail import CustomGuardrail

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Decision, Source
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

GOVERNED_COMPLETION_CALLS = (
    "completion",
    "acompletion",
    "anthropic_messages",
    "aanthropic_messages",
    "responses",
    "aresponses",
)


class OneDoorRejection(Exception):
    """Raised to make LiteLLM reject the call; the message reaches the caller."""


class OneDoorGuardrail(CustomGuardrail):
    def __init__(
        self,
        policies: str = "examples/litellm_policies.yaml",
        db_path: str = "onedoor-litellm.db",
        **kwargs: Any,
    ) -> None:
        db = Database(db_path)
        db.init()
        self.conn = db.connect()
        policy_loader.load_file(self.conn, Path(policies))
        self.engine_config = EngineConfig(
            approval_ttl_seconds=3600, connector_timeout_seconds=30.0, tz=ZoneInfo("UTC")
        )
        # call id -> the permit awaiting its outcome. In memory: see the module
        # docstring on what a gateway restart costs.
        self._pending: dict[str, PermittedIntent] = {}
        super().__init__(**kwargs)

    # --- correlation --------------------------------------------------------

    @staticmethod
    def _call_id(data: dict) -> str:
        """The key tying a permit to its outcome. Absent ⇒ refuse before deciding."""
        call_id = data.get("litellm_call_id")
        if not call_id:
            raise OneDoorRejection(
                "onedoor: no litellm_call_id on this request, so the permit could not "
                "be tied to its outcome. Refusing rather than authorizing an action "
                "whose result cannot be reported."
            )
        return str(call_id)

    # --- phase A: decide, and hold the permit -------------------------------

    def _decide(self, action_type: str, params: dict[str, Any], rationale: str) -> PermittedIntent:
        """Reserve and return the permit. Anything not permitted raises."""
        now = now_utc()
        request = ActionRequest(
            request_id=uuid4(),
            action_type=action_type,
            params=params,
            source=Source.LLM,
            rationale=rationale,
            created_at=now,
        )
        outcome = decide_and_reserve(request, conn=self.conn, config=self.engine_config, now=now)
        if isinstance(outcome, PermittedIntent):
            return outcome
        d = outcome.decision
        if d.decision == Decision.PROPOSED:
            raise OneDoorRejection(
                f"onedoor: '{action_type}' requires human approval "
                f"(reason: {d.reason_code.value}, approval_id={outcome.approval_id})."
            )
        if d.decision == Decision.DRY_RUN:
            raise OneDoorRejection(f"onedoor: '{action_type}' is in dry-run — would have executed.")
        raise OneDoorRejection(
            f"onedoor: '{action_type}' denied (reason: {d.reason_code.value}"
            + (f" — {d.detail}" if d.detail else "")
            + ")."
        )

    # --- phase B: report what actually happened -----------------------------

    def _report(self, call_id: str, *, ok: bool, payload: dict, error: str | None) -> None:
        """Report once, if this call is one we permitted. Popping makes it once."""
        intent = self._pending.pop(call_id, None)
        if intent is None:
            return  # not governed by this guardrail, or already reported
        report_result(
            intent,
            conn=self.conn,
            ok=ok,
            payload=payload,
            error=error,
            now=now_utc(),
        )

    # --- LiteLLM hooks ------------------------------------------------------

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict,
        call_type: str,
    ) -> Exception | str | dict | None:
        if call_type == "call_mcp_tool":
            call_id = self._call_id(data)
            tool = data.get("name") or data.get("tool_name") or ""
            args = data.get("arguments") or {}
            self._pending[call_id] = self._decide(
                f"mcp.{tool}", dict(args), f"litellm mcp tool call {tool}"
            )
            return data
        if call_type in GOVERNED_COMPLETION_CALLS:
            call_id = self._call_id(data)
            self._pending[call_id] = self._decide(
                "llm.completion",
                {"model": data.get("model", "")},
                "litellm completion",
            )
            return data
        return data  # everything else: not governed by this example

    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict: Any,
        response: Any,
    ) -> Any:
        call_id = data.get("litellm_call_id")
        if not call_id:
            return response
        payload: dict[str, Any] = {"enforced_by": "litellm post_call"}
        model = getattr(response, "model", None)
        if model:
            payload["model"] = str(model)
        usage = getattr(response, "usage", None)
        total = getattr(usage, "total_tokens", None)
        if total is not None:
            payload["total_tokens"] = int(total)
        self._report(str(call_id), ok=True, payload=payload, error=None)
        return response

    async def async_post_call_failure_hook(
        self,
        request_data: dict,
        original_exception: Exception,
        user_api_key_dict: Any,
        traceback_str: str | None = None,
    ) -> None:
        # Do not skip this. An unreported permit is exactly what reservation
        # reclamation exists to catch, and an example that leaks permits on the
        # failure path teaches the wrong half of the contract.
        call_id = request_data.get("litellm_call_id")
        if not call_id:
            return
        self._report(
            str(call_id),
            ok=False,
            payload={"enforced_by": "litellm post_call"},
            error=str(original_exception),
        )


# --------------------------- self-test ---------------------------------------


def _selftest() -> None:
    import asyncio
    import tempfile
    from uuid import uuid4 as _uuid4

    g = OneDoorGuardrail(
        policies=str(Path(__file__).parent / "litellm_policies.yaml"),
        db_path=tempfile.mktemp(suffix=".db"),
        guardrail_name="onedoor",
    )

    class _Response:
        model = "gpt-4o-mini"

    async def run(call_type: str, data: dict) -> str:
        data = {**data, "litellm_call_id": str(_uuid4())}
        try:
            await g.async_pre_call_hook(None, None, data, call_type)
        except OneDoorRejection as e:
            return f"BLOCK {e}"
        # The gateway acts here. Only now is there an outcome to report.
        await g.async_post_call_success_hook(data, None, _Response())
        return "ok    (permitted, executed, reported)"

    async def main() -> None:
        cases = [
            ("completion", {"model": "gpt-4o-mini"}),
            ("completion", {"model": "gpt-4o-experimental"}),
            ("call_mcp_tool", {"name": "get_weather", "arguments": {"city": "Utrecht"}}),
            (
                "call_mcp_tool",
                {"name": "send_payment", "arguments": {"payee": "webshop", "amount_eur": 49.99}},
            ),
            (
                "call_mcp_tool",
                {"name": "send_payment", "arguments": {"payee": "webshop", "amount_eur": 5000}},
            ),
            ("call_mcp_tool", {"name": "delete_everything", "arguments": {}}),
        ]
        for call_type, data in cases:
            label = data.get("model") or data.get("name")
            print(f"{call_type:14s} {label:22s} -> {await run(call_type, data)}")

    asyncio.run(main())


if __name__ == "__main__":
    _selftest()
