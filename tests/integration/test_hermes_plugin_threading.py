"""Hermes Agent's own real dispatch calls `pre_tool_call`/`post_tool_call` hooks
from worker threads, never the thread that constructed the plugin (confirmed by
actually running `examples/integrations/hermes/plugin.py` against both tested
Hermes releases under Python 3.14 -- every real call failed with sqlite3's
same-thread error). This reproduces exactly that, one thread, no Hermes needed, so
a regression here is caught by the ordinary gate even without a Hermes checkout on
the interpreter.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from examples.integrations.hermes.plugin import OneDoorHermesPlugin

_POLICIES = str(Path(__file__).resolve().parents[2] / "examples/integrations/hermes/policies.yaml")


def _make_plugin() -> OneDoorHermesPlugin:
    return OneDoorHermesPlugin(policies_path=_POLICIES, db_path=tempfile.mktemp(suffix=".db"))


def test_hooks_called_from_a_thread_other_than_the_one_that_built_the_plugin() -> None:
    plugin = _make_plugin()  # built on this (the test's) thread

    call_id = str(uuid4())
    results: dict[str, object] = {}

    def worker() -> None:
        try:
            results["directive"] = plugin.on_pre_tool_call(
                tool_name="web_search", args={"query": "x"}, tool_call_id=call_id
            )
        except Exception as exc:  # noqa: BLE001 -- captured to assert on, not swallowed
            results["pre_error"] = exc
            return
        try:
            plugin.on_post_tool_call(
                tool_name="web_search", tool_call_id=call_id, result="3 results", status="ok"
            )
        except Exception as exc:  # noqa: BLE001
            results["post_error"] = exc

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert "pre_error" not in results, (
        f"on_pre_tool_call raised when called from another thread: {results.get('pre_error')!r}"
    )
    assert "post_error" not in results, (
        f"on_post_tool_call raised when called from another thread: {results.get('post_error')!r}"
    )
    assert results.get("directive") is None  # web_search is permitted by policies.yaml
    assert call_id not in plugin._pending  # post_tool_call reported it and popped it
