"""`evaluation_trace`: the ordered list of checks actually evaluated (AADP -03 §10,
a MUST).

The three checks this covers:

    a deny's reason matches the trace's failing entry
    a short-circuited pipeline shows no entries after the point where it stopped
    the trace is stored in the audit row and appears in the export from step 3
"""

from __future__ import annotations

import json
from decimal import Decimal
from sqlite3 import Connection

from onedoor.export import export_rows
from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import ActionResult, PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import OpaqueHosts, ParamEffectRule, Policy, Source, Tier, UrlMatch
from tests.conftest import FROZEN_NOW, make_request


def _audit_row(conn: Connection, audit_id: int) -> dict[str, object]:
    row = conn.execute("SELECT * FROM actions_audit WHERE id=?", (audit_id,)).fetchone()
    return dict(row)


def _trace_of(conn: Connection, audit_id: int) -> list[dict[str, str]]:
    raw = _audit_row(conn, audit_id)["evaluation_trace_json"]
    assert raw is not None, "a decision-kind row must carry an evaluation_trace"
    return list(json.loads(str(raw)))


def _permit_audit_id(result: ActionResult | PermittedIntent) -> int:
    if isinstance(result, PermittedIntent):
        return result.intent_audit_id
    assert result.audit_id is not None
    return result.audit_id


def test_a_denys_reason_matches_the_traces_failing_entry(
    conn: Connection, config: EngineConfig
) -> None:
    """A cap denial (demo.tier2, eur_day=10): the last fail entry is cap_value."""
    request = make_request(
        "demo.tier2", {}, source=Source.UI, cost_eur=Decimal("20"), now=FROZEN_NOW
    )
    result = decide_and_reserve(request, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.decision.decision.value == "denied"
    assert result.decision.reason_code.value == "cap_value"

    trace = _trace_of(conn, result.audit_id)
    failing = [e for e in trace if e["result"] == "fail"]
    assert failing, "a denial must have a failing entry"
    assert failing[-1]["check"] == "cap_value" == result.decision.reason_code.value
    assert not any(e["result"] == "pass" and e["check"] == "cap_value" for e in trace), (
        "the failing check must never also appear as pass"
    )


def test_a_short_circuited_pipeline_shows_no_entries_after_it_stopped(
    conn: Connection, config: EngineConfig
) -> None:
    """A bounds denial (demo.toggle, an invalid `state`): nothing after `bounds`."""
    request = make_request(
        "demo.toggle", {"target": "demo.lamp", "state": "up"}, source=Source.UI, now=FROZEN_NOW
    )
    result = decide_and_reserve(request, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.decision.reason_code.value == "bounds"

    trace = _trace_of(conn, result.audit_id)
    checks = [e["check"] for e in trace]
    assert checks[-1] == "bounds", f"bounds must be the last check evaluated, got {checks}"
    assert "dry_run" not in checks, "dry_run is evaluated after bounds; it must not appear"
    assert "cap_value" not in checks and "cap_rate" not in checks, (
        "caps are evaluated after bounds; they must not appear"
    )
    assert trace[-1]["result"] == "fail"


def test_a_malformed_url_denial_carries_an_honestly_empty_trace(
    conn: Connection, config: EngineConfig
) -> None:
    """No check in the ordered pipeline ran before this denial -- an empty trace is
    correct, not a gap: it fails during effect resolution, before tier/bounds/caps."""
    policy_loader.upsert(
        conn,
        Policy(
            action_type="demo.fetch",
            tier=Tier.AUTO,
            dry_run=False,
            compensating_command="demo.restore",
            param_effects=[
                ParamEffectRule(
                    param="url",
                    add_effects=[],
                    url=UrlMatch(hosts=["example.com"], schemes=["https"], opaque=OpaqueHosts()),
                )
            ],
        ),
    )
    request = make_request("demo.fetch", {"url": "https://[::1"}, source=Source.UI, now=FROZEN_NOW)
    result = decide_and_reserve(request, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    assert result.decision.reason_code.value == "malformed"
    trace = _trace_of(conn, result.audit_id)
    assert trace == [], "no check ran before the malformed-URL denial"


def test_the_trace_is_stored_and_appears_in_the_export(
    conn: Connection, config: EngineConfig
) -> None:
    request = make_request(
        "demo.toggle", {"target": "demo.lamp", "state": "on"}, source=Source.UI, now=FROZEN_NOW
    )
    result = decide_and_reserve(request, conn=conn, config=config, now=FROZEN_NOW)

    intent_audit_id = _permit_audit_id(result)
    trace = _trace_of(conn, intent_audit_id)
    assert trace, "a permitted tier-1 action must still carry the checks it passed"
    assert all(e["result"] != "fail" for e in trace), "a permit must carry no failing check"

    exported = export_rows(conn)
    exported_row = next(r for r in exported if r["id"] == intent_audit_id)
    stored = _audit_row(conn, intent_audit_id)["evaluation_trace_json"]
    assert exported_row["evaluation_trace_json"] == stored
    assert json.loads(str(exported_row["evaluation_trace_json"])) == trace


def test_kill_switch_is_absent_from_the_trace_for_an_exempt_observe_read(
    conn: Connection, config: EngineConfig
) -> None:
    """OBSERVE is exempt from the kill switch (decision.py's own comment): the trace
    must not claim kill_switch was evaluated for a read."""
    request = make_request("demo.read", {}, source=Source.UI, now=FROZEN_NOW)
    result = decide_and_reserve(request, conn=conn, config=config, now=FROZEN_NOW)
    assert isinstance(result, ActionResult)
    trace = _trace_of(conn, result.audit_id)
    assert "kill_switch" not in [e["check"] for e in trace]
