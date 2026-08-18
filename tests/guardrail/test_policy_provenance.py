"""Policy provenance — can a past decision still be re-derived after a policy edit?

AADP section 10: the evidence record MUST be sufficient to re-derive every verdict
it contains, given the policy version in force at the time. The policy table is
upserted in place with no history, so without a recorded version the answer was no:
edit the policy and every earlier decision becomes uncheckable.
"""

from __future__ import annotations

import json
from decimal import Decimal
from sqlite3 import Connection
from uuid import uuid4

import pytest
from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_raw
from onedoor.guardrail.models import Bounds, NumericBound, Policy, Tier

from tests.conftest import FROZEN_NOW


def _policy(max_amount: float) -> Policy:
    return Policy(
        action_type="prov.pay",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="prov.reverse",
        bounds=Bounds(
            numeric={"amount": NumericBound(min=0, max=max_amount)},
            required=["amount"],
            strict_params=False,
        ),
    )


def _call(conn: Connection, config: object, amount: int):
    return decide_raw(
        {
            "request_id": str(uuid4()),
            "action_type": "prov.pay",
            "params": {"amount": amount},
            "source": "llm",
            "rationale": "provenance",
            "cost_eur": Decimal(amount),
            "created_at": FROZEN_NOW,
        },
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )


def _versions(conn: Connection) -> list[str]:
    return [r["policy_version"] for r in conn.execute(
        "SELECT policy_version FROM actions_audit ORDER BY id"
    )]


def test_every_audit_row_carries_a_policy_version(conn: Connection, config: object) -> None:
    policy_loader.upsert(conn, _policy(100))
    assert isinstance(_call(conn, config, 50), PermittedIntent)
    stamps = _versions(conn)
    assert stamps and all(s for s in stamps), "an audit row with no policy version"


def test_editing_policy_changes_the_recorded_version(conn: Connection, config: object) -> None:
    policy_loader.upsert(conn, _policy(100))
    _call(conn, config, 50)
    before = policy_loader.current_version(conn)

    policy_loader.upsert(conn, _policy(10))  # tighten the bound
    after = policy_loader.current_version(conn)
    assert before != after, "editing policy did not produce a new version"

    _call(conn, config, 50)  # now denied under the new rules
    stamps = _versions(conn)
    assert stamps[0] == before
    assert stamps[-1] == after


def test_reverting_an_edit_restores_the_original_version(conn: Connection, config: object) -> None:
    """A hash is content, not a counter: the same rules must yield the same version."""
    policy_loader.upsert(conn, _policy(100))
    original = policy_loader.current_version(conn)
    policy_loader.upsert(conn, _policy(10))
    assert policy_loader.current_version(conn) != original
    policy_loader.upsert(conn, _policy(100))
    assert policy_loader.current_version(conn) == original


def test_the_recorded_snapshot_re_derives_the_decision(conn: Connection, config: object) -> None:
    """The stamp is only useful if the rules behind it can actually be recovered."""
    policy_loader.upsert(conn, _policy(100))
    permitted = _call(conn, config, 50)
    assert isinstance(permitted, PermittedIntent)
    stamped = _versions(conn)[0]

    policy_loader.upsert(conn, _policy(10))  # the rules of the time no longer apply

    snapshot = policy_loader.snapshot_for(conn, stamped)
    assert snapshot is not None, "policy set behind a decision was not recoverable"
    rules = json.loads(snapshot)
    row = next(p for p in rules["policies"] if p["action_type"] == "prov.pay")
    bounds = json.loads(row["bounds_json"])
    assert bounds["numeric"]["amount"]["max"] == 100, (
        "recovered rules do not match those in force when the decision was made"
    )


def test_policy_versions_is_append_only(conn: Connection) -> None:
    policy_loader.upsert(conn, _policy(100))
    version = policy_loader.current_version(conn)
    with pytest.raises(Exception, match="append-only"):
        conn.execute("UPDATE policy_versions SET snapshot_json='{}' WHERE version_hash=?",
                     (version,))
    with pytest.raises(Exception, match="append-only"):
        conn.execute("DELETE FROM policy_versions WHERE version_hash=?", (version,))


def test_edit_act_revert_leaves_a_trace(conn: Connection, config: object) -> None:
    """The insider case: loosen policy, act, tighten it back.

    The pointer returns to the original hash, but the decision made in between is
    stamped with the loosened version, which is still recorded and unrewritable.
    """
    policy_loader.upsert(conn, _policy(10))
    tight = policy_loader.current_version(conn)

    policy_loader.upsert(conn, _policy(10_000))  # loosen
    loose = policy_loader.current_version(conn)
    assert isinstance(_call(conn, config, 5_000), PermittedIntent)

    policy_loader.upsert(conn, _policy(10))  # put it back
    assert policy_loader.current_version(conn) == tight

    stamps = _versions(conn)
    assert loose in stamps, "the permissive window left no trace"
    recovered = json.loads(policy_loader.snapshot_for(conn, loose))
    row = next(p for p in recovered["policies"] if p["action_type"] == "prov.pay")
    assert json.loads(row["bounds_json"])["numeric"]["amount"]["max"] == 10_000
