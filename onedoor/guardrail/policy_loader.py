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
from decimal import Decimal
from ipaddress import ip_network
from pathlib import Path
from typing import Any

import yaml

from onedoor.guardrail import policy as policy_module
from onedoor.guardrail import urlcanon
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
        if rule.pattern is not None:
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                raise ValueError(
                    f"policy '{policy.action_type}' param_effects pattern "
                    f"{rule.pattern!r} does not compile: {exc}"
                ) from exc
        if rule.url is not None:
            # Validate the URL rule when the POLICY is written, not when a request
            # arrives. An unencodable host or a malformed CIDR is an authoring error,
            # and discovering it at decision time would turn one bad policy line into
            # a stream of runtime denials with no obvious cause.
            for host in rule.url.hosts:
                try:
                    urlcanon.canonicalize(f"https://{host}/")
                except urlcanon.CanonicalizationError as exc:
                    raise ValueError(
                        f"policy '{policy.action_type}' declares an uninterpretable "
                        f"host {host!r} in a param_effects url rule: {exc}"
                    ) from exc
            for cidr in rule.url.cidrs:
                try:
                    ip_network(cidr, strict=False)
                except ValueError as exc:
                    raise ValueError(
                        f"policy '{policy.action_type}' declares an invalid CIDR "
                        f"{cidr!r} in a param_effects url rule: {exc}"
                    ) from exc
            if not rule.url.hosts and not rule.url.cidrs:
                raise ValueError(
                    f"policy '{policy.action_type}' declares a param_effects url rule "
                    f"with neither hosts nor cidrs -- it can never match, and a rule "
                    f"that can never match is almost certainly not what was meant"
                )


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


class _DecimalSafeLoader(yaml.SafeLoader):
    """A SafeLoader that yields `Decimal` where PyYAML would yield `float`.

    E10 applies to policy YAML as explicitly as it applies to the wire: *or bounds
    compare a Decimal against a float and the money-through-a-float defect reopens*.
    A policy written `max: 500.10` must mean exactly 500.10, not the double nearest
    to it -- otherwise the bound admits anything that rounds onto it (S2).
    """


def _decimal_constructor(loader: yaml.SafeLoader, node: yaml.Node) -> object:
    value = loader.construct_scalar(node)  # type: ignore[arg-type]
    text = str(value)
    lowered = text.lower().lstrip("+-")
    if lowered in {".inf", ".nan"} or "inf" in lowered or "nan" in lowered:
        # E10: NaN and Infinity are malformed input, never silently accepted.
        raise yaml.constructor.ConstructorError(
            None, None, f"non-finite number in policy: {text!r}", node.start_mark
        )
    return Decimal(text)


_DecimalSafeLoader.add_constructor("tag:yaml.org,2002:float", _decimal_constructor)


def _safe_load_decimal(text: str) -> dict[str, Any]:
    """Load policy YAML with numbers as Decimal. Shape-checked, not trusted."""
    loaded = yaml.load(text, Loader=_DecimalSafeLoader)  # noqa: S506 - SafeLoader subclass
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"policy file must be a mapping, got {type(loaded).__name__}")
    return loaded


def load_file(conn: sqlite3.Connection, path: str | Path) -> int:
    """Load and upsert all policies from a YAML file. Validates before writing any.

    Returns the number of policies loaded. Raises before mutating the table if any
    entry is invalid (fail-closed — no partial population).
    """
    raw = _safe_load_decimal(Path(path).read_text(encoding="utf-8")) or {}
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


SNAPSHOT_SCHEMA = "onedoor/policy-snapshot/2"
"""Which canonicalisation produced a `version_hash` (R019).

From 0.4.0 the snapshot renders decimals through the canonical renderer, so `100`,
`100.00` and `1E+2` all record as `100` and hash identically. The consequence is that
an UNCHANGED policy set gets a new hash once, on upgrade -- and disclosure alone does
not make that hash diff *attributable*. Recording the schema lets a reader tell
"renderer changed, rules did not" from "rules changed", from the record rather than
from memory of when the upgrade happened.

Absent means schema 1, by the same absent-value rule as an unstamped `protocol`
column meaning aadp/0.1: pre-0.4.0 rows carry NULL and were hashed under Pydantic's
default rendering, which preserved authored scale and stored numeric bounds as IEEE
doubles.

Once a hash's preimage includes a canonicalisation, the canonicalisation's identity
is part of what the hash means -- a preimage whose definition is not recorded is
re-derivable only by someone who already knows which definition was in force.
"""


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
        "INSERT OR IGNORE INTO policy_versions "
        "(version_hash, snapshot_json, created_at, snapshot_schema) "
        "VALUES (?,?,?,?)",
        (version, snapshot, stamp, SNAPSHOT_SCHEMA),
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
