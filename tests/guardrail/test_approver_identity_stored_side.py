"""The normalization check and its comparison must read the STORED
identity fresh and normalize it too, not assume it was already written
normalized -- a database upgraded from 0.10.2, or any row written before
the normalization fix landed, holds identities exactly as they were
typed (literally "Alice", unnormalized). `cas_approve` already does
this: both `row["proposed_by"]` and each entry of `current_approvers`
are read raw from the database and passed through `normalize_identity`
at comparison time, every time -- not read once and assumed normalized.
Demonstrated here directly against rows holding their identities in raw,
unnormalized, as-typed form.
"""

from __future__ import annotations

from decimal import Decimal
from sqlite3 import Connection

import pytest

from onedoor.guardrail import approvals, policy_loader
from onedoor.guardrail.errors import ApprovalError
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ApprovalPolicy, Bounds, Policy, Tier
from onedoor.store.db import tx
from tests.conftest import FROZEN_NOW, make_request


def _two_person(conn: Connection) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.identity_stored_side",
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(strict_params=False),
            approval=ApprovalPolicy(two_person_above_eur=Decimal("100")),
        ),
    )


def _propose(conn: Connection, config: EngineConfig, *, proposed_by: str | None) -> int:
    with tx(conn):
        approval_id = approvals.create(
            conn,
            make_request("demo.identity_stored_side", {}, cost_eur=Decimal("150")),
            config.approval_ttl_seconds,
            FROZEN_NOW,
            proposed_by=proposed_by,
        )
    return approval_id


def test_a_proposer_stored_in_its_raw_typed_form_is_still_recognized(
    conn: Connection, config: EngineConfig
) -> None:
    """`approvals.create` writes `proposed_by` exactly as its caller
    passed it -- no normalization at write time, by design (it is
    whatever the caller's own authentication handed over). A row created
    today already looks like a "pre-fix" or "upgraded from 0.10.2" row in
    this one respect. Presenting a differently-cased, padded form of the
    same identity must still be refused as the proposer's own vote."""
    _two_person(conn)
    approval_id = _propose(conn, config, proposed_by="Alice")
    row = conn.execute("SELECT proposed_by FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["proposed_by"] == "Alice"  # stored exactly as typed, raw

    with pytest.raises(ApprovalError, match="cannot approve it"):
        approvals.cas_approve(conn, approval_id, " alice ", FROZEN_NOW)


def test_an_approver_stored_in_its_raw_typed_form_is_still_recognized_as_a_duplicate(
    conn: Connection, config: EngineConfig
) -> None:
    """Simulates a row written before the normalization fix existed (or
    migrated in from 0.10.2): `approvers_json` planted directly, holding
    the identity exactly as it was typed, bypassing `cas_approve`'s own
    writer (which would store the normalized form). A later vote from a
    differently-cased, padded presentation of the SAME identity must
    still be recognized as the same person, not a second approver."""
    _two_person(conn)
    approval_id = _propose(conn, config, proposed_by="agent-7")
    conn.execute(
        "UPDATE approvals SET approvers_json=? WHERE id=?",
        ('["Bob"]', approval_id),
    )
    row = conn.execute("SELECT approvers_json FROM approvals WHERE id=?", (approval_id,)).fetchone()
    assert row["approvers_json"] == '["Bob"]'  # planted raw, as typed

    with pytest.raises(ApprovalError, match="already approved"):
        approvals.cas_approve(conn, approval_id, " BOB ", FROZEN_NOW)
