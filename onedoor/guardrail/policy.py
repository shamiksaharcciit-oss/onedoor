"""PolicyStore — read/lookup policies and effect policies, with default-deny synthesis.

An action type absent from the table resolves to a synthesized Tier-3 policy
(``is_default_deny=True``): default-deny (invariant 2). Nothing self-promotes.
"""

from __future__ import annotations

import json
import sqlite3

from onedoor.guardrail.models import Bounds, Caps, EffectPolicy, ParamEffectRule, Policy, Tier
from onedoor.store.clock import from_iso


def _row_to_policy(row: sqlite3.Row) -> Policy:
    return Policy(
        action_type=row["action_type"],
        tier=Tier(row["tier"]),
        bounds=Bounds.model_validate_json(row["bounds_json"]),
        caps=Caps.model_validate_json(row["caps_json"]),
        effects=json.loads(row["effects_json"]) if "effects_json" in row.keys() else [],
        param_effects=[ParamEffectRule.model_validate(r)
                       for r in json.loads(row["param_effects_json"])]
        if "param_effects_json" in row.keys() else [],
        dry_run=bool(row["dry_run"]),
        dry_run_until=from_iso(row["dry_run_until"]) if row["dry_run_until"] else None,
        compensating_command=row["compensating_command"],
        undo_window_seconds=int(row["undo_window_seconds"]),
        requires_step_up=bool(row["requires_step_up"]),
        is_default_deny=False,
    )


class PolicyStore:
    """Thin read layer over the ``policies`` table."""

    def get(self, conn: sqlite3.Connection, action_type: str) -> Policy:
        row = conn.execute("SELECT * FROM policies WHERE action_type=?", (action_type,)).fetchone()
        if row is None:
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
        return _row_to_policy(row)

    def get_effect(self, conn: sqlite3.Connection, effect: str) -> EffectPolicy | None:
        row = conn.execute(
            "SELECT * FROM effect_policies WHERE effect=?", (effect,)
        ).fetchone()
        if row is None:
            return None
        return EffectPolicy(
            effect=row["effect"],
            min_tier=Tier(row["min_tier"]) if row["min_tier"] is not None else None,
            caps=Caps.model_validate_json(row["caps_json"]),
        )

    def all(self, conn: sqlite3.Connection) -> list[Policy]:
        return [
            _row_to_policy(r) for r in conn.execute("SELECT * FROM policies ORDER BY action_type")
        ]
