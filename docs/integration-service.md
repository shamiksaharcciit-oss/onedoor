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

On Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`, whose
own `-Headers`/body handling doesn't take these calls verbatim: use
`curl.exe` (the real binary) with `--%`, PowerShell's stop-parsing token, so
embedded double quotes reach the call exactly as written, and write the
JSON body as one line with escaped quotes instead of a single-quoted
here-string:

```powershell
curl.exe --% -s -X POST localhost:8470/v1/decide -H "Authorization: Bearer svc-key-1" -H "Content-Type: application/json" -d "{\"action_type\": \"payments.transfer\", \"params\": {\"payee\": \"acme\", \"amount_eur\": 120}, \"rationale\": \"agent-initiated refund\"}"
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

```powershell
curl.exe --% -s -X POST localhost:8470/v1/report -H "Authorization: Bearer svc-key-1" -H "Content-Type: application/json" -d "{\"intent_audit_id\": 41, \"outcome\": \"success\", \"payload\": {\"tx_ref\": \"b-2291\"}}"
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

```powershell
curl.exe --% -s localhost:8470/v1/approvals -H "Authorization: Bearer admin-key-1"
curl.exe --% -s -X POST localhost:8470/v1/approvals/7/approve -H "Authorization: Bearer admin-key-1"
curl.exe --% -s -X POST localhost:8470/v1/approvals/7/deny -H "Authorization: Bearer admin-key-1"
```

Set `ONEDOOR_APPROVAL_WEBHOOK=https://hooks.slack.com/...` and every Tier-3
proposal POSTs a Slack-compatible payload (`text` plus a structured `onedoor`
object). A failing webhook never blocks or fails a decision.

### Signed approval links

A policy's own `approval_notify` block (`channel: email|webhook`, `recipient:
...`) sends a signed, single-use approve link and a separate deny link for
each of its own Tier-3 proposals, through `GET`/`POST /v1/approvals/by-link/
{token}`.

**Turning it on.** The `Run` command above, and
`--factory` generally, cannot turn this on: `notify_config`,
`send_email` and `send_webhook` are Python arguments to `create_app()`
itself, with no environment variable or CLI flag standing in for them.
A deployment that wants links writes its own small factory module and
points uvicorn at that instead:

```python
# myapp_factory.py
from onedoor.guardrail.approval_link import NotifyConfig
from onedoor.service.app import create_app


def app():
    return create_app(
        notify_config=NotifyConfig(
            approval_link_base_url="https://onedoor.internal/links",
            approval_link_signing_keys={"k1": b"...32+ bytes..."},
            approval_link_signing_key_id="k1",
            approval_link_issuer="prod-us-east",
        ),
        send_email=my_send_email,  # or send_webhook=my_send_webhook
    )
```
```bash
uvicorn myapp_factory:app --factory --port 8470
```

**The link is a bearer credential**: whoever holds it can approve
or deny, exactly once, as the recipient it was issued to, until it expires —
possession is the proof, the same security model an email password-reset
link already has, not a separate identity check. **The link's own
lifetime is the approval's own lifetime** — there is no separate setting
for it. The service passes `EngineConfig.approval_ttl_seconds` (set from
`ONEDOOR_APPROVAL_TTL`, default `3600`) as every link's own `ttl_seconds`
when it issues one; `approval_link.DEFAULT_LINK_TTL_SECONDS` is a
different thing entirely — `issue()`'s own fallback for a caller using
the library directly and passing no `ttl_seconds` at all, which the
service's own wiring never does. The two happen to share the same
one-hour value by convention, not because either defines the other. A
deployment that cares about the exposure window shortens
`ONEDOOR_APPROVAL_TTL` itself (which shortens ordinary Tier-3 approvals
too, not only links), and sends the link over a channel only the real
approver reads — never a shared inbox or a channel the proposer can also
see, since anyone who can read it can use it.

**A link vote grants; it does not resume.** Like
`/grant`, not `/approve`: the by-link POST route flips the approval's own
state and nothing else, never calling back into the decide pipeline to
execute or resume the underlying action. The action resumes exactly the
same way a vote cast through `/grant` already resumes one — the original
caller presenting that same `approval_ref` again, on a fresh `/v1/decide`
call (there is currently no route that resumes an already-granted
approval by itself; see the kill switch section below for the same point
made about `/grant`). A recorded-but-insufficient vote (a two-person
policy, one vote in) answers `202`, the same as `/grant` gives for the
same case — not `200`, which would read as a completed decision.

The receipt (`approvals.link_used_at`) records that a link was used and
when, never who clicked it: the identity recorded as having approved or
denied is the recipient the link was issued to, not a browser session or an
IP address, by design. **For a webhook channel, that identity is the
webhook URL itself** (`approval_notify.recipient` is the URL for that
channel) — the same string recorded as having approved or denied, not a
caller or account name.

A policy names exactly one `approval_notify.recipient`, so every link it
issues carries that same identity — two link presentations under one
policy are the same approver voting twice, not two people. A link vote,
an admin-key vote (`/approve`, `/grant`), and a library vote (a resumed
approval with neither a key nor a link involved) are three different
identity spaces that can never be equal as strings; a vote through one
and a second vote through a different one does not complete a
two-person approval — the second vote is refused with its own `409` (or
its library-level equivalent), naming the mixed channel, and is not
recorded as a second approver:

| First vote | Second vote | Completes a two-person approval? |
|---|---|---|
| key | key, different identity | Yes |
| key | link | No -- mixed channel |
| key | library | No -- mixed channel |
| link | link, same policy | No -- same recipient identity, not two votes |
| link | library | No -- mixed channel |
| library | library, different identity | Yes |

**Required config.** `NotifyConfig.approval_link_issuer`
is a non-empty string naming this deployment -- signed into every token it
issues and checked against a presented token's own claim, so a token
issued by a different deployment (one replayed from a restored backup
that happens to share a signing key, say) is refused regardless of its
signature. A token also binds the approval's own request digest at issue
time, checked against that approval's current request -- refused if the
approval id now names a different request than the one the token was
issued for.

**The access log.** `create_app` installs a filter on uvicorn's own
`uvicorn.access` logger that redacts a by-link token from the request
line it writes -- this module's own log already redacted it
before this filter was added. That filter runs inside this process only;
a reverse proxy or load balancer in front of it sees the real request
line regardless. A deployment using signed links should also run uvicorn
with `--no-access-log`, which removes the request-line log at its source
rather than relying on a filter to catch every path that writes one.

**The kill switch.** A by-link vote is unaffected by
it: the route only flips the approval's own state (`cas_approve`/`deny`,
the same as `/grant`), never resumes or executes anything, and the kill
switch is checked inside the decide pipeline a RESUME takes (`/approve`),
not inside `cas_approve`/`deny` themselves. A link presented while the
kill switch is engaged still records its vote exactly as it would
otherwise.

**A nonce spent on a vote that is then refused stays spent.**
`approval_link.resolve` consumes the token's own single-use nonce as
soon as its signature, expiry and claims verify -- before the route
ever calls `cas_approve`. A vote that verifies cleanly but is then
refused for an unrelated reason (a mixed channel, or recorded as
insufficient against a two-person threshold) has already spent the
nonce: presenting that exact token again answers `CONSUMED`, not a
fresh attempt. The token itself was genuine and was used exactly once,
which is what single-use means here -- it is not a promise that the
vote it carried was the one that completed anything.

**`link_used_at` is set the same way, for the same reason.**
The route sets it immediately after a presented link verifies, still
before `cas_approve` runs -- so a vote that verifies and is then refused
(the same two cases above) still marks the link used. The column
records that a verified link was presented and acted on, not that the
action it asked for actually went through.

## Kill switch

```bash
curl -s -X POST localhost:8470/v1/killswitch \
  -H "Authorization: Bearer admin-key-1" -H "Content-Type: application/json" \
  -d '{"engaged": true, "origin": "incident-2291"}'
```

```powershell
curl.exe --% -s -X POST localhost:8470/v1/killswitch -H "Authorization: Bearer admin-key-1" -H "Content-Type: application/json" -d "{\"engaged\": true, \"origin\": \"incident-2291\"}"
```

While engaged: every actionable decision is denied with reason `kill_switch`
rather than proposed, so an incident never fills the approval queue with
rows nobody can act on yet; reads (Tier 0) stay available; even
already-approved actions are blocked. Release with `{"engaged": false}`.

A stop's effect on an approval already granted depends on how it is
presented. The MCP integration presents a granted approval's reference in
the same call the kill switch denies, so that call consumes it — the human
must grant again once the switch is lifted. The LangChain middleware's
`"interrupt"` mode does not: resuming re-proposes before presenting the
reference (a LangGraph property, not onedoor's), so that fresh proposal is
what the kill switch denies, and the reference is never presented. A stop
there does not use up an approval granted for an interrupted LangChain
action -- after the switch is lifted, resuming with that same approval id
runs the action, unless an approver denies or withdraws it first. There is
currently no route that withdraws an *already-granted* approval (`/deny`
only refuses one still `pending`); see the LangChain guide and the
known-limitations list.

## Observability

`pip install "onedoor[otel]"` and configure the standard `OTEL_*` environment
variables: each decision emits a `onedoor.decide` span (action type) and a
`onedoor.decisions` counter (outcome, reason, tier). No collector configured →
clean no-op.

## Operational notes (v0.3)

- Single-process service, one SQLite writer behind an internal lock. Run one
  instance per policy domain; Postgres and multi-instance (`ND-019`) are not
  supported yet.
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
