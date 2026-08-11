"""Seed and validate the policy table from ``config/policies.yaml`` at boot.

Fail-closed: a Tier-1 policy without a registered compensating command is
rejected (invariant 10 — if there's no reversal, it cannot be Tier 1). Loading is
idempotent (upsert), so repeated boots converge to the file's contents.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from onedoor.guardrail.models import Caps, EffectPolicy, Policy, Tier
from onedoor.store.clock import now_utc, to_iso


def _policy_from_entry(entry: dict[str, Any]) -> Policy:
    return Policy.model_validate(entry)


def validate_policy(policy: Policy) -> None:
    if policy.tier == Tier.AUTO and not policy.compensating_command:
        raise ValueError(
            f"policy '{policy.action_type}' is Tier 1 but has no compensating_command "
            "(invariant 10: no reversal => cannot be Tier 1)"
        )
    for rule in policy.param_effects:
        try:
            re.compile(rule.pattern)
        except re.error as exc:
            raise ValueError(
                f"policy '{policy.action_type}' param_effects pattern "
                f"{rule.pattern!r} does not compile: {exc}"
            ) from exc


def upsert_effect(conn: sqlite3.Connection, ep: EffectPolicy) -> None:
    conn.execute(
        "INSERT INTO effect_policies (effect, min_tier, caps_json, updated_at) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(effect) DO UPDATE SET min_tier=excluded.min_tier,"
        " caps_json=excluded.caps_json, updated_at=excluded.updated_at",
        (ep.effect, int(ep.min_tier) if ep.min_tier is not None else None,
         ep.caps.model_dump_json(), to_iso(now_utc())),
    )


def upsert(conn: sqlite3.Connection, policy: Policy) -> None:
    validate_policy(policy)
    conn.execute(
        "INSERT INTO policies ("
        " action_type, tier, bounds_json, caps_json, effects_json, param_effects_json,"
        " dry_run, dry_run_until,"
        " compensating_command, undo_window_seconds, requires_step_up, updated_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(action_type) DO UPDATE SET "
        " tier=excluded.tier, bounds_json=excluded.bounds_json, caps_json=excluded.caps_json,"
        " effects_json=excluded.effects_json, param_effects_json=excluded.param_effects_json,"
        " dry_run=excluded.dry_run, dry_run_until=excluded.dry_run_until,"
        " compensating_command=excluded.compensating_command,"
        " undo_window_seconds=excluded.undo_window_seconds,"
        " requires_step_up=excluded.requires_step_up, updated_at=excluded.updated_at",
        (
            policy.action_type,
            int(policy.tier),
            policy.bounds.model_dump_json(),
            policy.caps.model_dump_json(),
            json.dumps(policy.effects),
            json.dumps([r.model_dump() for r in policy.param_effects]),
            int(policy.dry_run),
            to_iso(policy.dry_run_until) if policy.dry_run_until else None,
            policy.compensating_command,
            policy.undo_window_seconds,
            int(policy.requires_step_up),
            to_iso(now_utc()),
        ),
    )


def load_file(conn: sqlite3.Connection, path: str | Path) -> int:
    """Load and upsert all policies from a YAML file. Validates before writing any.

    Returns the number of policies loaded. Raises before mutating the table if any
    entry is invalid (fail-closed — no partial population).
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries = raw.get("policies", [])
    policies = [_policy_from_entry(e) for e in entries]
    for policy in policies:  # validate all first
        validate_policy(policy)
    effect_entries = raw.get("effects", {}) or {}
    effect_policies = [
        EffectPolicy(effect=name,
                     min_tier=Tier(int(cfg["min_tier"])) if cfg.get("min_tier") is not None else None,
                     caps=Caps.model_validate(cfg.get("caps", {}) or {}))
        for name, cfg in effect_entries.items()
    ]
    for policy in policies:  # then write
        upsert(conn, policy)
    for ep in effect_policies:
        upsert_effect(conn, ep)
    return len(policies)
