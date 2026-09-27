"""0.8.0's budget vocabulary switch: a row sealed before it is never rewritten,
and every reader of `actions_audit` handles both the old names and the new
ones. `cap_value`/`cap_rate` and the seven-field pre-0.8.0 `budget` object are
never emitted again after this switch -- the fixtures below build rows in
that exact old shape directly, the same way a store upgraded from before the
switch would already hold them, without needing an old commit checked out
to produce one.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from sqlite3 import Connection

import pytest

from onedoor.decision_digest import decision_digest
from onedoor.decision_ref import MATCHES, check
from onedoor.export import export_rows
from onedoor.guardrail import audit, chain
from onedoor.guardrail.decision import decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import CheckId, Decision, PolicyDecision, Tier
from onedoor.guardrail.receipt import Status, fetch_decision, verify_decision
from onedoor.store.db import run_migrations, tx
from tests.conftest import FROZEN_NOW, make_request


def _unstamped_cap_denial(conn: Connection, *, reason_code: str, request_id: str) -> int:
    """A row exactly as pre-0.4.0 code wrote one: no `protocol` column at all (it did
    not exist yet), so it reads back NULL -- the absent-value rule's `aadp/0.1`. A raw
    INSERT, not `audit._row_values`, because that helper always stamps the CURRENT
    protocol; this fixture's whole point is a row with none."""
    conn.execute(
        "INSERT INTO actions_audit (request_id, kind, action_type, source, params_json,"
        " decision, reason_code, nominal_tier, effective_tier, created_at)"
        " VALUES (?, 'decision', 'demo.legacy_spend', 'ui', '{}', 'denied', ?, 2, 2, ?)",
        (request_id, reason_code, FROZEN_NOW.isoformat()),
    )
    return int(
        conn.execute("SELECT id FROM actions_audit WHERE request_id=?", (request_id,)).fetchone()[
            "id"
        ]
    )


def _undo_migration_0024(conn: Connection) -> None:
    """Make it as if `0024_vocabulary_epochs.sql` had not run yet, on a
    connection where it already has (the `conn` fixture's database is fully
    migrated before any test body runs). Not a hypothetical: an operator's
    real database is exactly this shape at the moment they upgrade -- rows
    already written, the migration about to run for the first time -- and
    that is the only way to test what the migration itself records rather
    than what a fresh, empty database trivially would.

    Dropping the table, not just its `schema_migrations` row: the migration's
    own `CREATE TABLE IF NOT EXISTS` would otherwise no-op against a table
    that still exists, and its `INSERT` would then collide with the rows
    already in it.
    """
    conn.execute("DELETE FROM schema_migrations WHERE version LIKE '0024%'")
    conn.execute("DROP TABLE IF EXISTS vocabulary_epochs")


OLD_VALUE_BUDGET_JSON = json.dumps(
    {
        "dimension": "value",
        "unit": "EUR",
        "window": "day",
        "limit": "10",
        "consumed": "9.5",
        "remaining": "0.5",
        "window_resets_at": "2026-07-05T22:00:00Z",
    },
    sort_keys=True,
    separators=(",", ":"),
)
OLD_RATE_BUDGET_JSON = json.dumps(
    {
        "dimension": "rate",
        "unit": "calls",
        "window": "day",
        "limit": "1",
        "consumed": "1",
        "remaining": "0",
        "window_resets_at": "2026-07-05T22:00:00Z",
    },
    sort_keys=True,
    separators=(",", ":"),
)


def _legacy_cap_denial(
    conn: Connection,
    *,
    reason_code: str,
    budget_json: str,
    action_type: str = "demo.legacy_spend",
    now: datetime = FROZEN_NOW,
) -> int:
    """A `decision` row shaped exactly as the pre-0.8.0 code path wrote one:
    the deprecated reason string, and `budget_json` in the seven-field shape
    that predates `name`. Built by reusing `audit._row_values` for every
    column an old row and a new one share, then overwriting only the two
    that actually changed -- so everything else (provenance, the policy
    stamp, the protocol string) is exactly what a real row carries, not a
    hand-typed guess at it.
    """
    request = make_request(action_type, {}, now=now)
    decision = PolicyDecision(
        decision=Decision.DENIED,
        effective_tier=Tier.AUTO_CAPPED,
        nominal_tier=Tier.AUTO_CAPPED,
        reason_code=CheckId.BUDGET_EXHAUSTED,  # placeholder; overwritten below
        detail="legacy fixture: a cap reached before the 0.8.0 switch",
    )
    trace_json = json.dumps(
        [
            {
                "check": reason_code,
                "rule": "budget caps (rate and/or value) must not be exceeded by this action",
                "condition": "already-reserved + this action's cost <= the declared cap",
                "value": "legacy fixture",
                "result": "fail",
            }
        ],
        separators=(",", ":"),
    )
    values = audit._row_values(conn, request, decision, kind="decision", now=now)
    values["reason_code"] = reason_code
    values["budget_json"] = budget_json
    values["evaluation_trace_json"] = trace_json
    if audit.chaining_on(conn):
        audit._stamp_chain(conn, values, audit._read_tip(conn))
    return audit._insert(conn, values)


def test_old_rows_still_verify_after_new_ones_are_written(
    conn: Connection, config: EngineConfig
) -> None:
    """A mixed store: a decision made before the switch, and one made after,
    side by side. The legacy row's own evidence -- its budget object, parsed
    under the shape it was actually written in -- still holds together;
    neither row is reinterpreted as the other's shape.

    `reason_vocabulary` still reads `failed` here, not `retired_vocabulary` --
    NOT because a retired code is categorically a
    failure (see `test_a_retired_code_before_its_own_retirement_is_not_
    failed` below, which is the opposite outcome for a DIFFERENT retired
    code), but because `cap_value`/`cap_rate` retired at 0.8.0 without a
    protocol bump: every row since 0.4.0, this fixture's included, carries
    the identical `aadp/0.2` stamp, so nothing on the row lets this check
    tell "written in 2026-05, honestly" from "forged today using an old
    word". See `RETIRED_BEFORE` in `receipt.py`.
    """
    with tx(conn):
        legacy_id = _legacy_cap_denial(
            conn, reason_code="cap_value", budget_json=OLD_VALUE_BUDGET_JSON
        )

    decide_and_reserve(
        make_request("demo.capped", {}), conn=conn, config=config, now=FROZEN_NOW
    )  # an ordinary new-vocabulary decision, unrelated to the legacy row

    legacy_verification = verify_decision(conn, fetch_decision(conn, legacy_id))
    budget_check = legacy_verification.by_name("budget_object")
    assert budget_check.status is Status.VERIFIED, budget_check.detail
    reason_check = legacy_verification.by_name("reason_vocabulary")
    assert reason_check.status is Status.FAILED, (
        f"a retired reason code failing this specific check is expected; got {reason_check.status}"
    )

    legacy_row = conn.execute(
        "SELECT reason_code, budget_json FROM actions_audit WHERE id=?", (legacy_id,)
    ).fetchone()
    assert legacy_row["reason_code"] == "cap_value"
    assert json.loads(legacy_row["budget_json"]) == json.loads(OLD_VALUE_BUDGET_JSON)


def test_a_retired_code_before_its_own_retirement_is_not_failed(conn: Connection) -> None:
    """`cap_eur_day` retired at 0.4.0,
    which is also where the `protocol` column was born. A row with none -- read as
    `aadp/0.1` by the absent-value rule -- can only predate 0.4.0, so it can only
    predate this code's own retirement: a real, row-carried marker, not an inference
    from when someone happened to look.

    An operator who upgrades must not see this honest, contemporaneous record turn
    into a failed verification -- it gets its own state instead.
    """
    audit_id = _unstamped_cap_denial(conn, reason_code="cap_eur_day", request_id="pre-0.4.0")
    row = conn.execute("SELECT protocol FROM actions_audit WHERE id=?", (audit_id,)).fetchone()
    assert row["protocol"] is None, "the fixture must genuinely carry no protocol stamp"

    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("reason_vocabulary")
    assert check.status is Status.RETIRED_VOCABULARY, (
        f"a code retired after this row was written must not read failed; got {check.status}"
    )
    assert check.status is not Status.FAILED


def test_a_retired_code_after_its_own_retirement_stays_failed(
    conn: Connection, config: EngineConfig
) -> None:
    """The SAME retired code (`cap_eur_day`), on a row
    whose own protocol stamp is `aadp/0.2` -- current, i.e. from 0.4.0 or later, long
    after `cap_eur_day` retired. The two cases differ by WHEN the row was written,
    never by the code alone: same string, opposite verdict, because this row's own
    marker proves it could not have been an honest record of that code.
    """
    decide_and_reserve(make_request("demo.capped", {}), conn=conn, config=config, now=FROZEN_NOW)
    audit_id = int(
        conn.execute("SELECT id FROM actions_audit ORDER BY id DESC LIMIT 1").fetchone()["id"]
    )
    with tx(conn):
        conn.execute("DROP TRIGGER actions_audit_no_update")
        conn.execute("UPDATE actions_audit SET reason_code=? WHERE id=?", ("cap_eur_day", audit_id))
        conn.execute(
            "CREATE TRIGGER actions_audit_no_update BEFORE UPDATE ON actions_audit "
            "BEGIN SELECT RAISE(ABORT, 'actions_audit is append-only: UPDATE forbidden'); END"
        )
    row = conn.execute("SELECT protocol FROM actions_audit WHERE id=?", (audit_id,)).fetchone()
    assert row["protocol"] == "aadp/0.2", "the fixture must genuinely carry the current stamp"

    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("reason_vocabulary")
    assert check.status is Status.FAILED, (
        f"a retired code on a row that postdates its retirement must fail; got {check.status}"
    )


def test_a_fresh_database_leaves_nothing_to_retire(conn: Connection) -> None:
    """`cap_value`/`cap_rate` retired without a protocol bump, so the only
    marker distinguishing an honest pre-0.8.0 row from a post-0.8.0 forgery
    is the upgrade boundary migration `0024` records -- and on a database
    that never held either code, that boundary is honestly nothing: `0` is
    not a real audit id, so no row could ever read at-or-before it."""
    rows = {
        r["code"]: (r["retired_in_version"], r["last_audit_id_before"])
        for r in conn.execute(
            "SELECT code, retired_in_version, last_audit_id_before FROM vocabulary_epochs"
        )
    }
    assert rows == {"cap_value": ("0.8.0", 0), "cap_rate": ("0.8.0", 0)}


def test_07_style_rows_survive_the_upgrade_as_retired_vocabulary(conn: Connection) -> None:
    """The scenario item 2 is about, not a synthetic stand-in for it: a real
    database already holding `cap_value`/`cap_rate` denials from before
    `0.8.0`, migrating forward. `_undo_migration_0024` puts this connection's
    database back to exactly that state -- rows already written, `0024`
    about to run for the first time -- then `run_migrations` plays the
    upgrade forward for real, computing the boundary against the rows that
    are actually there."""
    with tx(conn):
        _undo_migration_0024(conn)
        value_id = _legacy_cap_denial(
            conn, reason_code="cap_value", budget_json=OLD_VALUE_BUDGET_JSON
        )
        rate_id = _legacy_cap_denial(conn, reason_code="cap_rate", budget_json=OLD_RATE_BUDGET_JSON)

    applied = run_migrations(conn)
    assert any("0024" in name for name in applied), f"0024 did not re-apply: {applied}"

    epoch = {
        r["code"]: r["last_audit_id_before"]
        for r in conn.execute("SELECT code, last_audit_id_before FROM vocabulary_epochs")
    }
    assert epoch["cap_value"] >= value_id
    assert epoch["cap_rate"] >= rate_id

    for audit_id, code in ((value_id, "cap_value"), (rate_id, "cap_rate")):
        check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("reason_vocabulary")
        assert check.status is Status.RETIRED_VOCABULARY, (
            f"{code} row {audit_id}: expected retired_vocabulary, got {check.status}"
        )


def test_a_cap_value_row_forced_in_after_the_migration_still_fails(conn: Connection) -> None:
    """The other half of the same distinction: a `cap_value` row written
    (or forged) on THIS database, after `0024` already ran -- so its id is
    necessarily past the boundary the migration recorded -- must still read
    `failed`, exactly as before this migration existed."""
    with tx(conn):
        audit_id = _legacy_cap_denial(
            conn, reason_code="cap_value", budget_json=OLD_VALUE_BUDGET_JSON
        )

    check = verify_decision(conn, fetch_decision(conn, audit_id)).by_name("reason_vocabulary")
    assert check.status is Status.FAILED, (
        f"a cap_value row written after the recorded boundary must fail; got {check.status}"
    )


def test_vocabulary_epochs_refuses_update_and_delete(conn: Connection) -> None:
    """The boundary is only honest if nothing after the migration can move
    it -- the same append-only shape `actions_audit` already has, and for
    the same reason."""
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE vocabulary_epochs SET last_audit_id_before=999 WHERE code='cap_value'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM vocabulary_epochs WHERE code='cap_value'")


def test_sabotage_a_zeroed_epoch_makes_the_upgrade_test_fail(conn: Connection) -> None:
    """Proves `test_07_style_rows_survive_the_upgrade_as_retired_vocabulary`
    actually discriminates on `last_audit_id_before`'s real value, rather
    than passing regardless of it: force the SAME legacy row's boundary back
    to `0` -- as if the migration had run on an empty database, the way a
    fresh install's does -- and the row must stop reading
    `retired_vocabulary`. Bypasses the table's own append-only trigger the
    same way the existing `..._stays_failed` test bypasses `actions_audit`'s,
    to reach a state nothing in the shipped product can ever legitimately
    create."""
    with tx(conn):
        _undo_migration_0024(conn)
        value_id = _legacy_cap_denial(
            conn, reason_code="cap_value", budget_json=OLD_VALUE_BUDGET_JSON
        )
    run_migrations(conn)

    before = verify_decision(conn, fetch_decision(conn, value_id)).by_name("reason_vocabulary")
    assert before.status is Status.RETIRED_VOCABULARY, (
        "fixture setup did not reach the state to sabotage"
    )

    with tx(conn):
        conn.execute("DROP TRIGGER vocabulary_epochs_no_update")
        conn.execute("UPDATE vocabulary_epochs SET last_audit_id_before=0 WHERE code='cap_value'")
        conn.execute(
            "CREATE TRIGGER vocabulary_epochs_no_update BEFORE UPDATE ON vocabulary_epochs "
            "BEGIN SELECT RAISE(ABORT, "
            "'vocabulary_epochs is append-only: UPDATE forbidden'); END"
        )

    after = verify_decision(conn, fetch_decision(conn, value_id)).by_name("reason_vocabulary")
    assert after.status is Status.FAILED, (
        "sabotage failed to reproduce the regression: a zeroed epoch must make "
        f"this row read failed again; got {after.status}"
    )


def test_the_chain_verifies_across_the_switch(conn: Connection, config: EngineConfig) -> None:
    """A legacy-shaped row and a current-shaped row, chained together. The
    walker must not treat the vocabulary change as a break -- chaining hashes
    the row's bytes, not its meaning."""
    with tx(conn):
        chain.enable(conn)
    with tx(conn):
        _legacy_cap_denial(conn, reason_code="cap_rate", budget_json=OLD_RATE_BUDGET_JSON)

    decide_and_reserve(make_request("demo.capped", {}), conn=conn, config=config, now=FROZEN_NOW)

    report = chain.verify_chain(conn)
    assert report.sound, report.broken


def test_export_writes_a_legacy_row_byte_for_byte(conn: Connection) -> None:
    """The export never reinterprets a column -- a legacy row's `reason_code`
    and `budget_json` come out exactly as stored, not translated to the
    current vocabulary."""
    with tx(conn):
        legacy_id = _legacy_cap_denial(
            conn, reason_code="cap_value", budget_json=OLD_VALUE_BUDGET_JSON
        )
    exported = {int(row["id"]): row for row in export_rows(conn)}
    row = exported[legacy_id]
    assert row["reason_code"] == "cap_value"
    assert row["budget_json"] == OLD_VALUE_BUDGET_JSON


def test_a_mixed_export_carries_old_and_new_rows_side_by_side(
    conn: Connection, config: EngineConfig
) -> None:
    with tx(conn):
        legacy_id = _legacy_cap_denial(
            conn, reason_code="cap_rate", budget_json=OLD_RATE_BUDGET_JSON
        )
    new_result = decide_and_reserve(
        make_request("demo.capped", {}), conn=conn, config=config, now=FROZEN_NOW
    )
    exported = {int(row["id"]): row for row in export_rows(conn)}
    assert exported[legacy_id]["reason_code"] == "cap_rate"
    assert exported[int(new_result.intent_audit_id)]["reason_code"] in {  # type: ignore[union-attr,arg-type]
        "passed",
        "budget_exhausted",
        "rate_exhausted",
    }


def test_decision_ref_checking_still_matches_a_reference_issued_before_the_switch(
    conn: Connection,
) -> None:
    """`decision_digest` canonicalizes whatever a row actually holds -- it was
    never vocabulary-aware, so a reference computed over a legacy row's exact
    bytes must still read MATCHES against a fresh export of that same row."""
    with tx(conn):
        legacy_id = _legacy_cap_denial(
            conn, reason_code="cap_value", budget_json=OLD_VALUE_BUDGET_JSON
        )
    row = conn.execute("SELECT * FROM actions_audit WHERE id=?", (legacy_id,)).fetchone()
    digest = decision_digest(row)

    exported = [dict(r) for r in export_rows(conn)]
    ref = {
        "format": "onedoor-decision-ref/1",
        "request_id": row["request_id"],
        "decision_digest": digest,
        "verdict": "deny",
        "issuer": "https://onedoor.example/legacy-check",
    }
    result = check(ref, exported)
    assert result.status == MATCHES, result.detail
