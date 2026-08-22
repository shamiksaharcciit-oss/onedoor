"""Clean-venv smoke: the checks a wheel has actually failed before."""

import tempfile
from uuid import uuid4
from zoneinfo import ZoneInfo

from onedoor.guardrail import policy_loader
from onedoor.guardrail.decision import PermittedIntent, decide_and_reserve
from onedoor.guardrail.executor import EngineConfig
from onedoor.guardrail.models import (
    ActionRequest,
    Bounds,
    EffectPolicy,
    OpaqueHosts,
    ParamEffectRule,
    Policy,
    Source,
    Tier,
    UrlMatch,
)
from onedoor.store.clock import now_utc
from onedoor.store.db import Database

db = Database(tempfile.mktemp(suffix=".db"))
db.init()  # 0.3.0 shipped a wheel that died right here
conn = db.connect()
applied = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
print("migrations applied:", len(applied), "->", applied[-1])
cols = {r["name"] for r in conn.execute("PRAGMA table_info(actions_audit)")}
for needed in ("malformed_kind", "canon_schema", "opaque_class"):
    assert needed in cols, f"{needed} missing from actions_audit"
print(
    "0.4.1 evidence columns present:",
    sorted(c for c in cols if c in {"malformed_kind", "canon_schema", "opaque_class"}),
)

policy_loader.upsert_effect(conn, EffectPolicy(effect="money.egress.url", min_tier=Tier.CONFIRM))
policy_loader.upsert(
    conn,
    Policy(
        action_type="url.http",
        tier=Tier.AUTO,
        dry_run=False,
        compensating_command="onedoor.noop",
        bounds=Bounds(strict_params=False),
        param_effects=[
            ParamEffectRule(
                param="url",
                add_effects=["money.egress.url"],
                url=UrlMatch(hosts=["bank.example.com"], schemes=["https"], opaque=OpaqueHosts()),
            )
        ],
    ),
)


def verdict(url):
    now = now_utc()
    return decide_and_reserve(
        ActionRequest(
            request_id=uuid4(),
            action_type="url.http",
            params={"url": url},
            source=Source.LLM,
            rationale="smoke",
            created_at=now,
        ),
        conn=conn,
        config=EngineConfig(
            approval_ttl_seconds=60, connector_timeout_seconds=5.0, tz=ZoneInfo("UTC")
        ),
        now=now,
    )


for url, expect_permitted in [
    ("https://weather.example.com/today", True),  # innocent, untouched
    ("https://bank%2Eexample%2Ecom/transfer", False),  # canonicalization
    ("https://t.co/x9k2", False),  # opaque class, min_tier None
    ("https://bank%2Fevil.test/x", False),  # unreadable -> malformed
]:
    r = verdict(url)
    permitted = isinstance(r, PermittedIntent)
    assert permitted == expect_permitted, f"{url}: permitted={permitted}"
    tag = (
        "permitted" if permitted else f"{r.decision.decision.value}/{r.decision.reason_code.value}"
    )
    print(f"  {url:42s} -> {tag}")
print("OK: clean-venv install decides correctly on 0.4.1's new surface")
