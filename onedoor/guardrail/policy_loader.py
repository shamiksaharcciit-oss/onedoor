"""Seed and validate the policy table from ``config/policies.yaml`` at boot.

Fail-closed: a Tier-1 policy without a registered compensating command is
rejected (invariant 10 — if there's no reversal, it cannot be Tier 1). Loading is
idempotent (upsert), so repeated boots converge to the file's contents.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from onedoor.guardrail import policy as policy_module
from onedoor.guardrail.models import Caps, EffectPolicy, Policy, Tier
from onedoor.store.clock import now_utc, to_iso


def _policy_from_entry(entry: dict[str, Any]) -> Policy:
    return Policy.model_validate(entry)


def validate_policy(policy: Policy) -> None:
    # Every tier that executes without a human needs a registered reversal, not
    # just Tier 1. A budget does not make an irreversible action safe to automate.
    if policy.tier in (Tier.AUTO, Tier.AUTO_CAPPED) and not policy.compensating_command:
        raise ValueError(
            f"policy '{policy.action_type}' is Tier {int(policy.tier)} (auto-executing) "
            "but has no compensating_command (no reversal => cannot auto-execute)"
        )
    # A euro cap needs a resolvable amount. Declaring `cost_param` is the only
    # way policy can supply one, and a parameter that may be absent is not a
    # source -- so it must also be required. The alternative, an amount the
    # engine cannot find, was silently treated as zero and passed every budget.
    if policy.cost_param is not None and policy.cost_param not in policy.bounds.required:
        raise ValueError(
            f"policy '{policy.action_type}' declares cost_param "
            f"'{policy.cost_param}' but does not list it under bounds.required "
            "(an absent amount is not a zero amount)"
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
        (
            ep.effect,
            int(ep.min_tier) if ep.min_tier is not None else None,
            ep.caps.model_dump_json(),
            to_iso(now_utc()),
        ),
    )
    record_snapshot(conn)


def upsert(conn: sqlite3.Connection, policy: Policy) -> None:
    validate_policy(policy)
    conn.execute(
        "INSERT INTO policies ("
        " action_type, tier, bounds_json, caps_json, effects_json, param_effects_json,"
        " dry_run, dry_run_until,"
        " compensating_command, cost_param, undo_window_seconds, requires_step_up,"
        " updated_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(action_type) DO UPDATE SET "
        " tier=excluded.tier, bounds_json=excluded.bounds_json, caps_json=excluded.caps_json,"
        " effects_json=excluded.effects_json, param_effects_json=excluded.param_effects_json,"
        " dry_run=excluded.dry_run, dry_run_until=excluded.dry_run_until,"
        " compensating_command=excluded.compensating_command,"
        " cost_param=excluded.cost_param,"
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
            policy.cost_param,
            policy.undo_window_seconds,
            int(policy.requires_step_up),
            to_iso(now_utc()),
        ),
    )
    record_snapshot(conn)


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
        EffectPolicy(
            effect=name,
            min_tier=Tier(int(cfg["min_tier"])) if cfg.get("min_tier") is not None else None,
            caps=Caps.model_validate(cfg.get("caps", {}) or {}),
        )
        for name, cfg in effect_entries.items()
    ]
    for policy in policies:  # then write
        upsert(conn, policy)
    for ep in effect_policies:
        upsert_effect(conn, ep)
    return len(policies)


def _normalized_snapshot(conn: sqlite3.Connection) -> str:
    """The whole policy set as canonical JSON: sorted keys, stable ordering.

    Canonical form matters — the hash must change when the *rules* change and not
    when a dict happens to serialize in a different order.
    """
    policies = [
        {k: row[k] for k in row.keys() if k != "updated_at"}
        for row in conn.execute("SELECT * FROM policies ORDER BY action_type")
    ]
    effects = [
        {k: row[k] for k in row.keys() if k != "updated_at"}
        for row in conn.execute("SELECT * FROM effect_policies ORDER BY effect")
    ]
    return json.dumps(
        {"policies": policies, "effects": effects}, sort_keys=True, separators=(",", ":")
    )


def record_snapshot(conn: sqlite3.Connection) -> str:
    """Record the current policy set as a version and return its hash.

    Idempotent: an unchanged policy set yields the same hash and inserts nothing.
    Reverting an edit therefore re-uses the original version row, which is correct —
    the rules genuinely are the same — while the audit log still shows every
    decision made in between under the intervening hash.
    """
    snapshot = _normalized_snapshot(conn)
    version = hashlib.sha256(snapshot.encode("utf-8")).hexdigest()
    policy_module.invalidate(conn)  # this connection just wrote; data_version will not tell it
    stamp = to_iso(now_utc())
    conn.execute(
        "INSERT OR IGNORE INTO policy_versions (version_hash, snapshot_json, created_at) "
        "VALUES (?,?,?)",
        (version, snapshot, stamp),
    )
    conn.execute(
        "INSERT INTO policy_current (id, version_hash, updated_at) VALUES (1,?,?) "
        "ON CONFLICT(id) DO UPDATE SET version_hash=excluded.version_hash,"
        " updated_at=excluded.updated_at",
        (version, stamp),
    )
    return version


def current_version(conn: sqlite3.Connection) -> str | None:
    """The hash of the policy set currently in force, or None if never recorded.

    Reads the pointer rather than the newest ``policy_versions`` row: an edit that
    is reverted re-uses the original version, and "most recently inserted" would
    then name the intervening one.
    """
    row = conn.execute("SELECT version_hash FROM policy_current WHERE id=1").fetchone()
    return row["version_hash"] if row else None


def snapshot_for(conn: sqlite3.Connection, version_hash: str) -> str | None:
    """The exact policy set behind a recorded version — the re-derivation input."""
    row = conn.execute(
        "SELECT snapshot_json FROM policy_versions WHERE version_hash=?", (version_hash,)
    ).fetchone()
    return row["snapshot_json"] if row else None
