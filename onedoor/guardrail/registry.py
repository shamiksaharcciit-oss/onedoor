"""ConnectorRegistry — the seam that keeps the executor agnostic.

Maps ``action_type`` to a connector ``act_*`` callable. The executor is the only
place that resolves and calls these, satisfying the invariant that only the
executor imports connector actions. A connector callable takes the action params
and returns a JSON-serializable payload; raising is handled fail-soft.
"""

from __future__ import annotations

from collections.abc import Callable

from onedoor.guardrail.models import JsonValue

ActFn = Callable[[dict[str, JsonValue]], dict[str, JsonValue]]


class ConnectorRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, ActFn] = {}

    def register(self, action_type: str, fn: ActFn) -> None:
        self._actions[action_type] = fn

    def resolve(self, action_type: str) -> ActFn | None:
        return self._actions.get(action_type)

    def has(self, action_type: str) -> bool:
        return action_type in self._actions
