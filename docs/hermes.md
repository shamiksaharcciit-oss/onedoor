# Hermes Agent plugin — EXPERIMENTAL EXAMPLE

Gate [Hermes Agent](https://github.com/NousResearch/hermes-agent)'s own
built-in tools (`terminal`, `write_file`, `execute_code`, `send_message`, …)
through onedoor's guardrail engine, as a Hermes plugin.

Read from Hermes Agent's own source: `v0.22.5` (commit
`bf0203a794a07aac3ff764972ab9087baa4e4f4e`) and `v0.23.2` (commit
`ae2a81ccc00e9b7c06301523e5bb09608397149c`); this example runs unmodified on
both, with one version-dependent import noted below. Install: `examples/integrations/hermes/plugin.py`
needs an editable Hermes Agent checkout, not a PyPI package — see
[Install](#install).

## The hook, and why it is the one real gate

Hermes dispatches every tool call through `_dispatch_authorized_once`
(`agent/tool_executor.py`), which runs `pre_tool_call` plugin hooks before
the real dispatch and honours a `{"action": "block", "message": ...}`
return by refusing the call outright — the message becomes the tool's own
result and the real tool function never runs
(`agent/tool_executor.py::_pre_tool_block`, calling
`hermes_cli.plugins._dispatch_pre_tool_call_hooks`, which resolves
block/approve/modify directives in `_get_pre_tool_call_directive_details`).
`pre_tool_call` is a declared, synchronous, blocking hook
(`hermes_cli/plugins.py`'s `VALID_HOOKS`), and a plugin registers a handler
for it the same way the bundled `plugins/security-guidance` example does: a
`plugin.yaml` naming it under `provides_hooks`, and a `register(ctx)`
function calling `ctx.register_hook("pre_tool_call", handler)`.

### Two hook points considered and not used

- **The gateway's `agent:step` hook** (`gateway/hooks.py`'s own docstring,
  fired from `gateway/run_turn_progress.py::_step_callback_sync`) looks like
  a per-tool-call hook but is not one: it is scheduled asynchronously
  (`self._schedule(...)`) and fires only *after* the prior iteration's tools
  already ran, with its return value discarded by `HookRegistry.emit`. It
  cannot block anything — not possible, by that source line.
- **`agent._tool_guardrails.before_call`** (`agent/tool_guardrails.py`) is
  Hermes's own internal anti-loop safety net (repeated-failure /
  identical-call-streak detection, with its own `allow | warn | block |
  halt` vocabulary), not an extension point for a third party's policy —
  nothing a plugin can register into.

## The two-phase contract, and why it needs two hooks

AADP splits authorization from execution: `decide_and_reserve` records the
*intent* and reserves budget, then Hermes's own dispatch runs the tool, then
`report_result` records what actually happened. The permit is a promise to
report, not a report — `pre_tool_call` decides and holds the permit;
`post_tool_call` reports the real outcome. Hermes's own dispatch calls
`post_tool_call` exactly once per `tool_call_id`, whether the call ran,
raised, or was itself blocked by this same plugin
(`agent/tool_executor.py::_blocked_tool_result` emits it too, with
`status="blocked"`) — a call this plugin denied never entered the pending
map, so there is nothing to report for it, the same as
`examples/litellm_guardrail.py`'s own `_pending.pop(call_id, None)`.

Correlation is Hermes's own `tool_call_id`, which both hooks receive under
the identical key from the same shared helper
(`agent/inline_tool_executors.py::tool_hook_ids`) — no id translation
between the two hooks.

## Decided both ways

| onedoor decision | `pre_tool_call` return |
|---|---|
| Permitted | `None` — the real tool runs |
| Denied | `{"action": "block", "message": "onedoor: '<tool>' denied (reason: ...)."}` — becomes the tool's own result |

`Decision.PROPOSED` (needs a human) is also expressed as a `block`, naming
the approval id in the message — the same wording
[`docs/integration-mcp.md`](integration-mcp.md)'s "Proposed" row uses —
rather than Hermes's own `{"action": "approve"}` directive. That escalates
to Hermes's own, separate human-approval gate
(`hermes_cli/plugins.py::_resolve_block_from_details`), which knows nothing
of onedoor's store or its approval ids; using it would create two unrelated
approval systems for one decision, so onedoor's own approval stays the one
source of truth.

`Decision.DRY_RUN` is **not possible** through this hook: a veto hook can
only block or allow, and "allow, but tell the model it would have executed
and don't really run it" is neither — the same limitation
[`docs/integration-mcp.md`](integration-mcp.md) states for its own dry-run
row, which needs the tool function itself wrapped, not a veto point.
`examples/integrations/hermes/plugin.py::_decide` raises on a `DRY_RUN`
decision so the gap is loud rather than silently treated as a permit.

## Install

Hermes Agent is not published to PyPI as a built wheel, as of the versions
read above (`setup.py`'s own docstring: *"pip/PyPI ... are no longer
supported distribution methods for Hermes Agent"*); `pip install -e .`
(an editable install) is unaffected, since editable installs use
`build_editable`, never `bdist_wheel`. This example therefore only runs
against an editable Hermes Agent checkout, never an ordinary `pip install`.

Point `HERMES_BUNDLED_PLUGINS` at a directory holding
`examples/integrations/hermes/plugin.py` plus its `plugin.yaml`
(`get_bundled_plugins_dir`, `hermes_cli/plugins.py`), or copy both into the
checkout's own `plugins/onedoor/`. Plugins load opt-in by default
(`plugins.enabled`); enable `onedoor` the same way any other bundled plugin
is enabled.

`examples/integrations/hermes/policies.yaml` declares the example's own
tool surface (`hermes.web_search`, `hermes.send_payment`); every other
Hermes tool (`terminal`, `write_file`, `execute_code`, `delete_everything`,
…) is denied by default, same as any action type no policy names.

Self-test (no Hermes needed): `python -m examples.integrations.hermes.plugin`

## Version note

`PluginContext` moved from `hermes_cli.plugins` (`v0.22.5`) to
`hermes_cli.plugins_context` (`v0.23.2`); `register(ctx)` only calls
`ctx.register_hook`, unchanged across both, so the plugin itself needs no
version check. `tests/integration/test_hermes_gateway.py`, which constructs
a `PluginContext` directly to drive Hermes's real dispatch, tries the
`v0.23.2` location first and falls back to the `v0.22.5` one.

## Status and caveats

Experimental example, like `examples/litellm_guardrail.py`. Stated
honestly:

- **The pending-intent map is in process memory** — the same limitation
  `examples/litellm_guardrail.py` states: onedoor reserves the action
  before it runs, and the reservation is settled or released when the
  tool reports back; a restart between the two hooks strands the permit,
  and the reservation reclaimer releases its budget at the deadline.
- Tested against both `v0.22.5` and `v0.23.2`'s own dispatch code directly
  (`hermes_cli.plugins.get_pre_tool_call_directive`), not against a full,
  running agent turn with a live model — no model, no key, no network, per
  `tests/integration/test_hermes_gateway.py`'s own docstring.
