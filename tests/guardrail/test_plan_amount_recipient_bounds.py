"""A plan that names no `amount_param` (or no `recipient_param`) for an
action whose policy bounds that amount or recipient is an open-ended
authorization, approved against a ceiling it never applies -- the amount
(or recipient) is never read, so the plan's own ceiling never spends and
never refuses. Closed at both ends: `plans.propose` refuses to create such
a plan in the first place, and `plan_ref.resolve_match` refuses to match
one even if its covered policy only came to bound that amount or recipient
*after* the plan was already proposed and approved -- a plan cannot open a
gap a current policy would not have allowed.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path
from sqlite3 import Connection

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import plan_ref, plans, policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.errors import PlanError
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ApprovalPolicy,
    Bounds,
    Caps,
    Decision,
    NumericBound,
    Policy,
    Tier,
)
from onedoor.service.app import create_app
from tests.conftest import FROZEN_NOW, make_request

ROOT = Path(__file__).parent.parent.parent
PAY = "demo.plan_bounds"
EXPIRES_IN = FROZEN_NOW.replace(year=FROZEN_NOW.year + 1)


def _policy(
    conn: Connection,
    *,
    action_type: str = PAY,
    cost_param: str | None = "amount_eur",
    two_person_above_eur: Decimal | None = Decimal("1000"),
    enum: dict[str, list[str]] | None = None,
    strict_params: bool = False,
    eur_day: Decimal | None = None,
    numeric: dict[str, NumericBound] | None = None,
) -> None:
    policy_loader.upsert(
        conn,
        Policy(
            action_type=action_type,
            tier=Tier.CONFIRM,
            dry_run=False,
            bounds=Bounds(
                required=["amount_eur", "payee"],
                enum=enum or {},
                numeric=numeric or {},
                strict_params=strict_params,
            ),
            caps=Caps(eur_day=eur_day),
            cost_param=cost_param,
            approval=(
                ApprovalPolicy(two_person_above_eur=two_person_above_eur)
                if two_person_above_eur is not None
                else None
            ),
        ),
    )


# --- refused at proposal when no amount bound exists ---------------------------------


def test_propose_refuses_a_plan_with_no_amount_param_when_the_policy_bounds_amount(
    conn: Connection,
) -> None:
    _policy(conn)
    with pytest.raises(PlanError, match="amount_param"):
        plans.propose(
            conn,
            "alice",
            {PAY: {"recipient_param": "payee"}},
            count_ceiling=10,
            amount_ceiling=Decimal(10),
            recipients=["acme"],
            expires_at=EXPIRES_IN,
            now=FROZEN_NOW,
        )
    assert conn.execute("SELECT count(*) FROM plans").fetchone()[0] == 0


def test_propose_refuses_a_plan_with_no_recipient_param_when_the_policy_bounds_recipients(
    conn: Connection,
) -> None:
    _policy(conn, enum={"payee": ["acme"]})
    with pytest.raises(PlanError, match="recipient_param"):
        plans.propose(
            conn,
            "alice",
            {PAY: {"amount_param": "amount_eur"}},
            count_ceiling=10,
            amount_ceiling=Decimal(1000),
            recipients=["acme"],
            expires_at=EXPIRES_IN,
            now=FROZEN_NOW,
        )
    assert conn.execute("SELECT count(*) FROM plans").fetchone()[0] == 0


def test_propose_allows_a_fully_declared_plan(conn: Connection) -> None:
    _policy(conn, enum={"payee": ["acme"]})
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "amount_eur", "recipient_param": "payee"}},
        count_ceiling=10,
        amount_ceiling=Decimal(1000),
        recipients=["acme"],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    assert plan_id > 0


def test_propose_allows_no_amount_param_when_the_policy_does_not_bound_amount(
    conn: Connection,
) -> None:
    """No `cost_param`, no euro cap, no two-person threshold -- nothing on
    this policy bounds an amount at all, so a plan naming no `amount_param`
    is not an open-ended authorization against anything: there is nothing
    for it to be unbounded against."""
    _policy(conn, cost_param=None, two_person_above_eur=None)
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {}},
        count_ceiling=10,
        amount_ceiling=Decimal(10),
        recipients=[],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    assert plan_id > 0


# --- "any recipient" in those exact words, where no bound exists -------------------


def test_a_plan_with_no_recipient_bound_records_any_recipient_literally(
    conn: Connection,
) -> None:
    _policy(conn)  # no bounds.enum -- no recipient bound anywhere
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "amount_eur"}},
        count_ceiling=10,
        amount_ceiling=Decimal(1000),
        recipients=[],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    row = conn.execute("SELECT recipients_json FROM plans WHERE id=?", (plan_id,)).fetchone()
    assert row["recipients_json"] == '["any recipient"]'
    assert plans.recipients_text([]) == "any recipient"
    assert plans.recipients_text(["acme"]) == "acme"


# --- items 2 and 4: the match-time backstop, exercised at all three entry points ---


def _propose_while_unbounded_then_tighten(
    conn: Connection, *, amount: bool, action_type: str = PAY
) -> int:
    """The retroactive-gap shape: proposed while the covered policy bounded
    nothing, correctly naming no `amount_param`/`recipient_param`, which is
    permitted; the policy is then edited to bound it. `resolve_match`
    must not let the old plan go on matching as though nothing changed."""
    _policy(conn, action_type=action_type, cost_param=None, two_person_above_eur=None)
    plan_id = plans.propose(
        conn,
        "alice",
        {action_type: {} if amount else {"amount_param": "amount_eur"}},
        count_ceiling=10,
        amount_ceiling=Decimal(10),
        recipients=[],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    if amount:
        # now bounds amount (cost_param + two-person above 1000)
        _policy(conn, action_type=action_type)
    else:
        _policy(conn, action_type=action_type, enum={"payee": ["acme"]})  # now bounds recipients
    return plan_id


def test_resolve_match_refuses_a_plan_the_current_policy_now_bounds_by_amount(
    conn: Connection, config: EngineConfig
) -> None:
    plan_id = _propose_while_unbounded_then_tighten(conn, amount=True)
    for _ in range(3):
        result = decide_and_reserve(
            make_request(PAY, {"amount_eur": Decimal(5000), "payee": "acme"}).model_copy(
                update={"plan_ref": plan_id}
            ),
            conn=conn,
            config=config,
            now=FROZEN_NOW,
        )
        assert not isinstance(result, PermittedIntent)
        assert result.decision.decision == Decision.PROPOSED
        assert result.decision.plan_ref is None
    row = conn.execute(
        "SELECT consumed_count, consumed_amount FROM plans WHERE id=?", (plan_id,)
    ).fetchone()
    assert row["consumed_count"] == 0
    assert Decimal(str(row["consumed_amount"])) == Decimal(0)


def test_resolve_match_refuses_a_plan_the_current_policy_now_bounds_by_recipient(
    conn: Connection, config: EngineConfig
) -> None:
    plan_id = _propose_while_unbounded_then_tighten(conn, amount=False)
    result = decide_and_reserve(
        make_request(PAY, {"amount_eur": Decimal(10), "payee": "acme"}).model_copy(
            update={"plan_ref": plan_id}
        ),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.plan_ref is None


def test_resolve_match_refuses_the_same_plan_at_the_http_entry_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    db_path = tempfile.mktemp(suffix=".db")
    app = create_app(db_path=db_path, policies=str(ROOT / "config" / "policies.yaml"))
    engine = app.state.engine  # type: ignore[attr-defined]
    plan_id = _propose_while_unbounded_then_tighten(engine.conn, amount=True)
    client = TestClient(app)
    r = client.post(
        "/v1/decide",
        json={
            "action_type": PAY,
            "params": {"amount_eur": 5000, "payee": "acme"},
            "plan_ref": plan_id,
        },
        headers={"Authorization": "Bearer dkey"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "proposed"
    assert body["plan_ref"] is None
    row = engine.conn.execute("SELECT consumed_count FROM plans WHERE id=?", (plan_id,)).fetchone()
    assert row["consumed_count"] == 0


def test_resolve_match_refuses_the_same_plan_through_the_mcp_proxy(tmp_path: Path) -> None:
    import io
    import json
    import sys

    from onedoor.mcp.proxy import PLAN_REF_META, Proxy

    fixtures = Path(__file__).parent.parent / "mcp" / "fixtures"
    downstream = f'"{sys.executable}" -m tests.mcp.fixtures.mismatched_demo_server'
    proxy = Proxy(
        downstream,
        ROOT / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
        mapping=fixtures / "mismatched_mapping.yaml",
    )
    send_payment = "mcp.send_payment"
    plan_id = _propose_while_unbounded_then_tighten(
        proxy.conn, amount=True, action_type=send_payment
    )

    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "wire_transfer",
            "arguments": {"to": "acme", "amount": {"value": 5000}},
            "_meta": {PLAN_REF_META: plan_id},
        },
    }
    out = io.StringIO()
    proxy.serve(io.StringIO(json.dumps(msg) + "\n"), out)
    reply = dict(json.loads(out.getvalue()))
    text = str(reply["result"]["content"][0]["text"])
    assert reply["result"]["isError"] is True
    assert "requires approval" in text
    assert "has not been forwarded" in text
    row = proxy.conn.execute("SELECT consumed_count FROM plans WHERE id=?", (plan_id,)).fetchone()
    assert row["consumed_count"] == 0


# --- amount_param must be the field the policy reads, not merely present ---------
#
# A reviewer's own attack: a plan naming `amount_param="fee"` against a policy
# that reads its real cost from `amount_eur` -- the first version of this check
# only asked whether `amount_param` was present, never whether it was the field
# the policy actually measures. A request carrying both an incidental `fee` (or
# `fee_eur`) field AND the real `amount_eur` field matched the plan's own ceiling
# against the small, irrelevant field while the real 5000 transfer went completely
# unread by it -- at the library, through `/v1/decide`, and through the MCP
# gateway, `strict_params` or not.


def _plant_fee_mismatched_plan(
    conn: Connection, *, action_type: str, fee_field: str, strict_params: bool
) -> int:
    """Simulates a plan already approved under the first, buggy version of
    `_check_action_spec` (present-only, never checked against `cost_param`):
    proposed while the policy bounded nothing at all, honestly naming
    `amount_param=fee_field` (nothing to be wrong about yet), approved, and
    only THEN does the policy settle into its real shape -- `cost_param
    ="amount_eur"`, with `fee_field` itself declared as an allowed numeric
    param so a real request may carry it alongside the real amount."""
    _policy(
        conn,
        action_type=action_type,
        cost_param=None,
        two_person_above_eur=None,
        strict_params=strict_params,
        numeric={fee_field: NumericBound()} if strict_params else None,
    )
    plan_id = plans.propose(
        conn,
        "alice",
        {action_type: {"amount_param": fee_field}},
        count_ceiling=10,
        amount_ceiling=Decimal(10),
        recipients=[],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    _policy(
        conn,
        action_type=action_type,
        cost_param="amount_eur",
        two_person_above_eur=Decimal("1000"),
        strict_params=strict_params,
        numeric={fee_field: NumericBound()} if strict_params else None,
    )
    return plan_id


@pytest.mark.parametrize("fee_field,strict", [("fee", False), ("fee_eur", True)])
def test_propose_refuses_ne7_stop_the_fee_plan(
    fee_field: str, strict: bool, conn: Connection
) -> None:
    """ne7_stop / ne7_stop_b: proposing the mismatched plan from scratch,
    against the policy's REAL shape, is refused outright -- the attack
    never gets as far as being approved in the first place."""
    _policy(
        conn,
        cost_param="amount_eur",
        strict_params=strict,
        numeric={fee_field: NumericBound()} if strict else None,
    )
    with pytest.raises(PlanError, match="amount_param"):
        plans.propose(
            conn,
            "alice",
            {PAY: {"amount_param": fee_field}},
            count_ceiling=10,
            amount_ceiling=Decimal(10),
            recipients=[],
            expires_at=EXPIRES_IN,
            now=FROZEN_NOW,
        )
    assert conn.execute("SELECT count(*) FROM plans").fetchone()[0] == 0


@pytest.mark.parametrize("fee_field,strict", [("fee", False), ("fee_eur", True)])
def test_ne7_stop_refused_at_match_through_the_library(
    fee_field: str, strict: bool, conn: Connection, config: EngineConfig
) -> None:
    plan_id = _plant_fee_mismatched_plan(
        conn, action_type=PAY, fee_field=fee_field, strict_params=strict
    )
    result = decide_and_reserve(
        make_request(
            PAY, {"amount_eur": Decimal(5000), "payee": "acme", fee_field: Decimal(1)}
        ).model_copy(update={"plan_ref": plan_id}),
        conn=conn,
        config=config,
        now=FROZEN_NOW,
    )
    assert not isinstance(result, PermittedIntent)
    assert result.decision.decision == Decision.PROPOSED
    assert result.decision.plan_ref is None
    row = conn.execute(
        "SELECT consumed_count, consumed_amount FROM plans WHERE id=?", (plan_id,)
    ).fetchone()
    assert row["consumed_count"] == 0
    assert Decimal(str(row["consumed_amount"])) == Decimal(0)


@pytest.mark.parametrize("fee_field,strict", [("fee", False), ("fee_eur", True)])
def test_ne7_stop_refused_at_the_http_entry_point(
    fee_field: str, strict: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ONEDOOR_DECIDE_KEYS", "dkey")
    db_path = tempfile.mktemp(suffix=".db")
    app = create_app(db_path=db_path, policies=str(ROOT / "config" / "policies.yaml"))
    engine = app.state.engine  # type: ignore[attr-defined]
    plan_id = _plant_fee_mismatched_plan(
        engine.conn, action_type=PAY, fee_field=fee_field, strict_params=strict
    )
    client = TestClient(app)
    r = client.post(
        "/v1/decide",
        json={
            "action_type": PAY,
            "params": {"amount_eur": 5000, "payee": "acme", fee_field: 1},
            "plan_ref": plan_id,
        },
        headers={"Authorization": "Bearer dkey"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "proposed"
    assert body["plan_ref"] is None
    row = engine.conn.execute("SELECT consumed_count FROM plans WHERE id=?", (plan_id,)).fetchone()
    assert row["consumed_count"] == 0


@pytest.mark.parametrize("fee_field,strict", [("fee", False), ("fee_eur", True)])
def test_ne7_stop_refused_through_the_mcp_proxy(
    fee_field: str, strict: bool, tmp_path: Path
) -> None:
    import io
    import json
    import sys

    from onedoor.mcp.proxy import PLAN_REF_META, Proxy

    fixtures = Path(__file__).parent.parent / "mcp" / "fixtures"
    downstream = f'"{sys.executable}" -m tests.mcp.fixtures.mismatched_demo_server'
    proxy = Proxy(
        downstream,
        ROOT / "config" / "mcp_policies.yaml",
        str(tmp_path / "proxy.db"),
        mapping=fixtures / "mismatched_mapping.yaml",
    )
    send_payment = "mcp.send_payment"
    plan_id = _plant_fee_mismatched_plan(
        proxy.conn, action_type=send_payment, fee_field=fee_field, strict_params=strict
    )

    msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "wire_transfer",
            "arguments": {"to": "acme", "amount": {"value": 5000}, fee_field: 1},
            "_meta": {PLAN_REF_META: plan_id},
        },
    }
    out = io.StringIO()
    proxy.serve(io.StringIO(json.dumps(msg) + "\n"), out)
    reply = dict(json.loads(out.getvalue()))
    text = str(reply["result"]["content"][0]["text"])
    assert reply["result"]["isError"] is True
    assert "requires approval" in text
    assert "has not been forwarded" in text
    row = proxy.conn.execute("SELECT consumed_count FROM plans WHERE id=?", (plan_id,)).fetchone()
    assert row["consumed_count"] == 0


# --- The other two shapes of the same gap, also refused at match (not just proposal) ---


def test_match_refuses_a_stored_plan_against_a_euro_cap_with_no_cost_param(
    conn: Connection,
) -> None:
    """Shape 2: proposed while unbounded (honest, nothing to tie a ceiling
    to yet); the policy then settles into a euro cap with no `cost_param`
    at all -- there is no field name a plan's `amount_param` could ever
    have named correctly, so the plan is refused at match regardless of
    what it says. Calls `resolve_match` directly, not through the full
    engine: a euro cap with no `cost_param` ALSO fails cost resolution
    independently of plan matching, which would make a full-engine
    assertion pass for the wrong reason and hide a regression in
    `_check_action_spec` itself."""
    _policy(conn, cost_param=None, two_person_above_eur=None)
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "amount_eur"}},
        count_ceiling=10,
        amount_ceiling=Decimal(10),
        recipients=[],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    _policy(conn, cost_param=None, two_person_above_eur=None, eur_day=Decimal("500"))
    match = plan_ref.resolve_match(
        conn,
        plan_ref=plan_id,
        request=make_request(PAY, {"amount_eur": Decimal(10), "payee": "acme"}),
        now=FROZEN_NOW,
    )
    assert match is None


def test_match_refuses_a_stored_plan_whose_amount_param_is_not_the_numeric_bound(
    conn: Connection,
) -> None:
    """Shape 3: proposed while unbounded, naming `amount_param="unrelated"`
    (nothing wrong yet -- nothing bounded); the policy then settles into a
    plain `bounds.numeric` bound on `amount_eur` with no `cost_param`, no
    euro cap, no two-person threshold. The plan's own `amount_param` is not
    the numerically-bounded field, so its ceiling would still never be
    read -- refused at match. Calls `resolve_match` directly for the same
    reason as the euro-cap case above."""
    _policy(conn, cost_param=None, two_person_above_eur=None)
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "unrelated"}},
        count_ceiling=10,
        amount_ceiling=Decimal(10),
        recipients=[],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    plans.approve(conn, plan_id, "bob", FROZEN_NOW)
    _policy(
        conn,
        cost_param=None,
        two_person_above_eur=None,
        numeric={"amount_eur": NumericBound(max=Decimal("2000"))},
    )
    # "unrelated" is itself present in the request (a small, real value) --
    # if the plan's own mismatched amount_param were merely absent from the
    # request, resolve_match would decline to match for that unrelated
    # reason, hiding whether the field-correctness check itself still works.
    match = plan_ref.resolve_match(
        conn,
        plan_ref=plan_id,
        request=make_request(
            PAY, {"amount_eur": Decimal(10), "payee": "acme", "unrelated": Decimal(1)}
        ),
        now=FROZEN_NOW,
    )
    assert match is None


def test_propose_allows_amount_param_naming_a_plain_numeric_bound(conn: Connection) -> None:
    """The positive case for shape 3: no `cost_param`, no euro cap, no
    two-person threshold, but `bounds.numeric` bounds `amount_eur` --
    naming it as `amount_param` is exactly right, and the plan proposes
    cleanly."""
    _policy(
        conn,
        cost_param=None,
        two_person_above_eur=None,
        numeric={"amount_eur": NumericBound(max=Decimal("2000"))},
    )
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {"amount_param": "amount_eur"}},
        count_ceiling=10,
        amount_ceiling=Decimal(10),
        recipients=[],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    assert plan_id > 0


def test_propose_refuses_a_euro_cap_action_with_no_cost_param_even_with_an_amount_param(
    conn: Connection,
) -> None:
    """Shape 2 at proposal time directly: a plan cannot name ANY
    `amount_param` that would make this action coverable, so it is refused
    outright, not merely when it guesses wrong."""
    _policy(conn, cost_param=None, two_person_above_eur=Decimal("1000"))
    with pytest.raises(PlanError, match="cost_param"):
        plans.propose(
            conn,
            "alice",
            {PAY: {"amount_param": "amount_eur"}},
            count_ceiling=10,
            amount_ceiling=Decimal(10),
            recipients=[],
            expires_at=EXPIRES_IN,
            now=FROZEN_NOW,
        )
    assert conn.execute("SELECT count(*) FROM plans").fetchone()[0] == 0


def test_propose_refuses_amount_param_not_matching_the_numeric_bound(conn: Connection) -> None:
    """Shape 3 at proposal time directly: a plan naming an `amount_param`
    that is not one of the numerically-bounded fields is refused -- its
    ceiling would apply to a field the policy never checks against
    anything."""
    _policy(
        conn,
        cost_param=None,
        two_person_above_eur=None,
        numeric={"amount_eur": NumericBound(max=Decimal("2000"))},
    )
    with pytest.raises(PlanError, match="amount_param"):
        plans.propose(
            conn,
            "alice",
            {PAY: {"amount_param": "unrelated"}},
            count_ceiling=10,
            amount_ceiling=Decimal(10),
            recipients=[],
            expires_at=EXPIRES_IN,
            now=FROZEN_NOW,
        )
    assert conn.execute("SELECT count(*) FROM plans").fetchone()[0] == 0


# --- One recipient list, one meaning ----------------------------------------------


def test_propose_refuses_a_plan_covering_one_action_with_a_recipient_param_and_one_without(
    conn: Connection,
) -> None:
    """A reviewer's own two-action case: `PAY` names `recipient_param`,
    a second action in the same plan names none at all -- the stored
    `recipients_json` would bind `PAY` but be silently ignored by the
    other action, which is not what a single recorded list can honestly
    say it covers."""
    other = "demo.plan_bounds_other"
    _policy(
        conn, action_type=PAY, cost_param=None, two_person_above_eur=None, enum={"payee": ["acme"]}
    )
    _policy(conn, action_type=other, cost_param=None, two_person_above_eur=None)
    with pytest.raises(PlanError, match="recipient_param"):
        plans.propose(
            conn,
            "alice",
            {
                PAY: {"recipient_param": "payee"},
                other: {},
            },
            count_ceiling=10,
            amount_ceiling=Decimal(10),
            recipients=["acme"],
            expires_at=EXPIRES_IN,
            now=FROZEN_NOW,
        )
    assert conn.execute("SELECT count(*) FROM plans").fetchone()[0] == 0


def test_propose_allows_two_actions_that_both_name_a_recipient_param(conn: Connection) -> None:
    other = "demo.plan_bounds_other"
    _policy(
        conn, action_type=PAY, cost_param=None, two_person_above_eur=None, enum={"payee": ["acme"]}
    )
    _policy(
        conn,
        action_type=other,
        cost_param=None,
        two_person_above_eur=None,
        enum={"payee": ["acme"]},
    )
    plan_id = plans.propose(
        conn,
        "alice",
        {
            PAY: {"recipient_param": "payee"},
            other: {"recipient_param": "payee"},
        },
        count_ceiling=10,
        amount_ceiling=Decimal(10),
        recipients=["acme"],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    assert plan_id > 0


def test_propose_allows_two_actions_neither_naming_a_recipient_param(conn: Connection) -> None:
    other = "demo.plan_bounds_other"
    _policy(conn, action_type=PAY, cost_param=None, two_person_above_eur=None)
    _policy(conn, action_type=other, cost_param=None, two_person_above_eur=None)
    plan_id = plans.propose(
        conn,
        "alice",
        {PAY: {}, other: {}},
        count_ceiling=10,
        amount_ceiling=Decimal(10),
        recipients=[],
        expires_at=EXPIRES_IN,
        now=FROZEN_NOW,
    )
    assert plan_id > 0
