"""The ratification ceremony (ND-052 / S2, T1-T5).

Diff a candidate against what is in force, **show the hash it would become**, ratify,
and issue a receipt. This is the act that turns a *candidate* — which has only S1's
`policy_digest`, a digest over models — into a *version*: a `version_hash` recorded in
the store's own `policy_versions`.

The ceremony cites; it never re-derives (R043 §4, R045 §2)
-----------------------------------------------------------
`policy_loader.record_snapshot` owns the canonical form of a policy set and the hash
over it, and `SNAPSHOT_SCHEMA` owns the attribution for when that form changes. Nothing
here recomputes either. The same rule that keeps ND-015's signature and ND-017's Merkle
leaf citing `docs/row-preimage.md` rather than growing their own.

That has a sharp consequence for the preview, which is the demo's whole credibility.

Why the preview is a scratch ratification and not a computation
----------------------------------------------------------------
Showing "this candidate will become `a3f2…`" is a promise the store has to keep. There
were two ways to produce that number: derive it over the candidate the same way
`record_snapshot` does, or ratify into a throwaway store and read what came out. The
first is a **second derivation of a value that already has an owner** — it would work,
and it would drift the first time `_normalized_snapshot` changed. So the preview is the
second: the number shown is produced by the function that will produce the real one.

**And the trap, which is why `preview` copies rows rather than taking the candidate
alone:** `_normalized_snapshot` renders the *whole* policy table. Seeding a scratch
store with just the changed rules yields the hash of a two-rule deployment — *a
different number wearing the right label*. The scratch store therefore holds the
candidate **merged over the active set**, seeded by copying the live rows verbatim, and
`test_sabotage_a_scratch_store_seeded_with_only_the_changed_rules` (R045 §2) watches the
equality test fail when it is not.

Why the write is a compare-and-swap
------------------------------------
A UI has a gap between reading and clicking. If another operator ratifies in that gap,
the diff on screen is stale and the operator signs something other than what they read.
So `ratify` records the hash it diffed **from** and refuses if the active hash has
moved — `approvals.cas_approve`'s shape, for `cas_approve`'s reason: **a lost race must
not silently write.** It refuses loudly; it never retries on the operator's behalf.

What this ceremony cannot do, stated rather than implied away
---------------------------------------------------------------
**A ratification cannot retire a rule.** `policy_loader.upsert` inserts and updates; it
has no delete, and the merged-over-active semantics that finding one requires mean an
action type the candidate omits stays exactly as it was. So `changes` carries `added`
and `modified` and **no `removed`** — a field that can never be non-empty is a promise
nothing keeps. Retirement needs a delete path in the loader and a rule about what
happens to in-flight reservations under a rule that vanished; that is its own ticket,
not a line in this one.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from onedoor._vendor.canonical import digest_obj
from onedoor.guardrail import killswitch, policy, policy_loader
from onedoor.guardrail.models import Caps, EffectPolicy, Policy, Tier
from onedoor.store.clock import to_iso
from onedoor.store.db import Database, tx
from onedoor.studio import backtest

SCHEMA = "onedoor/ratification/1"
"""Version 1 records a **declared** session, not an authenticated principal.

R045 §3: when ND-004/005 brings an authenticated caller identity, that is
`onedoor/ratification/2`. Receipts are versioned for exactly this reason — the field's
meaning changes, so its schema must.
"""

REFUSED_LOST_RACE = "active_version_moved"
REFUSED_BACKTEST_UNRESOLVABLE = "cited_backtest_unresolvable"
REFUSED_BACKTEST_MISMATCH = "cited_backtest_policy_mismatch"
"""The ceremony's own refusal vocabulary.

Deliberately **not** AADP reason codes: these describe a Studio ceremony refusing to
proceed, not a PDP verdict about an action, and the protocol's vocabulary is closed
(`tests/guardrail/test_reason_vocabulary.py`). Naming them apart keeps a Studio refusal
from ever being mistaken for a decision the engine made.

The two backtest reasons are separate because *unverifiable and failed never collapse*
(R010): a digest that resolves to nothing is a citation this store cannot check; a
digest that resolves to a receipt about a **different candidate** is a citation this
store checked and rejected. Different facts, different remedies, different words.
"""


class RatificationRefused(RuntimeError):
    """The ceremony will not proceed, and it says which of its reasons applies."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _meaning(item: Policy | EffectPolicy) -> Any:
    """A rule's *meaning*, for comparison: canonical form, not authored spelling.

    `model_dump_json` renders decimals through the canonical renderer (E8), so a bound
    rewritten from `500` to `500.00` is **not** a change and does not appear in a diff.
    The same rendering that keeps `version_hash` stable across a cosmetic edit.
    """
    return json.loads(item.model_dump_json())


@dataclass(frozen=True)
class Changes:
    """What the candidate does to the set in force. See the module note on `removed`."""

    added: list[str]
    modified: list[str]

    @property
    def is_empty(self) -> bool:
        return not self.added and not self.modified

    def to_object(self) -> dict[str, list[str]]:
        return {"added": sorted(self.added), "modified": sorted(self.modified)}


def diff(active: list[Policy], candidate: list[Policy]) -> Changes:
    """T1. Rule-by-rule, in canonical form, so the diff is of meaning not of spelling."""
    in_force = {p.action_type: _meaning(p) for p in active}
    added: list[str] = []
    modified: list[str] = []
    for proposed in candidate:
        before = in_force.get(proposed.action_type)
        if before is None:
            added.append(proposed.action_type)
        elif before != _meaning(proposed):
            modified.append(proposed.action_type)
    return Changes(added=added, modified=modified)


def diff_effects(active: list[EffectPolicy], candidate: list[EffectPolicy]) -> Changes:
    """The same, for effect policies. Keyed by effect rather than by action type."""
    in_force = {e.effect: _meaning(e) for e in active}
    added: list[str] = []
    modified: list[str] = []
    for proposed in candidate:
        before = in_force.get(proposed.effect)
        if before is None:
            added.append(proposed.effect)
        elif before != _meaning(proposed):
            modified.append(proposed.effect)
    return Changes(added=added, modified=modified)


_COPIED_TABLES = ("policies", "effect_policies")


def _seed_from(source: sqlite3.Connection, scratch: sqlite3.Connection) -> None:
    """Copy the active policy rows **verbatim** into the scratch store.

    Verbatim, rather than round-tripping through `Policy` models, and the reason is the
    same one that made the preview a scratch ratification at all: a model round-trip is
    a second rendering of rows that already exist, and any infidelity in it would show
    up as a previewed hash that does not match the produced one. Copying the bytes
    leaves the scratch store differing from the live one by *only* the candidate's own
    upserts, which is exactly what the preview claims to be showing.
    """
    for table in _COPIED_TABLES:
        rows = source.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 - fixed names
        for row in rows:
            columns = list(row.keys())
            placeholders = ",".join("?" for _ in columns)
            scratch.execute(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",  # noqa: S608
                tuple(row[c] for c in columns),
            )


def _apply(
    conn: sqlite3.Connection, candidate: list[Policy], effects: list[EffectPolicy] | None
) -> str:
    """Upsert the candidate and return the resulting `version_hash`.

    One function, used by the preview and by the real ratification, so the two cannot
    diverge in what they apply or in the order they apply it.
    """
    for effect in effects or []:
        policy_loader.upsert_effect(conn, effect)
    for item in candidate:
        policy_loader.upsert(conn, item)
    return policy_loader.record_snapshot(conn)


@dataclass(frozen=True)
class Preview:
    """What the operator reads before deciding: from, to, and what moved."""

    from_version: str | None
    to_version: str
    changes: Changes
    effect_changes: Changes
    candidate_digest: str

    @property
    def is_a_change(self) -> bool:
        """False when the candidate is already in force — `to_version` equals `from`."""
        return self.from_version != self.to_version


def preview(
    conn: sqlite3.Connection,
    candidate: list[Policy],
    *,
    effects: list[EffectPolicy] | None = None,
    seed_active: bool = True,
) -> Preview:
    """T2. The hash the candidate would become, produced the way it will be produced.

    `seed_active=False` exists **only** for the sabotage in R045 §2 — it seeds the
    scratch store with the changed rules alone, which is the mistake the trap describes,
    and the equality test then fails as it must. No caller should pass it.
    """
    store = policy.PolicyStore()
    active = store.all(conn)
    active_effects = _active_effects(conn)
    with tempfile.TemporaryDirectory(prefix="onedoor-preview-") as scratch_dir:
        database = Database(str(Path(scratch_dir) / "preview.db"))
        database.init()
        scratch = database.connect()
        try:
            with tx(scratch):
                if seed_active:
                    _seed_from(conn, scratch)
            to_version = _apply(scratch, candidate, effects)
        finally:
            scratch.close()
    return Preview(
        from_version=policy_loader.current_version(conn),
        to_version=to_version,
        changes=diff(active, candidate),
        effect_changes=diff_effects(active_effects, list(effects or [])),
        candidate_digest=backtest.policy_digest(candidate),
    )


def _active_effects(conn: sqlite3.Connection) -> list[EffectPolicy]:
    store = policy.PolicyStore()
    return [
        e
        for e in (
            store.get_effect(conn, row["effect"])
            for row in conn.execute("SELECT effect FROM effect_policies ORDER BY effect")
        )
        if e is not None
    ]


@dataclass(frozen=True)
class Ratification:
    """The receipt. Canonical, digested, and citing rather than restating."""

    from_version: str | None
    to_version: str
    candidate_digest: str
    backtest_digest: str | None
    changes: Changes
    effect_changes: Changes
    kill_switch_engaged: bool
    ratified_by_session: str
    ratified_at: str

    def to_object(self) -> dict[str, Any]:
        """The canonical body, with `ratification_digest` absent — the manifest pattern."""
        return {
            "schema": SCHEMA,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "snapshot_schema": policy_loader.SNAPSHOT_SCHEMA,
            "candidate_digest": self.candidate_digest,
            "backtest_digest": self.backtest_digest,
            "changes": self.changes.to_object(),
            "effect_changes": self.effect_changes.to_object(),
            "kill_switch_engaged": self.kill_switch_engaged,
            "ratified_by_session": self.ratified_by_session,
            "ratified_at": self.ratified_at,
        }

    def digest(self) -> str:
        return digest_obj(self.to_object())

    def sealed(self) -> dict[str, Any]:
        return {**self.to_object(), "ratification_digest": self.digest()}


def _check_citation(conn: sqlite3.Connection, backtest_digest: str, candidate_digest: str) -> None:
    """R045 §4.1. A citation nobody checks is decoration.

    The digest must resolve **here**, and the receipt it names must be about **this**
    candidate. Citing someone else's homework is made structurally impossible rather
    than discouraged.
    """
    row = conn.execute(
        "SELECT policy_digest FROM backtest_receipts WHERE backtest_digest=?", (backtest_digest,)
    ).fetchone()
    if row is None:
        raise RatificationRefused(
            REFUSED_BACKTEST_UNRESOLVABLE,
            f"the cited backtest {backtest_digest[:12]}... does not resolve in this store. "
            "A citation this store cannot check is not evidence; run the backtest here, or "
            "ratify without one and let the absence be visible.",
        )
    cited = str(row["policy_digest"])
    if cited != candidate_digest:
        raise RatificationRefused(
            REFUSED_BACKTEST_MISMATCH,
            f"the cited backtest {backtest_digest[:12]}... tested policy "
            f"{cited[:12]}..., not the candidate being ratified "
            f"({candidate_digest[:12]}...). A backtest of a different candidate says "
            "nothing about this one.",
        )


def ratify(
    conn: sqlite3.Connection,
    candidate: list[Policy],
    *,
    expected_version: str | None,
    ratified_by_session: str,
    now: datetime,
    backtest_digest: str | None = None,
    effects: list[EffectPolicy] | None = None,
) -> Ratification:
    """T3 + T4. Compare-and-swap, apply, and seal the receipt. One transaction.

    `expected_version` is the hash the operator's diff was read from — `None` for the
    first ratification on a fresh store, which is **absent, not empty**, and is not the
    same as "I did not check".

    The kill switch does **not** block this (R045 §5). It wins over every action under
    every policy, so nothing ratified can move while it holds: the moment of risk is the
    lift, not the ratification, and blocking here would punish the operator tightening
    rules mid-incident while stopping no attacker who already has ratification access.
    The switch's state is recorded as a hashed field instead — *visible forever,
    deniable never* — and `killswitch.set_engaged` makes the lift the loud moment.
    """
    with tx(conn):
        active = policy_loader.current_version(conn)
        if active != expected_version:
            raise RatificationRefused(
                REFUSED_LOST_RACE,
                f"the active policy version moved while this candidate was being "
                f"reviewed: the diff was read from {_short(expected_version)} and the "
                f"store now holds {_short(active)}. The diff on screen is stale, so "
                "ratifying it would sign something other than what was read. Re-read "
                "the diff against the current version.",
            )
        candidate_digest = backtest.policy_digest(candidate)
        if backtest_digest is not None:
            _check_citation(conn, backtest_digest, candidate_digest)
        engaged = killswitch.is_engaged(conn)
        to_version = _apply(conn, candidate, effects)
        receipt = Ratification(
            from_version=active,
            to_version=to_version,
            candidate_digest=candidate_digest,
            backtest_digest=backtest_digest,
            changes=diff(_policies_at(conn, active), candidate),
            effect_changes=diff_effects(_effects_at(conn, active), list(effects or [])),
            kill_switch_engaged=engaged,
            ratified_by_session=ratified_by_session,
            ratified_at=to_iso(now),
        )
        _store(conn, receipt, now)
    return receipt


def _short(version: str | None) -> str:
    """Absent renders as a word, never as an empty string that reads like a hash."""
    return "no recorded version" if version is None else f"{version[:12]}..."


def _policies_at(conn: sqlite3.Connection, version_hash: str | None) -> list[Policy]:
    """The policy set behind a recorded version, rebuilt from its stored snapshot.

    The diff is computed **after** the write, from the archived snapshot of what was in
    force, rather than from a list read before it. The snapshot is the record; a list
    held in a local variable is a memory of the record.
    """
    snapshot = None if version_hash is None else policy_loader.snapshot_for(conn, version_hash)
    if snapshot is None:
        return []
    rows = json.loads(snapshot).get("policies", [])
    # `_row_to_policy` uses exactly two of `sqlite3.Row`'s methods, `__getitem__` and
    # `keys`, and `_FakeRow` provides both. The cast states that duck-type rather than
    # widening the reader's signature to `Any`, which would give up type checking for
    # every real caller in order to serve this one.
    return [policy._row_to_policy(cast("sqlite3.Row", _FakeRow(row))) for row in rows]


def _effects_at(conn: sqlite3.Connection, version_hash: str | None) -> list[EffectPolicy]:
    snapshot = None if version_hash is None else policy_loader.snapshot_for(conn, version_hash)
    if snapshot is None:
        return []
    return [
        EffectPolicy(
            effect=row["effect"],
            min_tier=Tier(int(row["min_tier"])) if row.get("min_tier") is not None else None,
            caps=Caps.model_validate_json(row["caps_json"]),
        )
        for row in json.loads(snapshot).get("effects", [])
    ]


class _FakeRow:
    """A `dict` wearing `sqlite3.Row`'s two-method interface, for snapshot rebuilds.

    The snapshot stores exactly the columns `_row_to_policy` reads, minus `updated_at`
    which it does not touch. Reusing the store's own row reader keeps one definition of
    "what a policy row means" rather than growing a second parser for archived rows.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def keys(self) -> list[str]:
        return list(self._data)


def _store(conn: sqlite3.Connection, receipt: Ratification, now: datetime) -> str:
    sealed = receipt.sealed()
    conn.execute(
        "INSERT INTO ratifications (ratification_digest, from_version, to_version, "
        "candidate_digest, backtest_digest, kill_switch_engaged, ratified_by_session, "
        "body_json, created_at) VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(ratification_digest) DO NOTHING",
        (
            sealed["ratification_digest"],
            receipt.from_version,
            receipt.to_version,
            receipt.candidate_digest,
            receipt.backtest_digest,
            int(receipt.kill_switch_engaged),
            receipt.ratified_by_session,
            json.dumps(sealed, sort_keys=True, separators=(",", ":")),
            to_iso(now),
        ),
    )
    return str(sealed["ratification_digest"])


def load(conn: sqlite3.Connection, ratification_digest: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT body_json FROM ratifications WHERE ratification_digest=?", (ratification_digest,)
    ).fetchone()
    return None if row is None else dict(json.loads(row["body_json"]))


def latest(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT body_json FROM ratifications ORDER BY created_at DESC, rowid DESC LIMIT 1"
    ).fetchone()
    return None if row is None else dict(json.loads(row["body_json"]))


# --- T4: the two-file export -------------------------------------------------------


def export(conn: sqlite3.Connection, ratification_digest: str) -> tuple[dict[str, Any], str]:
    """The receipt and the snapshot it names. Two files, and nothing else is needed.

    The snapshot is returned as the **exact stored text**, not a re-serialization: its
    SHA-256 *is* `to_version`, so re-rendering it would break the very check the second
    file exists to make possible. E10's received-bytes discipline arriving at a value
    this store generated but must now treat as fixed.
    """
    body = load(conn, ratification_digest)
    if body is None:
        raise RatificationRefused(
            REFUSED_BACKTEST_UNRESOLVABLE,
            f"no ratification {ratification_digest[:12]}... in this store",
        )
    snapshot = policy_loader.snapshot_for(conn, str(body["to_version"]))
    if snapshot is None:  # pragma: no cover - the write path records both together
        raise RatificationRefused(
            REFUSED_BACKTEST_UNRESOLVABLE,
            f"ratification {ratification_digest[:12]}... names a version this store does not hold",
        )
    return body, snapshot


def verify_files(receipt_path: str, snapshot_path: str) -> tuple[str, str]:
    """The whole third-party check: two files, no database.

    Deliberately a thin function over plain arithmetic, so the acceptance test can run
    it in a directory holding exactly those two files. If this ever needs the store, the
    design has failed the independence metric that `anchoring.verify_files` set.
    """
    with open(receipt_path, encoding="utf-8") as handle:
        receipt = json.load(handle)
    with open(snapshot_path, "rb") as raw:
        snapshot_bytes = raw.read()
    claimed = str(receipt.get("ratification_digest", ""))
    body = {k: v for k, v in receipt.items() if k != "ratification_digest"}
    if digest_obj(body) != claimed:
        return ("failed", "the receipt does not match its own digest")
    computed = hashlib.sha256(snapshot_bytes).hexdigest()
    if computed != str(receipt.get("to_version")):
        return (
            "failed",
            f"the snapshot hashes to {computed[:12]}..., not to the "
            f"{_short(str(receipt.get('to_version')))} this receipt ratified",
        )
    return ("verified", f"{_short(str(receipt.get('to_version')))} ratified this policy set")


# --- T5's model: the store dereferences, the renderer renders ----------------------


@dataclass(frozen=True)
class CitedBacktest:
    """A dereferenced citation. `provenance` is None when the digest does not resolve."""

    digest: str
    provenance: str | None


@dataclass(frozen=True)
class RatificationView:
    """Everything a rendering shows, and nothing it computes for itself.

    Built here rather than in the viewer because dereferencing a citation is a store
    read, and `onedoor.viewer.page`'s law is that the page renders an answer it was
    given. The same split that keeps the viewer from growing a second opinion about
    whether a receipt is sound.
    """

    from_version: str | None
    to_version: str
    changes: Changes
    kill_switch_engaged: bool
    ratified_by_session: str
    ratified_at: str
    backtest: CitedBacktest | None
    digest: str


def view_model(conn: sqlite3.Connection, sealed: dict[str, Any]) -> RatificationView:
    """Resolve a stored receipt into what a rendering needs, citation dereferenced."""
    cited: CitedBacktest | None = None
    digest = sealed.get("backtest_digest")
    if digest is not None:
        row = conn.execute(
            "SELECT ledger_provenance FROM backtest_receipts WHERE backtest_digest=?",
            (str(digest),),
        ).fetchone()
        cited = CitedBacktest(
            digest=str(digest),
            provenance=None if row is None else str(row["ledger_provenance"]),
        )
    changes = sealed.get("changes", {})
    return RatificationView(
        from_version=sealed.get("from_version"),
        to_version=str(sealed.get("to_version", "")),
        changes=Changes(
            added=list(changes.get("added", [])), modified=list(changes.get("modified", []))
        ),
        kill_switch_engaged=bool(sealed.get("kill_switch_engaged")),
        ratified_by_session=str(sealed.get("ratified_by_session", "")),
        ratified_at=str(sealed.get("ratified_at", "")),
        backtest=cited,
        digest=str(sealed.get("ratification_digest", "")),
    )
