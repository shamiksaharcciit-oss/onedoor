"""Replay a candidate policy against the real ledger (ND-052 / S1, B1–B4).

*"Under this policy, yesterday's 214 actions: 209 allowed, 3 sent to approval, 2 denied
— here they are."* The Studio's most demo-worthy moment, and it needs no model at all:
it is the deterministic engine, dry-run, run twice.

Two rulings shape every line below.

**A backtest writes nothing to the decision ledger. Ever** (R042 §3) — not a decision
row, not a marker, not a breadcrumb. `actions_audit` is the enforcer's record and the
Studio is a proposer; constitution principle 1 does not bend for evidence's sake.

**It borrows the ledger's witness instead of adding to it.** The receipt binds to real
data by quoting what only the real ledger can produce — the sealed chain. *A backtest
proves it saw real data by citation, not by writing; the ledger vouches for the
backtest, never the reverse.*

Why the isolation is a separate store and not a flag
-----------------------------------------------------
The obvious implementation loads the candidate, replays, and reads the verdicts. It
**writes an audit row per replayed action**, because `decide_and_reserve` audits every
decision it makes — and `dry_run` does not help, since a dry-run *is* a decision and
writes a `dry_run` row. Worse, it **reserves budget**: `decide_and_reserve` is
check-and-reserve, so replaying yesterday's traffic would consume today's caps.

So the candidate goes into a scratch database that is discarded, and the real ledger is
opened for reading and never written. The wrong implementation produces right answers
and pollutes the enforcer's record while looking correct, which is exactly why the
no-rows-no-caps assertion is a test rather than a promise.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from onedoor._vendor.canonical import digest_obj
from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Policy, Source
from onedoor.guardrail.preimage import CURRENT_VERSION
from onedoor.store.clock import from_iso, to_iso
from onedoor.store.db import Database, tx

SCHEMA = "onedoor/backtest/1"

LIVE = "live"
FIXTURE = "fixture"
"""The two values of `ledger_provenance`, and there is no third (R043 §2).

It describes the **cited range**, not the store. A mixed store — a sealed chain with an
unchained prefix — is `live` over the chained span, with the prefix counted as a skip:
*a range that cannot be cited is not replayed*. A label that needs a footnote to be told
apart from its neighbour is a footnote wearing a label's clothes.
"""

SKIP_UNCHAINED_PREFIX = "unchained_prefix"
SKIP_COST_UNDERIVABLE = "cost_underivable"
"""The candidate declares no `cost_param`, so this action's cost is a NON-MEASUREMENT.

R043 §1's law: **measured zero and declared zero never share a representation.** A cost
of `0.00` resolved from `params_json` through the candidate's `cost_param` is a
measurement and participates in cap accounting. An action whose candidate policy
declares no `cost_param` is not a zero — and the engine already says so, because
`caps.resolve_cost` returns `None` rather than zero and the verdict comes back
`cost_unknown`. The two therefore land in different receipts by construction rather than
by a convention this module has to remember.
"""
SKIP_UNREPLAYABLE = "unreplayable_row"

REPLAY_RATIONALE = "onedoor/backtest replay"
"""A required field of an in-memory object, never a value that reaches evidence.

`ActionRequest.rationale` is informational and participates in no check. The scratch
store this request is decided against is discarded, and the receipt records counts, so
nothing invented here is ever sealed — which is the distinction between supplying a
constructor argument and synthesising evidence.
"""


class BacktestRefused(RuntimeError):
    """The backtest will not run, and the message names the remedy."""


@dataclass(frozen=True)
class CitedRange:
    """The span replayed, and the citation that proves it was real."""

    first_seq: int
    last_seq: int
    row_hash_at_last_seq: str

    def to_object(self) -> dict[str, Any]:
        return {
            "first_seq": self.first_seq,
            "last_seq": self.last_seq,
            "row_hash_at_last_seq": self.row_hash_at_last_seq,
        }


@dataclass
class Divergence:
    """What the candidate would have done differently."""

    allowed: int = 0
    to_approval: int = 0
    denied: int = 0
    flips: Counter[str] = field(default_factory=Counter)
    tier_changes: Counter[str] = field(default_factory=Counter)

    def to_object(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "to_approval": self.to_approval,
            "denied": self.denied,
            "flips": dict(sorted(self.flips.items())),
            "tier_changes": dict(sorted(self.tier_changes.items())),
        }


@dataclass(frozen=True)
class BacktestReceipt:
    """The artifact a backtest produces. It cites the ledger; it never writes to it."""

    policy_digest: str
    ledger_provenance: str
    cited: CitedRange
    anchor: dict[str, Any] | None
    instrument: dict[str, Any]
    replayed: int
    skipped: dict[str, int]
    divergence: Divergence

    def to_object(self) -> dict[str, Any]:
        """The canonical body, with `backtest_digest` absent — the manifest pattern."""
        return {
            "schema": SCHEMA,
            "policy_digest": self.policy_digest,
            "ledger_provenance": self.ledger_provenance,
            "range": self.cited.to_object(),
            "anchor": self.anchor,
            "instrument": self.instrument,
            "coverage": {
                "replayed": self.replayed,
                "skipped": dict(sorted(self.skipped.items())),
            },
            "divergence": self.divergence.to_object(),
        }

    def digest(self) -> str:
        """SHA-256 over the canonical whole, with the digest field absent.

        Same run twice gives the same digest -- which makes re-runs comparable for free,
        and is a property a test asserts rather than an aspiration.
        """
        return digest_obj(self.to_object())

    def sealed(self) -> dict[str, Any]:
        """The receipt as it is stored and exported: body plus its own address."""
        return {**self.to_object(), "backtest_digest": self.digest()}


def _cited_range(ledger: sqlite3.Connection) -> tuple[CitedRange, int]:
    """The chained span, and how many rows precede it. Refuses an unchained store.

    **R043 §2's unasked ruling:** a store with no chain at all gets a **refusal, not a
    receipt**. `row_hash_at_last_seq` is REQUIRED precisely so this door cannot be left
    open — a receipt whose citation is null is the store vouching for itself, which this
    product never does. Chaining is opt-in and off by default, so this is the common
    case rather than an exotic one, and the message names the remedy.
    """
    row = ledger.execute(
        "SELECT seq, row_hash FROM actions_audit WHERE seq IS NOT NULL ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise BacktestRefused(
            "this store has no hash-chained rows, so a backtest cannot cite what it "
            "replayed — and a citation-free receipt would be the store vouching for "
            "itself. Enable chaining (`chain.enable`) and rows sealed from today are "
            "citable tomorrow; until then the shipped fixture ledger is the honest "
            "demo path."
        )
    first = ledger.execute(
        "SELECT MIN(seq) AS seq FROM actions_audit WHERE seq IS NOT NULL"
    ).fetchone()
    unchained = ledger.execute(
        "SELECT COUNT(*) AS n FROM actions_audit WHERE seq IS NULL"
    ).fetchone()["n"]
    return (
        CitedRange(
            first_seq=int(first["seq"]),
            last_seq=int(row["seq"]),
            row_hash_at_last_seq=str(row["row_hash"]),
        ),
        int(unchained),
    )


def _request_from(row: sqlite3.Row) -> ActionRequest | None:
    """Rebuild the request a historical row recorded, or None if it cannot be.

    `cost_eur` is deliberately **not** set: the candidate's `cost_param` resolves it
    from `params_json` through `caps.resolve_cost`, which is the same mechanism the live
    engine uses — the instrument is identical, not merely the answer plausible. Where
    the candidate declares no `cost_param`, `resolve_cost` returns **None rather than
    zero** and the verdict comes back `cost_unknown`, which is R043 §1's law enforced by
    the engine itself.
    """
    raw = row["params_json"]
    if raw is None:
        return None
    text = raw if isinstance(raw, str) else bytes(raw).decode("utf-8", "replace")
    try:
        params = json.loads(text, parse_float=Decimal)
        return ActionRequest(
            request_id=UUID(str(row["request_id"])),
            action_type=str(row["action_type"]),
            params=params,
            source=Source(str(row["source"])),
            rationale=REPLAY_RATIONALE,
            created_at=from_iso(str(row["created_at"])),
        )
    except (ValueError, TypeError):
        return None


_LIVE_SHAPE = {"executed": "allowed", "proposed": "to_approval", "denied": "denied"}


def _shape(decision: str) -> str:
    """Collapse a verdict to the three words a deployer reads on the canvas."""
    return _LIVE_SHAPE.get(decision, decision)


def run(
    ledger: sqlite3.Connection,
    candidate: list[Policy],
    *,
    config: EngineConfig,
    provenance: str,
    effects: list[Any] | None = None,
) -> BacktestReceipt:
    """Replay the ledger's chained rows against a candidate policy set.

    The real ledger is **read only**. Every decision is made in a scratch database that
    is deleted when this returns, so `actions_audit` gains no rows and no cap counter
    moves — asserted by a test, because the wrong implementation looks correct.
    """
    if provenance not in (LIVE, FIXTURE):
        raise BacktestRefused(f"ledger_provenance must be {LIVE!r} or {FIXTURE!r}")

    cited, unchained = _cited_range(ledger)
    skipped: Counter[str] = Counter()
    if unchained:
        skipped[SKIP_UNCHAINED_PREFIX] = unchained

    rows = ledger.execute(
        "SELECT * FROM actions_audit WHERE seq IS NOT NULL AND kind IN "
        "('decision','exec_intent') ORDER BY seq"
    ).fetchall()

    divergence = Divergence()
    replayed = 0

    with tempfile.TemporaryDirectory(prefix="onedoor-backtest-") as scratch:
        database = Database(str(Path(scratch) / "candidate.db"))
        database.init()
        conn = database.connect()
        try:
            with tx(conn):
                for effect in effects or []:
                    policy_loader.upsert_effect(conn, effect)
            for policy in candidate:
                policy_loader.upsert(conn, policy)
            declares_cost = {p.action_type: p.cost_param is not None for p in candidate}

            for row in rows:
                request = _request_from(row)
                if request is None:
                    skipped[SKIP_UNREPLAYABLE] += 1
                    continue
                if not declares_cost.get(request.action_type, True):
                    # A non-measurement, not a zero (R043 §1). Counted here AND left to
                    # the engine, which returns `cost_unknown` rather than assuming a
                    # free action -- so the two cases cannot collapse into one receipt.
                    skipped[SKIP_COST_UNDERIVABLE] += 1

                outcome = decide_and_reserve(
                    request, conn=conn, config=config, now=request.created_at
                )
                replayed += 1
                was = _shape(str(row["decision"]))
                now = (
                    "allowed"
                    if isinstance(outcome, PermittedIntent)
                    else _shape(outcome.decision.decision.value)
                )
                setattr(divergence, now, getattr(divergence, now, 0) + 1)
                if was != now:
                    divergence.flips[f"{was}->{now}"] += 1
                new_tier = (
                    int(outcome.effective_tier)
                    if isinstance(outcome, PermittedIntent)
                    else int(outcome.decision.effective_tier)
                )
                if int(row["effective_tier"]) != new_tier:
                    divergence.tier_changes[f"{row['effective_tier']}->{new_tier}"] += 1
        finally:
            conn.close()

    return BacktestReceipt(
        policy_digest=policy_digest(candidate),
        ledger_provenance=provenance,
        cited=cited,
        anchor=_anchor_object(ledger, cited.last_seq),
        instrument={
            "engine": _engine_version(),
            "preimage_version": CURRENT_VERSION,
            "snapshot_schema": policy_loader.SNAPSHOT_SCHEMA,
        },
        replayed=replayed,
        skipped=dict(skipped),
        divergence=divergence,
    )


def policy_digest(candidate: list[Policy]) -> str:
    """The candidate's identity: a digest over its canonical form.

    Built from the models rather than from a store, because a candidate is a proposal
    and has not been ratified into one. S2's ceremony is what turns a candidate into a
    `version_hash`, and it will do that by citing `policy_loader.record_snapshot` rather
    than re-deriving it (R043 §4).
    """
    return digest_obj(
        [json.loads(p.model_dump_json()) for p in sorted(candidate, key=lambda p: p.action_type)]
    )


def _engine_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return f"onedoor/{version('onedoor')}"
    except PackageNotFoundError:  # pragma: no cover - only in a source tree with no dist
        return "onedoor/unknown"


def _anchor_object(ledger: sqlite3.Connection, last_seq: int) -> dict[str, Any] | None:
    from onedoor.guardrail import anchoring

    anchor = anchoring.anchor_for(ledger, last_seq)
    return None if anchor is None else anchor.to_object()


def store(conn: sqlite3.Connection, receipt: BacktestReceipt, now: datetime) -> str:
    """Persist a backtest receipt in the STUDIO's own table. Never `actions_audit`."""
    sealed = receipt.sealed()
    conn.execute(
        "INSERT INTO backtest_receipts (backtest_digest, policy_digest, ledger_provenance, "
        "first_seq, last_seq, row_hash_at_last_seq, body_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(backtest_digest) DO NOTHING",
        (
            sealed["backtest_digest"],
            receipt.policy_digest,
            receipt.ledger_provenance,
            receipt.cited.first_seq,
            receipt.cited.last_seq,
            receipt.cited.row_hash_at_last_seq,
            json.dumps(sealed, sort_keys=True, separators=(",", ":")),
            to_iso(now),
        ),
    )
    return str(sealed["backtest_digest"])
