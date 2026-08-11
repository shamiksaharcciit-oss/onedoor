"""niyam as a LiteLLM custom guardrail — EXPERIMENTAL EXAMPLE.

LiteLLM's proxy loads custom guardrails (subclasses of ``CustomGuardrail``)
and calls ``async_pre_call_hook`` before every call — including, notably,
``call_type="call_mcp_tool"`` for tool calls routed through LiteLLM's MCP
gateway. That hook is a natural Policy Enforcement Point: this adapter turns
each call into a niyam ``ActionRequest`` and consults the decision engine.

What this adds over LiteLLM's built-in MCP permission ACLs (allowed/blocked
tools, allowed param *names*): value-level bounds (amount <= 500, model in an
allow-list), daily caps reserved race-free, default-deny for unlisted tools,
dry-run, a kill switch, tier-3 *defer* (the call is refused with an approval
id a human can release), and an append-only decision audit with reasons.

Example-grade simplifications, stated honestly:
- The engine is synchronous SQLite; a busy proxy should offload to a thread
  and use one guardrail instance per worker.
- Permitted intents are reported immediately (the gateway executes right
  after); a production adapter would carry the intent into
  ``async_post_call_success_hook`` and report the true outcome.
- Approvals are released out-of-band (any process with the DB can call
  ``resume``-style logic); wiring a UI/webhook is the integrator's choice.

Proxy config sketch (config.yaml):
    guardrails:
      - guardrail_name: niyam
        litellm_params:
          guardrail: examples.litellm_guardrail.NiyamGuardrail
          mode: pre_call
          policies: examples/litellm_policies.yaml
          db_path: /var/lib/niyam/gateway.db

Self-test (no proxy needed):  python -m examples.litellm_guardrail
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from litellm.integrations.custom_guardrail import CustomGuardrail

from niyam.guardrail import policy_loader
from niyam.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from niyam.guardrail.executor import EngineConfig
from niyam.guardrail.models import ActionRequest, Decision, Source
from niyam.store.clock import now_utc
from niyam.store.db import Database
from zoneinfo import ZoneInfo


class NiyamRejection(Exception):
    """Raised to make LiteLLM reject the call; the message reaches the caller."""


class NiyamGuardrail(CustomGuardrail):
    def __init__(
        self,
        policies: str = "examples/litellm_policies.yaml",
        db_path: str = "niyam-litellm.db",
        **kwargs: Any,
    ) -> None:
        db = Database(db_path)
        db.init()
        self.conn = db.connect()
        policy_loader.load_file(self.conn, Path(policies))
        self.engine_config = EngineConfig(
            approval_ttl_seconds=3600, connector_timeout_seconds=30.0, tz=ZoneInfo("UTC")
        )
        super().__init__(**kwargs)

    # --- the decision, shared by both governed surfaces ---------------------

    def _decide(self, action_type: str, params: dict[str, Any], rationale: str) -> None:
        now = now_utc()
        request = ActionRequest(
            request_id=uuid4(),
            action_type=action_type,
            params=params,
            source=Source.LLM,
            rationale=rationale,
            created_at=now,
        )
        outcome = decide_and_reserve(
            request, conn=self.conn, config=self.engine_config, now=now
        )
        if isinstance(outcome, PermittedIntent):
            # Example simplification: the gateway executes immediately after a
            # permitted pre-call, so report here. Production: report the real
            # outcome from async_post_call_success_hook.
            report_result(
                outcome, conn=self.conn, ok=True,
                payload={"enforced_by": "litellm pre_call"}, error=None, now=now,
            )
            return
        d = outcome.decision
        if d.decision == Decision.PROPOSED:
            raise NiyamRejection(
                f"niyam: '{action_type}' requires human approval "
                f"(reason: {d.reason_code.value}, approval_id={outcome.approval_id})."
            )
        if d.decision == Decision.DRY_RUN:
            raise NiyamRejection(
                f"niyam: '{action_type}' is in dry-run — would have executed."
            )
        raise NiyamRejection(
            f"niyam: '{action_type}' denied (reason: {d.reason_code.value}"
            + (f" — {d.detail}" if d.detail else "") + ")."
        )

    # --- LiteLLM hook -------------------------------------------------------

    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict,
        call_type: str,
    ) -> Exception | str | dict | None:
        if call_type == "call_mcp_tool":
            tool = data.get("name") or data.get("tool_name") or ""
            args = data.get("arguments") or {}
            self._decide(f"mcp.{tool}", dict(args), f"litellm mcp tool call {tool}")
            return data
        if call_type in ("completion", "acompletion", "anthropic_messages",
                         "aanthropic_messages", "responses", "aresponses"):
            self._decide(
                "llm.completion",
                {"model": data.get("model", "")},
                "litellm completion",
            )
            return data
        return data  # everything else: not governed by this example


# --------------------------- self-test ---------------------------------------

def _selftest() -> None:
    import asyncio
    import tempfile

    g = NiyamGuardrail(
        policies=str(Path(__file__).parent / "litellm_policies.yaml"),
        db_path=tempfile.mktemp(suffix=".db"),
        guardrail_name="niyam",
    )

    async def run(call_type: str, data: dict) -> str:
        try:
            await g.async_pre_call_hook(None, None, data, call_type)
            return "ok    (permitted, audited)"
        except NiyamRejection as e:
            return f"BLOCK {e}"

    async def main() -> None:
        cases = [
            ("completion", {"model": "gpt-4o-mini"}),
            ("completion", {"model": "gpt-4o-experimental"}),
            ("call_mcp_tool", {"name": "get_weather", "arguments": {"city": "Utrecht"}}),
            ("call_mcp_tool", {"name": "send_payment",
                               "arguments": {"payee": "webshop", "amount_eur": 49.99}}),
            ("call_mcp_tool", {"name": "send_payment",
                               "arguments": {"payee": "webshop", "amount_eur": 5000}}),
            ("call_mcp_tool", {"name": "delete_everything", "arguments": {}}),
        ]
        for call_type, data in cases:
            label = data.get("model") or data.get("name")
            print(f"{call_type:14s} {label:22s} -> {await run(call_type, data)}")

    asyncio.run(main())


if __name__ == "__main__":
    _selftest()
