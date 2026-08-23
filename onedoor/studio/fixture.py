"""The shipped demonstration ledger (ND-052 / S1-B3).

A day-one deployment has an empty store, and the demo bar says **real, receipted,
limit-stated output**. Those meet at a declared field rather than a blur: a backtest run
against this ledger is `ledger_provenance: fixture`, hashed with the rest of the receipt,
and the label must survive into every rendering.

**Mechanically real in every respect** — chained rows, valid preimages, verifiable
digests, sealable, anchorable — because it is produced by the real engine making real
decisions. Nothing here writes an audit row by hand. A fixture whose rows were forged
would be a demo of the forger's arithmetic rather than of the product.

What is pinned, and why it is the ledger rather than the file
-------------------------------------------------------------
Timestamps are **pinned inputs, not sampled**, and request ids are derived rather than
minted — so **every `actions_audit` row and the chain head reproduce exactly**, asserted
in CI by building twice and comparing.

**The database FILE is not byte-reproducible, and cannot be.** Measured rather than
assumed: two builds produce identical `actions_audit` (107 rows, the same `row_hash` on
every one) and differ only in housekeeping stamps the engine samples internally —
`schema_migrations.applied_at`, `policy_versions.created_at`, `config.updated_at`,
`policy_current.updated_at`. None of those is an input this script can pin; reaching them
would mean threading an injected clock through migrations and snapshot writes, which is a
change to the engine for the sake of a demo asset.

So **the pinned artifact is the chain head**, committed as one line in `_fixture/HEAD`,
and the ledger is built on demand. That serves both purposes R043 §3 named better than a
committed `.db` would: the regeneration test compares what is actually deterministic, and
the anti-masquerade property depends only on `row_hash` values, which are. It also keeps
the wheel small — the committed database measured 315 KB, over the 256 KB the ticket
declared, and this is a few hundred bytes.

The property that pinning buys beyond reproducibility (R043 §3): **the fixture's chain
head is a published constant.** Every install ships the same bytes, so its `row_hash`
values are public — which makes a fixture-backed receipt stripped of its label and
presented as `live` **checkable by anyone**, by comparing the cited
`row_hash_at_last_seq` against the shipped head. B5's tests guard the renderings; the
pinning guards the world outside them.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from onedoor.guardrail import chain, policy_loader
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    Caps,
    EffectPolicy,
    NumericBound,
    Policy,
    Source,
    Tier,
)
from onedoor.store.db import Database, tx

FIXTURE_DIR = Path(__file__).parent / "_fixture"
FIXTURE_DB = FIXTURE_DIR / "demo-ledger.db"
HEAD_FILE = FIXTURE_DIR / "HEAD"
"""The published chain head. One line, so anyone can check a citation against it."""

EPOCH = datetime(2026, 3, 2, 9, 0, 0, tzinfo=UTC)
"""A pinned input, not a sample. Sampling the clock would make the bytes drift daily and
the pin meaningless."""

CONFIG = EngineConfig(approval_ttl_seconds=3600, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC"))

ACTIONS = ("payments.transfer", "crm.update_record", "docs.read", "net.http", "refunds.issue")
"""A payments-shaped world, matching S5's vertical and the launch demo's incident."""


def _policies() -> tuple[list[Policy], list[EffectPolicy]]:
    """The demonstration deployment's rules. Ordinary, and deliberately imperfect."""
    effects = [
        EffectPolicy(
            effect="money.egress", min_tier=Tier.AUTO_CAPPED, caps=Caps(eur_day=Decimal("500"))
        ),
    ]
    policies = [
        Policy(
            action_type="payments.transfer",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="payments.reverse",
            caps=Caps(eur_day=Decimal("500")),
            cost_param="amount_eur",
            effects=["money.egress"],
            bounds=Bounds(
                strict_params=False,
                required=["amount_eur"],
                numeric={"amount_eur": NumericBound(max=Decimal("2000"))},
            ),
        ),
        Policy(
            action_type="refunds.issue",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            compensating_command="payments.reverse",
            caps=Caps(eur_day=Decimal("300")),
            cost_param="amount_eur",
            effects=["money.egress"],
            bounds=Bounds(strict_params=False, required=["amount_eur"]),
        ),
        Policy(
            action_type="payments.reverse",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="payments.reverse",
            bounds=Bounds(strict_params=False),
        ),
        Policy(
            action_type="crm.update_record",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="payments.reverse",
            bounds=Bounds(strict_params=False),
        ),
        Policy(
            action_type="docs.read",
            tier=Tier.OBSERVE,
            bounds=Bounds(strict_params=False),
        ),
        Policy(
            action_type="net.http",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="payments.reverse",
            bounds=Bounds(strict_params=False),
        ),
    ]
    return policies, effects


def _script() -> list[tuple[int, str, dict[str, object]]]:
    """The demo day, as `(minute offset, action, params)`. Pinned, never random.

    Shaped so a backtest of it has something to say: ordinary traffic, a few payments
    that walk into the daily cap, and reads that never move money.
    """
    plan: list[tuple[int, str, dict[str, object]]] = []
    minute = 0
    for day in range(3):
        base = day * 24 * 60
        for i in range(28):
            minute = base + i * 17
            if i % 7 == 0:
                plan.append((minute, "payments.transfer", {"amount_eur": Decimal("120.00")}))
            elif i % 7 == 3:
                plan.append((minute, "refunds.issue", {"amount_eur": Decimal("45.50")}))
            elif i % 7 == 5:
                plan.append((minute, "net.http", {"url": "https://status.example.com/health"}))
            elif i % 3 == 0:
                plan.append((minute, "crm.update_record", {"id": f"c-{i}", "field": "notes"}))
            else:
                plan.append((minute, "docs.read", {"path": f"handbook/{i}.md"}))
    return plan


def build(path: Path) -> str:
    """Generate the fixture ledger at `path`. Returns its chain head.

    Every row is written by the real engine deciding a real request. The only thing
    pinned is the *input*: the clock and the request ids.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    database = Database(str(path))
    database.init()
    conn = database.connect()
    try:
        policies, effects = _policies()
        with tx(conn):
            for effect in effects:
                policy_loader.upsert_effect(conn, effect)
        for policy in policies:
            policy_loader.upsert(conn, policy)
        with tx(conn):
            chain.enable(conn)

        for index, (offset, action, params) in enumerate(_script()):
            when = EPOCH + timedelta(minutes=offset)
            decide_and_reserve(
                ActionRequest(
                    # Derived, not minted: uuid4 would make the bytes drift per run.
                    request_id=UUID(int=0xD3_0000 + index),
                    action_type=action,
                    params=params,  # type: ignore[arg-type]
                    source=Source.LLM,
                    rationale="onedoor demonstration ledger",
                    created_at=when,
                ),
                conn=conn,
                config=CONFIG,
                now=when,
            )
        return head(conn)
    finally:
        conn.close()


def head(conn: sqlite3.Connection) -> str:
    """The chain head — the constant a citation is checked against."""
    row = conn.execute(
        "SELECT row_hash FROM actions_audit WHERE seq IS NOT NULL ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if row is None:  # pragma: no cover - a fixture without a chain is a build failure
        raise RuntimeError("the fixture ledger has no chained rows")
    return str(row["row_hash"])


def published_head() -> str | None:
    """The shipped head, or None when the fixture has not been generated."""
    if not HEAD_FILE.is_file():
        return None
    return HEAD_FILE.read_text(encoding="utf-8").strip()


def cache_path() -> Path:
    """Where a built fixture lives: beside the package when writable, else a temp dir."""
    if FIXTURE_DIR.is_dir() and os.access(FIXTURE_DIR, os.W_OK):
        return FIXTURE_DB
    return Path(tempfile.gettempdir()) / "onedoor-demo-ledger.db"


def open_fixture() -> sqlite3.Connection:
    """A connection to the demonstration ledger, building it if it is not there yet.

    The ledger is generated rather than shipped, for the reason in the module docstring:
    a `.db` cannot be byte-pinned, and what matters -- the chain head -- can be.

    **The head is checked against the committed constant every time.** A fixture that did
    not reproduce would be a demo asset quietly drifting from the value the
    anti-masquerade check compares against, which is worse than having no fixture.
    """
    path = cache_path()
    expected = published_head()
    if path.is_file():
        conn = Database(str(path)).connect()
        try:
            if expected is None or head(conn) == expected:
                return conn
        except (RuntimeError, sqlite3.DatabaseError):
            pass
        conn.close()
    built = build(path)
    if expected is not None and built != expected:
        raise RuntimeError(
            f"the demonstration ledger did not reproduce: built {built[:12]}..., expected "
            f"{expected[:12]}.... The generator has changed without its HEAD being "
            f"regenerated, and the anti-masquerade check compares against HEAD."
        )
    return Database(str(path)).connect()


def main() -> int:  # pragma: no cover - the generator, exercised by the regeneration test
    """Regenerate the ledger and commit its head. The head is the artifact."""
    digest = build(cache_path())
    HEAD_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEAD_FILE.write_text(digest + chr(10), encoding="utf-8")
    print(f"built {cache_path()} ({cache_path().stat().st_size} bytes, NOT committed)")
    print(f"pinned chain head -> {HEAD_FILE}")
    print(digest)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
