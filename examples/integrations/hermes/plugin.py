"""onedoor as a Hermes Agent plugin — EXPERIMENTAL EXAMPLE.

Read from Hermes Agent's own source (https://github.com/NousResearch/hermes-agent),
`v0.22.5` (commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e`) and `v0.23.2` (commit
`ae2a81ccc00e9b7c06301523e5bb09608397149c`); this example runs unmodified on both.

The hook, and why it is the one real gate
------------------------------------------
Hermes dispatches every tool call through `_dispatch_authorized_once`
(`agent/tool_executor.py`), which runs `pre_tool_call` plugin hooks before the
real dispatch and honours a `{"action": "block", "message": ...}` return by
refusing the call outright -- the message becomes the tool's own result and
the real tool function never runs (`agent/tool_executor.py::_pre_tool_block`,
calling `hermes_cli.plugins._dispatch_pre_tool_call_hooks`, which resolves
block/approve/modify directives in `_get_pre_tool_call_directive_details`).
`pre_tool_call` is a declared, synchronous, blocking hook
(`hermes_cli/plugins.py`'s `VALID_HOOKS`), and a plugin registers a handler
for it the same way the bundled `plugins/security-guidance` example does:
a `plugin.yaml` naming it under `provides_hooks`, and a `register(ctx)`
function calling `ctx.register_hook("pre_tool_call", handler)`.

Two other hook points were considered and are **not used**, with their own
source lines for why:
- The gateway's `agent:step` hook (`gateway/hooks.py`'s own docstring, fired
  from `gateway/run_turn_progress.py::_step_callback_sync`) is scheduled
  asynchronously (`self._schedule(...)`) and fires only AFTER the prior
  iteration's tools already ran, with its return value discarded by
  `HookRegistry.emit` -- it cannot block anything.
- `agent._tool_guardrails.before_call` (`agent/tool_guardrails.py`) is
  Hermes's own internal anti-loop safety net (repeated-failure / identical-
  call detection), not an extension point for a third party's policy.

The two-phase contract, and why it needs two hooks
----------------------------------------------------
AADP splits authorization from execution: `decide_and_reserve` records the
*intent* and reserves budget, then Hermes's own dispatch runs the tool, then
`report_result` records what actually happened. The permit is a promise to
report, not a report -- `pre_tool_call` decides and holds the permit;
`post_tool_call` reports the real outcome. Hermes's own dispatch calls
`post_tool_call` exactly once per `tool_call_id`, whether the call ran,
raised, or was itself blocked by this same plugin
(`agent/tool_executor.py::_blocked_tool_result` emits it too, with
`status="blocked"`) -- a call this plugin denied never entered the pending
map in the first place, so there is nothing to report for it, the same as
`examples/litellm_guardrail.py`'s own `_pending.pop(call_id, None)`.

Correlation is Hermes's own `tool_call_id`, which both hooks receive under
the identical key from the same shared helper
(`agent/inline_tool_executors.py::tool_hook_ids`), so a pre-call permit and
its post-call outcome are always keyed the same way -- no id translation.

Decided both ways
------------------
- Permitted: return `None` (or anything not a `block`/`approve`/`modify`
  dict) from the `pre_tool_call` handler -- the real tool runs.
- Denied: return `{"action": "block", "message": "onedoor: '<tool>' denied
  (reason: ...)."}`. The message becomes the tool's own result, exactly as
  `_blocked_tool_result` builds it.

`Decision.PROPOSED` (needs a human) is also expressed as a `block`, naming
the approval id in the message -- the same wording `docs/integration-mcp.md`
uses for its own "Proposed" row -- rather than Hermes's own `{"action":
"approve"}` directive: that escalates to Hermes's own, separate human-
approval gate (`hermes_cli/plugins.py::_resolve_block_from_details`), which
knows nothing of onedoor's store or its approval ids. Using it would create
two unrelated approval systems for one decision; onedoor's own approval
stays the one source of truth.

`Decision.DRY_RUN` cannot be expressed through this hook at all: a veto hook
can only block or allow, and "allow, but tell the model it would have
executed and don't really run it" is not either of those -- same limitation
`docs/integration-mcp.md` states for its own dry-run row, which needs the
tool function itself wrapped, not a veto point. Out of scope for this
example; `_on_pre_tool_call` raises on a `DRY_RUN` decision so the gap is
loud rather than silently treated as a permit.

Example-grade simplifications, stated honestly:
- **The pending-intent map is in process memory** -- the same stated limit
  as `examples/litellm_guardrail.py`: onedoor reserves the action before it
  runs, and the reservation is settled or released when the tool reports
  back; a restart between the two hooks strands the permit, and the
  reservation reclaimer releases its budget at the deadline.
- `PluginContext` moved from `hermes_cli.plugins` (v0.22.5) to
  `hermes_cli.plugins_context` (v0.23.2); `register(ctx)` below only uses
  `ctx.register_hook`, which is unchanged across both, so this plugin needs
  no version check of its own -- the import-path shim lives in this
  example's own test (`tests/integration/test_hermes_gateway.py`), which
  constructs a `PluginContext` directly to drive Hermes's real dispatch.

Install: this plugin needs an editable Hermes Agent checkout (Hermes is not
published to PyPI as of the versions read above --
`setup.py`'s own docstring: "pip/PyPI ... are no longer supported
distribution methods for Hermes Agent" for a built wheel/sdist; `pip install
-e .` is unaffected, since editable installs use `build_editable`, never
`bdist_wheel`). Point `HERMES_BUNDLED_PLUGINS` at a directory holding this
file plus a `plugin.yaml` (`provides_hooks: [pre_tool_call, post_tool_call]`),
or copy both into the checkout's own `plugins/onedoor/`.

Self-test (no Hermes needed): `python -m examples.integrations.hermes.plugin`
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Decision, Outcome, Source
from onedoor.store.clock import now_utc
from onedoor.store.db import Database


class OneDoorRejection(Exception):
    """Carries the block message a `pre_tool_call` handler returns."""


class OneDoorHermesPlugin:
    def __init__(self, policies_path: str, db_path: str) -> None:
        from onedoor.guardrail import policy_loader

        self._db = Database(db_path)
        self._db.init()
        # Loaded once, up front, on a short-lived connection -- connections run in
        # autocommit mode (onedoor.store.db), so this is already on disk and visible
        # to every per-thread connection `_conn` opens later.
        conn = self._db.connect()
        try:
            policy_loader.load_file(conn, Path(policies_path))
        finally:
            conn.close()
        self.engine_config = EngineConfig(
            approval_ttl_seconds=3600, connector_timeout_seconds=30.0, tz=ZoneInfo("UTC")
        )
        # tool_call_id -> the permit awaiting its outcome. In memory: see the
        # module docstring on what a restart between the two hooks costs.
        self._pending: dict[str, PermittedIntent] = {}
        # One sqlite connection per thread -- see `_conn`'s own docstring for why.
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        """This thread's own connection, opened the first time this thread needs one.

        Hermes's real dispatch (`_dispatch_authorized_once`) calls `pre_tool_call`
        and `post_tool_call` hooks from worker threads, not the thread that built
        this plugin. sqlite3 refuses to reuse one connection across threads by
        default (`check_same_thread`) -- a single shared connection raised "SQLite
        objects created in a thread can only be used in that same thread" the
        moment a real multi-threaded dispatch called it (see
        tests/integration/test_hermes_plugin_threading.py). One connection per
        thread, opened lazily and kept for that thread's own calls, fixes this
        without widening `check_same_thread`, which would only paper over
        concurrent access to one connection rather than give each thread its own.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._db.connect()
            self._local.conn = conn
        return conn

    # --- phase A: decide, and hold the permit -------------------------------

    def _decide(self, tool_name: str, args: dict[str, Any]) -> PermittedIntent:
        """Reserve and return the permit. Anything not permitted raises."""
        now = now_utc()
        request = ActionRequest(
            request_id=uuid4(),
            action_type=f"hermes.{tool_name}",
            params=dict(args),
            source=Source.LLM,
            rationale=f"hermes tool call {tool_name}",
            created_at=now,
        )
        outcome = decide_and_reserve(request, conn=self._conn(), config=self.engine_config, now=now)
        if isinstance(outcome, PermittedIntent):
            return outcome
        d = outcome.decision
        if d.decision == Decision.PROPOSED:
            raise OneDoorRejection(
                f"onedoor: '{tool_name}' requires human approval "
                f"(reason: {d.reason_code.value}, approval_id={outcome.approval_id})."
            )
        if d.decision == Decision.DRY_RUN:
            # Not expressible through a veto-only hook -- see the module docstring.
            raise OneDoorRejection(
                f"onedoor: '{tool_name}' is in dry-run, which this plugin cannot "
                "represent through a block/allow hook alone -- see plugin.py's docstring."
            )
        raise OneDoorRejection(
            f"onedoor: '{tool_name}' denied (reason: {d.reason_code.value}"
            + (f" — {d.detail}" if d.detail else "")
            + ")."
        )

    # --- phase B: report what actually happened -----------------------------

    def _report(
        self, tool_call_id: str, *, outcome: Outcome, payload: dict[str, Any], error: str | None
    ) -> None:
        """Report once, if this call is one we permitted. Popping makes it once."""
        intent = self._pending.pop(tool_call_id, None)
        if intent is None:
            return  # denied by this plugin, not governed, or already reported
        report_result(
            intent, conn=self._conn(), outcome=outcome, payload=payload, error=error, now=now_utc()
        )

    # --- Hermes hooks --------------------------------------------------------

    def on_pre_tool_call(
        self, tool_name: str = "", args: Any = None, tool_call_id: str = "", **_: Any
    ) -> dict[str, str] | None:
        if not tool_call_id:
            return {
                "action": "block",
                "message": "onedoor: no tool_call_id on this call, so the permit could not be "
                "tied to its outcome. Refusing rather than authorizing an action whose "
                "result cannot be reported.",
            }
        try:
            self._pending[tool_call_id] = self._decide(
                tool_name, args if isinstance(args, dict) else {}
            )
        except OneDoorRejection as exc:
            return {"action": "block", "message": str(exc)}
        return None

    def on_post_tool_call(
        self,
        tool_name: str = "",
        tool_call_id: str = "",
        result: Any = None,
        status: str | None = None,
        error_message: str | None = None,
        **_: Any,
    ) -> None:
        if not tool_call_id:
            return
        if status == "error" or error_message:
            self._report(
                tool_call_id,
                outcome=Outcome.FAILURE,
                payload={"enforced_by": "hermes post_tool_call"},
                error=error_message or "tool error",
            )
            return
        self._report(
            tool_call_id,
            outcome=Outcome.SUCCESS,
            payload={"enforced_by": "hermes post_tool_call", "tool_name": tool_name},
            error=None,
        )


_PLUGIN: OneDoorHermesPlugin | None = None


def _get_plugin() -> OneDoorHermesPlugin:
    global _PLUGIN
    if _PLUGIN is None:
        here = Path(__file__).parent
        _PLUGIN = OneDoorHermesPlugin(
            policies_path=str(here / "policies.yaml"), db_path=str(here / "onedoor-hermes.db")
        )
    return _PLUGIN


def register(ctx: Any) -> None:
    plugin = _get_plugin()
    ctx.register_hook("pre_tool_call", plugin.on_pre_tool_call)
    ctx.register_hook("post_tool_call", plugin.on_post_tool_call)


# --------------------------- self-test ---------------------------------------


def _selftest() -> None:
    import tempfile

    plugin = OneDoorHermesPlugin(
        policies_path=str(Path(__file__).parent / "policies.yaml"),
        db_path=tempfile.mktemp(suffix=".db"),
    )

    def run(tool_name: str, args: dict[str, Any]) -> str:
        call_id = str(uuid4())
        directive = plugin.on_pre_tool_call(tool_name=tool_name, args=args, tool_call_id=call_id)
        if directive is not None:
            return f"BLOCK {directive['message']}"
        # Hermes's real dispatch runs the tool here.
        plugin.on_post_tool_call(
            tool_name=tool_name, tool_call_id=call_id, result="ok", status="ok"
        )
        return "ok    (permitted, executed, reported)"

    cases: list[tuple[str, dict[str, Any]]] = [
        ("web_search", {"query": "python 3.13 release notes"}),
        ("send_payment", {"payee": "webshop", "amount_eur": 49.99}),
        ("send_payment", {"payee": "webshop", "amount_eur": 5000}),
        ("delete_everything", {}),
    ]
    for tool_name, args in cases:
        print(f"{tool_name:18s} {args!s:45s} -> {run(tool_name, args)}")


if __name__ == "__main__":
    _selftest()
