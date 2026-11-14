"""Tool-to-action mapping for the MCP proxy.

A tool's own call shape rarely matches onedoor's action vocabulary -- its argument
names differ, and a value the policy needs may sit nested inside the call. The
mapping file bridges that gap: each mapped tool names the onedoor action type it
becomes, a free-text effect label (for the receipt's rationale only -- it is not
a new decision input), and a dotted path per onedoor param name into the tool's
own `arguments` object.

A tool absent from the mapping is unmapped. The proxy denies it before any
decision is made and never forwards it -- this is a gateway-level guarantee, not
contingent on how any policy happens to be written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from onedoor.guardrail.models import JsonValue


@dataclass(frozen=True)
class ToolMapping:
    action_type: str
    effect: str
    params: dict[str, str] = field(default_factory=dict)
    """onedoor param name -> dotted path into the tool's own `arguments` object."""


@dataclass(frozen=True)
class Mapping:
    tools: dict[str, ToolMapping]
    tools_list_filter: bool = False
    session: str = "none"
    """`"none"` (the default) or `"per_connection"` (onedoor 0.11): whether
    the gateway assigns its own sequence-tracking session id
    instead of relying on a caller-supplied `_meta["onedoor/session_id"]` --
    see `Proxy`'s own resolution of this field for what "connection" means on
    each transport. Any other value fails to load, the same discipline every
    other closed enum in this codebase already has."""


def load_mapping(path: Path) -> Mapping:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_tools = data.get("tools") or {}
    tools: dict[str, ToolMapping] = {}
    for name, entry in raw_tools.items():
        entry = entry or {}
        raw_params = entry.get("params") or {}
        tools[str(name)] = ToolMapping(
            action_type=str(entry.get("action_type", f"mcp.{name}")),
            effect=str(entry.get("effect", "other")),
            params={str(k): str(v) for k, v in raw_params.items()},
        )
    session = str(data.get("session", "none"))
    if session not in ("none", "per_connection"):
        raise ValueError(
            f"mapping file's own 'session' must be 'none' or 'per_connection', got {session!r}"
        )
    return Mapping(
        tools=tools,
        tools_list_filter=bool(data.get("tools_list_filter", False)),
        session=session,
    )


def _extract(path: str, arguments: dict[str, Any]) -> Any | None:
    """Walk a dotted path into `arguments`. `None` if any step along it is
    missing or not a mapping -- never raises. A path with nothing at it is a
    value the mapping layer cannot see, not an error the mapping layer should
    itself fail closed on: the ONE fail-closed path a missing param takes is
    the engine's own `bounds.required`, which already denies a request that
    arrives (mapped or not) without a param it requires."""
    cur: Any = arguments
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def apply_mapping(mapping: ToolMapping, arguments: dict[str, Any]) -> dict[str, JsonValue]:
    """The onedoor params this call's own mapping extracts from `arguments`. A
    path with nothing at it is simply omitted from the result."""
    out: dict[str, JsonValue] = {}
    for onedoor_name, path in mapping.params.items():
        value = _extract(path, arguments)
        if value is not None:
            out[onedoor_name] = value
    return out


def resolve_untrusted_paths(mapping: ToolMapping, tool_paths: list[str]) -> list[str]:
    """Each caller-marked tool-argument path (onedoor 0.11),
    resolved to the onedoor param name this mapping already maps that same
    path onto -- the mapping's own `{onedoor_name: path}` table, read in
    reverse. A caller marks `"arguments.to"`; the mapping's own path for a
    param is stored without that leading member (`"to"`, matching what
    `_extract` walks against `arguments` directly), so a leading
    `"arguments."` is stripped before the lookup. A path absent from the
    mapping (an unmapped tool, or a tool argument the mapping does not name)
    resolves to nothing -- inert, the same as an unrecognised policy path."""
    reverse = {path: onedoor_name for onedoor_name, path in mapping.params.items()}
    resolved: list[str] = []
    for tool_path in tool_paths:
        key = tool_path[len("arguments.") :] if tool_path.startswith("arguments.") else tool_path
        onedoor_name = reverse.get(key)
        if onedoor_name is not None and onedoor_name not in resolved:
            resolved.append(onedoor_name)
    return resolved
