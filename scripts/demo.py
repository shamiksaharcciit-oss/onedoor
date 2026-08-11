"""End-to-end demo of the niyam guardrail engine — zero external dependencies.

Walks one of everything through the executor: an auto-executed reversible action
and its undo, an unlisted action falling to default-deny and needing approval,
a cap exhausting, a bounds rejection, dry-run, and the kill switch clamping an
auto action to propose-and-confirm.

Run:  python -m scripts.demo
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from niyam.connectors import mock
from niyam.guardrail import approvals, killswitch, policy_loader
from niyam.guardrail import undo as undo_mod
from niyam.guardrail.executor import EngineConfig, evaluate_and_execute, resume_approval
from niyam.guardrail.models import ActionRequest, Source
from niyam.guardrail.registry import ConnectorRegistry
from niyam.store.db import Database

NOW = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
CONFIG = EngineConfig(
    approval_ttl_seconds=3600,
    connector_timeout_seconds=5.0,
    tz=ZoneInfo("Europe/Amsterdam"),
)


def req(action_type: str, source: Source = Source.RULE, **params: object) -> ActionRequest:
    return ActionRequest(
        request_id=uuid4(), action_type=action_type, params=dict(params), source=source,
        rationale="demo walkthrough", created_at=NOW,
    )


def show(label: str, result: object) -> None:
    d = result.decision  # type: ignore[attr-defined]
    print(f"  {label:34s} -> {d.decision.value:9s} (tier {int(d.effective_tier)}, reason {d.reason_code.value})")


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    db = Database(str(tmp / "demo.db"))
    db.init()
    conn = db.connect()
    policy_loader.load_file(conn, Path(__file__).parent.parent / "config" / "policies.yaml")
    registry = mock.build_registry()

    print("1) Reversible Tier-1 action auto-executes (and registers a 15-min undo):")
    r1 = evaluate_and_execute(req("demo.toggle", target="demo.lamp", state="on"),
                              conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.toggle on", r1)

    print("2) One-tap undo — the compensating command goes through the same pipeline:")
    r2 = undo_mod.undo(r1.audit_id, conn=conn, registry=registry, config=CONFIG,
                       session_id="demo", now=NOW + timedelta(minutes=5))
    show("undo of (1)", r2)

    print("3) Unlisted action type: default-deny -> Tier 3 proposal:")
    r3 = evaluate_and_execute(req("demo.unlisted", anything="goes"),
                              conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.unlisted", r3)

    print("4) A human approves it — only then does it execute:")
    r4 = resume_approval(r3.approval_id, "demo-session", conn=conn, registry=registry,
                         config=CONFIG, now=NOW + timedelta(minutes=1))
    show("demo.unlisted (approved)", r4)

    print("5) Bounds: an out-of-range parameter is denied before any human sees it:")
    r5 = evaluate_and_execute(req("demo.toggle", target="demo.lamp", state="sideways"),
                              conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.toggle state=sideways", r5)

    print("6) Caps: third call of a 2/day-capped action is denied:")
    for i in range(3):
        r6 = evaluate_and_execute(req("demo.capped", n=i),
                                  conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.capped (3rd today)", r6)

    print("7) Dry-run: a new action type rehearses without executing or spending caps:")
    r7 = evaluate_and_execute(req("demo.dry", target="demo.lamp", state="on"),
                              conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.dry", r7)

    print("8) Kill switch: engaged, even a Tier-1 action becomes propose-and-confirm:")
    killswitch.set_engaged(conn, True, origin="demo")
    r8 = evaluate_and_execute(req("demo.toggle", target="demo.lamp", state="off"),
                              conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.toggle (killed)", r8)

    conn.close()
    print("\nEvery row above is in the append-only audit log. The model proposes;")
    print("the policy layer disposes.")


if __name__ == "__main__":
    main()
