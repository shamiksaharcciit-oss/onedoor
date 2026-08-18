"""Invariant 6 under real concurrency, with no process-wide mutex.

The HTTP service serializes every request through one lock, so the SQLite
``BEGIN IMMEDIATE`` serialization — the mechanism that is actually supposed to
make cap reservation safe under contention — is never exercised there. These
tests remove the mutex: N threads, each with its own connection, race for a
budget that admits a known number of calls.

Without this, the property that survives horizontal scaling is the one that was
never tested, and the property under test is enforced by the layer that would not.
"""

from __future__ import annotations

import threading
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest
from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_raw, report_result
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import Bounds, Caps, EffectPolicy, Policy, Tier
from onedoor.store.db import Database
from uuid import uuid4

from tests.conftest import FROZEN_NOW

BUDGET = 60  # EUR/day; 1 EUR per call => exactly 60 permits, whatever the racers do


@pytest.fixture
def raced_db(tmp_path: Path, config: EngineConfig) -> Database:
    db = Database(str(tmp_path / "race.db"))
    db.init()
    conn = db.connect()
    for name in ("race.refund_a", "race.payout_b"):
        policy_loader.upsert(
            conn,
            Policy(
                action_type=name,
                tier=Tier.AUTO_CAPPED,
                dry_run=False,
                compensating_command=f"{name}.undo",
                # Deliberately generous per-action: the SHARED effect budget binds.
                caps=Caps(eur_day=Decimal(10_000), eur_month=Decimal(100_000)),
                bounds=Bounds(strict_params=False),
                effects=["money_out"],
            ),
        )
    policy_loader.upsert_effect(
        conn,
        EffectPolicy(
            effect="money_out",
            caps=Caps(eur_day=Decimal(BUDGET), eur_month=Decimal(BUDGET * 10)),
        ),
    )
    conn.close()
    return db


def _race(db: Database, config: EngineConfig, threads: int, per_thread: int) -> Counter:
    results: Counter = Counter()
    guard = threading.Lock()  # protects the Counter only — never the engine

    def worker(idx: int) -> None:
        conn = db.connect()  # one connection per thread, no sharing
        action = "race.refund_a" if idx % 2 == 0 else "race.payout_b"
        local: Counter = Counter()
        try:
            for _ in range(per_thread):
                out = decide_raw(
                    {
                        "request_id": str(uuid4()),
                        "action_type": action,
                        "params": {},
                        "source": "llm",
                        "rationale": "race",
                        "cost_eur": Decimal(1),
                        "created_at": FROZEN_NOW,
                    },
                    conn=conn,
                    config=config,
                    now=FROZEN_NOW,
                )
                if isinstance(out, PermittedIntent):
                    report_result(
                        out, conn=conn, ok=True, payload=None, error=None, now=FROZEN_NOW
                    )
                    local["PERMIT"] += 1
                else:
                    local[str(out.decision.reason_code)] += 1
        finally:
            conn.close()
        with guard:
            results.update(local)

    workers = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    return results


def test_single_thread_exhausts_budget_exactly(raced_db: Database, config: EngineConfig) -> None:
    """Positive control. If this fails, the concurrent tests measure nothing."""
    res = _race(raced_db, config, threads=1, per_thread=BUDGET + 20)
    assert res["PERMIT"] == BUDGET


@pytest.mark.parametrize(("threads", "per_thread"), [(4, 25), (8, 15), (16, 10)])
def test_no_over_reservation_under_concurrency(
    raced_db: Database, config: EngineConfig, threads: int, per_thread: int
) -> None:
    res = _race(raced_db, config, threads, per_thread)
    raised = {k: v for k, v in res.items() if k.startswith("RAISED")}
    assert not raised, f"decide raised under contention: {raised}"
    assert res["PERMIT"] == BUDGET, (
        f"{threads} threads over-reserved by {res['PERMIT'] - BUDGET} "
        "— invariant 6 does not hold without the service mutex"
    )


def test_shared_effect_counter_is_not_partially_reserved(
    raced_db: Database, config: EngineConfig
) -> None:
    """A refused call must not have burned action-level budget on its way to refusal."""
    res = _race(raced_db, config, threads=8, per_thread=15)
    conn = raced_db.connect()
    rows = conn.execute(
        "SELECT action_type, eur_total FROM cap_counters WHERE window_kind='eur_day'"
    ).fetchall()
    conn.close()
    effect = sum(Decimal(r["eur_total"]) for r in rows if r["action_type"].startswith("effect:"))
    per_action = sum(
        Decimal(r["eur_total"]) for r in rows if not r["action_type"].startswith("effect:")
    )
    assert effect == per_action == Decimal(res["PERMIT"]) == Decimal(BUDGET)
