"""No model, no key, no network: registers `examples/integrations/hermes/plugin.py`
through Hermes Agent's own real `PluginContext`/`register_hook`, then calls Hermes's
own real `hermes_cli.plugins.get_pre_tool_call_directive`, exactly as
`agent/tool_executor.py::_pre_tool_block` does, over both tested releases
(v0.22.5, v0.23.2) -- proving the plugin genuinely wires into Hermes's unmodified
dispatch, not just that its own callback functions happen to return the right shape.

Skips outright unless a Hermes Agent checkout is importable (`hermes_cli`): Hermes is
not on PyPI as a built wheel as of the versions read for this example (`setup.py`'s own
docstring), so this is only ever exercised against an editable checkout (`pip install -e .`),
never by an ordinary `pip install`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

hermes_cli = pytest.importorskip(
    "hermes_cli", reason="no Hermes Agent checkout on this interpreter"
)

from examples.integrations.hermes.plugin import OneDoorHermesPlugin  # noqa: E402

try:  # v0.23.2 and newer
    from hermes_cli.plugins_context import PluginContext
except ImportError:  # v0.22.5
    from hermes_cli.plugins import PluginContext  # type: ignore[no-redef]

from hermes_cli.plugins import get_plugin_manager  # noqa: E402
from hermes_cli.plugins_manifest import PluginManifest  # noqa: E402


@pytest.fixture
def hermes_manager(monkeypatch, tmp_path):
    """The real, process-wide `PluginManager` for an isolated `HERMES_HOME`, marked
    already-discovered so no real plugin directory (including the bundled
    `security-guidance` example) is scanned or loaded -- this test registers the one
    hook it needs directly, through the same public `register_hook` real plugins use.
    """
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    manager = get_plugin_manager()
    manager._discovered = True  # see the docstring above: skip the real filesystem scan
    return manager


@pytest.fixture
def onedoor_plugin(hermes_manager):
    plugin = OneDoorHermesPlugin(
        policies_path=str(
            Path(__file__).resolve().parents[2] / "examples/integrations/hermes/policies.yaml"
        ),
        db_path=tempfile.mktemp(suffix=".db"),
    )
    manifest = PluginManifest(name="onedoor", provides_hooks=["pre_tool_call", "post_tool_call"])
    ctx = PluginContext(manifest, hermes_manager)
    ctx.register_hook("pre_tool_call", plugin.on_pre_tool_call)
    ctx.register_hook("post_tool_call", plugin.on_post_tool_call)
    return plugin


def _directive(tool_name: str, args: dict, tool_call_id: str) -> tuple[str | None, str | None]:
    """Hermes's own real dispatch, exactly as `_pre_tool_block` calls it."""
    from hermes_cli.plugins import get_pre_tool_call_directive

    return get_pre_tool_call_directive(tool_name, args, tool_call_id=tool_call_id)


def test_a_permitted_call_is_let_through_by_hermes_own_dispatch(onedoor_plugin) -> None:
    directive, message = _directive(
        "web_search", {"query": "python 3.13 release notes"}, str(uuid4())
    )
    assert (directive, message) == (None, None)


def test_an_unlisted_tool_is_blocked_by_hermes_own_dispatch(onedoor_plugin) -> None:
    directive, message = _directive("delete_everything", {}, str(uuid4()))
    assert directive == "block"
    assert message is not None and "denied" in message


def test_a_tier3_action_within_bounds_is_blocked_pending_approval(onedoor_plugin) -> None:
    directive, message = _directive(
        "send_payment", {"payee": "webshop", "amount_eur": 49.99}, str(uuid4())
    )
    assert directive == "block"
    assert (
        message is not None and "requires human approval" in message and "approval_id=" in message
    )


def test_a_bounds_violation_is_blocked_with_the_bound_named(onedoor_plugin) -> None:
    directive, message = _directive(
        "send_payment", {"payee": "webshop", "amount_eur": 5000}, str(uuid4())
    )
    assert directive == "block"
    assert message is not None and "denied" in message and "500" in message


def test_a_call_with_no_tool_call_id_is_refused_before_deciding(onedoor_plugin) -> None:
    directive, message = _directive("web_search", {"query": "x"}, "")
    assert directive == "block"
    assert message is not None and "tool_call_id" in message


def test_a_permitted_call_reports_its_outcome_and_a_denied_one_reports_nothing(
    onedoor_plugin,
) -> None:
    permitted_id, denied_id = str(uuid4()), str(uuid4())
    assert _directive("web_search", {"query": "x"}, permitted_id) == (None, None)
    assert _directive("delete_everything", {}, denied_id)[0] == "block"

    assert permitted_id in onedoor_plugin._pending
    assert denied_id not in onedoor_plugin._pending  # never entered the pending map at all

    onedoor_plugin.on_post_tool_call(
        tool_name="web_search", tool_call_id=permitted_id, result="3 results", status="ok"
    )
    assert permitted_id not in onedoor_plugin._pending  # reported exactly once

    # post_tool_call also fires for a call THIS plugin blocked (Hermes's own
    # _blocked_tool_result emits it with status="blocked"); nothing to report.
    onedoor_plugin.on_post_tool_call(
        tool_name="delete_everything", tool_call_id=denied_id, result="blocked", status="blocked"
    )
