# Decision service integration (HTTP)

The PDP over the wire: run the service next to your system and consult it
from any language. You enforce; the service decides, audits, and notifies.

## Run

```bash
pip install "onedoor[service]"
export ONEDOOR_DECIDE_KEYS=svc-key-1          # comma-separated
export ONEDOOR_ADMIN_KEYS=admin-key-1
export ONEDOOR_POLICIES=policies.yaml
export ONEDOOR_DB=/var/lib/onedoor/onedoor.db
uvicorn onedoor.service.app:create_app --factory --port 8470
```

Or Docker: `docker build -t onedoor . && docker run -p 8470:8470 -v onedoor-data:/data -e ONEDOOR_DECIDE_KEYS=... -e ONEDOOR_ADMIN_KEYS=... onedoor`

## Authentication and roles

`Authorization: Bearer <key>` on every call. Two roles, deliberately split:

| Role | Env var | May call |
|---|---|---|
| decide | `ONEDOOR_DECIDE_KEYS` | `/v1/decide`, `/v1/report` |
| admin | `ONEDOOR_ADMIN_KEYS` | `/v1/approvals` (list, approve, deny), `/v1/killswitch` |

Each key holds exactly one role; a key in both sets stops the service from
starting. The process that asks for permission never grants it.

## The decide → enforce → report loop

```bash
curl -s -X POST localhost:8470/v1/decide \
  -H "Authorization: Bearer svc-key-1" -H "Content-Type: application/json" \
  -d '{"action_type": "payments.transfer",
       "params": {"payee": "acme", "amount_eur": 120},
       "rationale": "agent-initiated refund"}'
```

Responses by outcome:

```jsonc
// permitted — YOU must act, then report:
{"decision": "permitted", "intent_audit_id": 41, "undo_until": null, ...}

// denied — do not act; the reason is machine-readable:
{"decision": "denied", "reason": "bounds", "detail": "param 'amount_eur'=9000 above max 500.0", ...}

// proposed — waiting for a human; poll or subscribe:
{"decision": "proposed", "reason": "tier_confirm", "approval_id": 7, ...}

// dry_run — log-only rehearsal, nothing to enforce
{"decision": "dry_run", ...}
```

After enforcing a permitted decision:

```bash
curl -s -X POST localhost:8470/v1/report \
  -H "Authorization: Bearer svc-key-1" -H "Content-Type: application/json" \
  -d '{"intent_audit_id": 41, "outcome": "success", "payload": {"tx_ref": "b-2291"}}'
```

**Report exactly once per intent**, success or failure. A permitted intent
that is never reported stays in the audit log as "intended, unconfirmed" —
alert on those.

## Approvals

```bash
curl -s localhost:8470/v1/approvals -H "Authorization: Bearer admin-key-1"
curl -s -X POST localhost:8470/v1/approvals/7/approve -H "Authorization: Bearer admin-key-1"
# -> {"decision": "permitted", "intent_audit_id": 44, ...}  — give it to the proposing PEP, which enforces and reports
curl -s -X POST localhost:8470/v1/approvals/7/deny -H "Authorization: Bearer admin-key-1"
```

Set `ONEDOOR_APPROVAL_WEBHOOK=https://hooks.slack.com/...` and every Tier-3
proposal POSTs a Slack-compatible payload (`text` plus a structured `onedoor`
object). A failing webhook never blocks or fails a decision.

## Kill switch

```bash
curl -s -X POST localhost:8470/v1/killswitch \
  -H "Authorization: Bearer admin-key-1" -H "Content-Type: application/json" \
  -d '{"engaged": true, "origin": "incident-2291"}'
```

While engaged: every actionable decision comes back `proposed` with reason
`kill_switch`; reads (Tier 0) stay available; even already-approved actions
are blocked. Release with `{"engaged": false}`.

## Observability

`pip install "onedoor[otel]"` and configure the standard `OTEL_*` environment
variables: each decision emits a `onedoor.decide` span (action type) and a
`onedoor.decisions` counter (outcome, reason, tier). No collector configured →
clean no-op.

## Operational notes (v0.3)

- Single-process service, one SQLite writer behind an internal lock. Run one
  instance per policy domain; Postgres + multi-instance are `ND-019` in
  [BACKLOG.md](../BACKLOG.md).
- Pending intents are held in memory between decide and report. A restart
  in that window leaves the honest "intended, unconfirmed" audit row; `ND-010`
  rebuilds intents from the audit log instead of memory.
- Keys are static in v0.3; OIDC/JWT is a v0.4 item. Terminate TLS in front
  of the service (reverse proxy) — it serves plain HTTP.
- Keys are recorded only as keyed fingerprints (`key-hmac:` and 16 hex
  characters): the approver of each approval and the proposer of each
  proposal made over HTTP. The fingerprint secret is
  `ONEDOOR_KEY_FINGERPRINT_SECRET` when set; otherwise it is generated once
  into `<database>.key-fingerprint`, beside the database. Keep that file out
  of version control; lose it and the same key gets a new fingerprint.
