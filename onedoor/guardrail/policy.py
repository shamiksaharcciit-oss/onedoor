"""PolicyStore — read/lookup policies and effect policies, with default-deny synthesis.

An action type absent from the table resolves to a synthesized Tier-3 policy
(``is_default_deny=True``): default-deny (invariant 2). Nothing self-promotes.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from onedoor.guardrail.models import Bounds, Caps, EffectPolicy, ParamEffectRule, Policy, Tier
from onedoor.store.clock import from_iso


def _row_to_policy(row: sqlite3.Row) -> Policy:
    return Policy(
        action_type=row["action_type"],
        tier=Tier(row["tier"]),
        bounds=Bounds.model_validate_json(row["bounds_json"]),
        caps=Caps.model_validate_json(row["caps_json"]),
        effects=(
            json.loads(row["effects_json"], parse_float=Decimal)
            if "effects_json" in row.keys()
            else []
        ),
        param_effects=[
            ParamEffectRule.model_validate(r)
            for r in json.loads(row["param_effects_json"], parse_float=Decimal)
        ]
        if "param_effects_json" in row.keys()
        else [],
        dry_run=bool(row["dry_run"]),
        dry_run_until=from_iso(row["dry_run_until"]) if row["dry_run_until"] else None,
        compensating_command=row["compensating_command"],
        cost_param=row["cost_param"] if "cost_param" in row.keys() else None,
        undo_window_seconds=int(row["undo_window_seconds"]),
        requires_step_up=bool(row["requires_step_up"]),
        is_default_deny=False,
    )


class _Snapshot:
    """Every policy and effect policy, reconstructed once per policy generation."""

    __slots__ = ("policies", "effects", "version")

    def __init__(self, conn: sqlite3.Connection, version: int) -> None:
        self.version = version
        self.policies: dict[str, Policy] = {
            r["action_type"]: _row_to_policy(r) for r in conn.execute("SELECT * FROM policies")
        }
        self.effects: dict[str, EffectPolicy] = {
            r["effect"]: EffectPolicy(
                effect=r["effect"],
                min_tier=Tier(r["min_tier"]) if r["min_tier"] is not None else None,
                caps=Caps.model_validate_json(r["caps_json"]),
            )
            for r in conn.execute("SELECT * FROM effect_policies")
        }


def invalidate(conn: sqlite3.Connection | None = None) -> None:
    """Drop the cached policy snapshot. Called by the loader after any write.

    ``PRAGMA data_version`` only changes for commits by *other* connections, so a
    process that edits policy through the same connection it decides on would
    otherwise keep reading its own stale snapshot.
    """
    if conn is not None:
        try:
            del conn._policy_snapshot  # type: ignore[attr-defined]
        except AttributeError:
            pass


def _snapshot(conn: sqlite3.Connection) -> _Snapshot:
    version = int(conn.execute("PRAGMA data_version").fetchone()[0])
    cached: _Snapshot | None = getattr(conn, "_policy_snapshot", None)
    if cached is not None and cached.version == version:
        return cached
    fresh = _Snapshot(conn, version)
    try:
        conn._policy_snapshot = fresh  # type: ignore[attr-defined]
    except AttributeError:
        pass  # a plain sqlite3.Connection cannot hold the cache; correctness is unaffected
    return fresh


class PolicyStore:
    """Thin read layer over the ``policies`` table, backed by a per-connection cache.

    The cache is invalidated by ``PRAGMA data_version`` (another connection
    committed) or explicitly by the loader (this connection wrote). Policy is read
    on every decision and changes rarely, which is the shape a cache is for — but
    the kill switch is deliberately NOT cached: a stale kill switch permits actions
    after a stop was ordered, and no latency saving is worth that.
    """

    def get(self, conn: sqlite3.Connection, action_type: str) -> Policy:
        policy = _snapshot(conn).policies.get(action_type)
        if policy is not None:
            return policy
        # Default-deny: unlisted action types are Tier 3, never auto-executing.
        # No declared schema exists, so bounds cannot check params — the human
        # approval is the check; disable strict_params so approval can proceed.
        return Policy(
            action_type=action_type,
            tier=Tier.CONFIRM,
            bounds=Bounds(strict_params=False),
            dry_run=False,
            is_default_deny=True,
        )

    def get_effect(self, conn: sqlite3.Connection, effect: str) -> EffectPolicy | None:
        return _snapshot(conn).effects.get(effect)

    def all(self, conn: sqlite3.Connection) -> list[Policy]:
        snap = _snapshot(conn)
        return [snap.policies[k] for k in sorted(snap.policies)]
