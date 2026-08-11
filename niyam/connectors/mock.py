"""Mock connector — exercises the guardrail engine without any real integration.

Registered into a :class:`ConnectorRegistry` for the M0 demo and the test suite.
The ``act_flaky`` / ``act_slow`` functions exist purely to test fail-soft handling.
"""

from __future__ import annotations

import time

from niyam.guardrail.models import JsonValue
from niyam.guardrail.registry import ConnectorRegistry


def act_toggle(params: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"toggled": True, "target": params.get("target"), "state": params.get("state")}


def act_restore(params: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"restored": True, "target": params.get("target")}


def act_ok(params: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {"ok": True}


def act_flaky(params: dict[str, JsonValue]) -> dict[str, JsonValue]:
    raise RuntimeError("simulated connector failure")


def act_slow(params: dict[str, JsonValue]) -> dict[str, JsonValue]:
    time.sleep(30)  # exceeds the connector timeout — used to test timeout handling
    return {"ok": True}


def build_registry() -> ConnectorRegistry:
    """Registry for the M0 demo action types (mirrors config/policies.yaml)."""
    registry = ConnectorRegistry()
    registry.register("demo.toggle", act_toggle)
    registry.register("demo.dry", act_toggle)
    registry.register("demo.capped", act_ok)
    registry.register("demo.restore", act_restore)
    # An unlisted action type (default-deny -> Tier 3) that still has a connector,
    # so approving it actually executes — demonstrating the full approval loop.
    registry.register("demo.unlisted", act_ok)
    return registry
