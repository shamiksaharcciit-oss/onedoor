"""Shared test fixtures for the guardrail suite.

Tests use a temp *file* SQLite DB (not :memory:) so the WAL + triggers behave like
production and multiple connections see the same data. ``now`` is frozen and
injected — the engine never calls the wall clock itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from onedoor.connectors import mock
from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Bounds, Caps, Policy, Source, Tier
from onedoor.guardrail.registry import ConnectorRegistry
from onedoor.store import bus
from onedoor.store.db import Database

_CONFIG_DIR = Path(__file__).parent.parent / "config"
FROZEN_NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)


def _seed_test_policies(conn: Connection) -> None:
    """Extra policies used only by tests (Tier 0/2 + fail-soft targets)."""
    extras = [
        Policy(action_type="demo.read", tier=Tier.OBSERVE, bounds=Bounds(strict_params=False)),
        Policy(
            action_type="demo.tier2",
            tier=Tier.AUTO_CAPPED,
            dry_run=False,
            # A tier-2 action executes without a human, so the reversibility
            # precondition applies to it exactly as it does to tier 1. This
            # fixture predates that rule being enforced above Tier.AUTO; the
            # tests using it are about cap accounting, not reversibility.
            compensating_command="demo.restore",
            caps=Caps(daily_rate=5, eur_day=Decimal("10"), eur_month=Decimal("50")),
            bounds=Bounds(strict_params=False),
        ),
        Policy(
            action_type="demo.flaky",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
        Policy(
            action_type="demo.slow",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            bounds=Bounds(strict_params=False),
        ),
    ]
    for policy in extras:
        policy_loader.upsert(conn, policy)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "test.db"))
    database.init()
    conn = database.connect()
    policy_loader.load_file(conn, _CONFIG_DIR / "policies.yaml")
    _seed_test_policies(conn)
    conn.close()
    bus.clear_subscribers()
    yield database
    bus.clear_subscribers()


@pytest.fixture
def fresh(tmp_path: Path) -> Iterator[Connection]:
    """A store with migrations applied and **no policies at all**.

    `db`/`conn` seed a policy set, which is right for the engine's tests and wrong for
    the Studio's: the day-one deployment -- no rules, no recorded version -- is a case
    the ratification ceremony has to get right, and it is where `from_version: None`
    stops being a hypothetical.
    """
    database = Database(str(tmp_path / "fresh.db"))
    database.init()
    connection = database.connect()
    yield connection
    connection.close()


@pytest.fixture
def conn(db: Database) -> Iterator[Connection]:
    connection = db.connect()
    yield connection
    connection.close()


@pytest.fixture
def registry() -> ConnectorRegistry:
    reg = mock.build_registry()
    reg.register("demo.tier2", mock.act_ok)
    reg.register("demo.flaky", mock.act_flaky)
    reg.register("demo.slow", mock.act_slow)
    return reg


@pytest.fixture
def config() -> EngineConfig:
    return EngineConfig(
        approval_ttl_seconds=3600,
        connector_timeout_seconds=1.0,  # short so the slow-connector test is quick
        tz=ZoneInfo("Europe/Amsterdam"),
    )


def make_request(
    action_type: str,
    params: dict[str, object] | None = None,
    *,
    source: Source = Source.UI,
    cost_eur: Decimal = Decimal(0),
    now: datetime = FROZEN_NOW,
) -> ActionRequest:
    return ActionRequest(
        request_id=uuid4(),
        action_type=action_type,
        params=params or {},  # type: ignore[arg-type]
        source=source,
        rationale="test",
        cost_eur=cost_eur,
        created_at=now,
    )
