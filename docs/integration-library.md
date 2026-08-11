# Library integration (Python)

Embed the engine in-process. Two styles: the composed executor (engine also
enforces, via a connector registry) or the decision/enforcement split (you
enforce; the engine decides and audits).

## Install

```bash
pip install niyam          # engine only; Python >= 3.12
```

## Setup once

```python
from pathlib import Path
from zoneinfo import ZoneInfo

from niyam.guardrail import policy_loader
from niyam.guardrail.executor import EngineConfig
from niyam.store.db import Database

db = Database("guardrail.db")
db.init()
conn = db.connect()
policy_loader.load_file(conn, Path("policies.yaml"))
config = EngineConfig(
    approval_ttl_seconds=3600,
    connector_timeout_seconds=10.0,
    tz=ZoneInfo("Europe/Amsterdam"),
)
```

## Style A — the decision/enforcement split (recommended for integrations)

You own the act (an API call, a tool invocation, a DB write); niyam owns the
judgment and the audit trail.

```python
from uuid import uuid4

from niyam.guardrail.decision import PermittedIntent, decide_and_reserve, report_result
from niyam.guardrail.models import ActionRequest, Source
from niyam.store.clock import now_utc

now = now_utc()
request = ActionRequest(
    request_id=uuid4(),
    action_type="crm.update_record",
    params={"record_id": "A-113", "field": "status", "value": "closed"},
    source=Source.LLM,
    rationale="agent proposed closing a resolved ticket",
    created_at=now,
)

outcome = decide_and_reserve(request, conn=conn, config=config, now=now)

if isinstance(outcome, PermittedIntent):
    try:
        result = my_crm.update(**request.params)        # <- your enforcement
        report_result(outcome, conn=conn, ok=True,
                      payload={"crm_result": str(result)[:500]}, error=None, now=now_utc())
    except Exception as exc:
        report_result(outcome, conn=conn, ok=False,
                      payload=None, error=str(exc)[:200], now=now_utc())
        raise
else:
    d = outcome.decision
    # d.decision is DENIED / PROPOSED / DRY_RUN; d.reason_code says why;
    # outcome.approval_id is set for proposals.
    handle_refusal(d)
```

**The contract:** if you receive a `PermittedIntent`, you must call
`report_result` exactly once, whatever happened. Caps were already reserved
and the intent row is already in the audit log — a missing report leaves an
honest "intended, unconfirmed" row, which your operators should treat as an
incident, not noise.

## Style B — the composed executor

Register connectors and let the engine enforce too. Suits systems where the
actions are yours end to end.

```python
from niyam.guardrail.executor import evaluate_and_execute, propose_action
from niyam.guardrail.registry import ConnectorRegistry

registry = ConnectorRegistry()
registry.register("crm.update_record", my_crm_act_fn)   # (params: dict) -> dict

result = propose_action(
    "crm.update_record", {"record_id": "A-113", "field": "status", "value": "closed"},
    rationale="agent proposal", conn=conn, registry=registry, config=config,
)
```

## Approvals and undo

```python
from niyam.guardrail.executor import resume_approval, deny_approval
from niyam.guardrail import approvals, undo

pending = approvals.list_pending(conn)
result = resume_approval(pending[0].approval_id, "session-ui-1",
                         conn=conn, registry=registry, config=config)

# Undo an executed Tier-1 action (within its window):
undo.undo(result.audit_id, conn=conn, registry=registry, config=config,
          session_id="session-ui-1")
```

## Threading

One connection, one writer. If your host runs handlers on a threadpool, hold
your own lock around engine calls and open the connection with
`db.connect(check_same_thread=False)` — the decision service does exactly
this.
