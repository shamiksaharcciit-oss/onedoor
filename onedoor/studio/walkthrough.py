"""One decision, so the dogfooding walkthrough has something to look at.

**This is a walkthrough aid, not a product feature.** `docs/DOGFOODING.md` needs History
and the re-evaluate flagship to have a row to show, and a person following a twenty-minute
walkthrough should not have to write Python to get one. It exists for that, it says so,
and it is named for what it does rather than for what it might grow into.

It submits **one** action through `decide_and_reserve` — the same entry point the decision
service calls — against the store the operator has been using. No fixtures, no forged
rows: the decision is real, the audit row is real, and whatever the policy set in force
says about it is what happens.

    python -m onedoor.studio.walkthrough --db onedoor.db

It writes to the enforcer store, which is the one thing the Studio itself never does. That
is not a contradiction: this is a **stand-in for the agent**, not part of the Studio, and
it is a separate command precisely so that distinction stays visible.
"""

from __future__ import annotations

import argparse
from uuid import uuid4

from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import ActionRequest, Source
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

RATIONALE = "onedoor dogfooding walkthrough"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m onedoor.studio.walkthrough", description=__doc__
    )
    parser.add_argument("--db", default="onedoor.db", help="the enforcer's store")
    parser.add_argument("--action", default="payments.transfer", help="the action to attempt")
    parser.add_argument("--param", default="amount_eur=400.00", help="one `name=value` parameter")
    args = parser.parse_args(argv)

    name, _, value = args.param.partition("=")
    database = Database(args.db)
    database.init()
    conn = database.connect()
    try:
        request = ActionRequest(
            request_id=uuid4(),
            action_type=args.action,
            params={name: value} if name else {},
            source=Source.LLM,
            rationale=RATIONALE,
            created_at=now_utc(),
        )
        outcome = decide_and_reserve(request, conn=conn, config=_config(), now=request.created_at)
    finally:
        conn.close()

    if isinstance(outcome, PermittedIntent):
        verdict, reason = "permitted", "the policy set in force allows it"
    else:
        verdict = outcome.decision.decision.value
        reason = outcome.decision.reason_code or ""
    print(f"{args.action}: {verdict} ({reason})")
    print("Open the Studio's History screen; the decision is the newest entry.")
    return 0


def _config() -> EngineConfig:
    from onedoor.studio.server import _default_config

    return _default_config()


if __name__ == "__main__":  # pragma: no cover - exercised through `main`
    raise SystemExit(main())
