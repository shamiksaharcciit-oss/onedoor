# Design note: the LangChain middleware over HTTP, with a decide-only key

Covers ruling item 3 (OD4) for 0.8.2. Amended with the decided retry/idempotency
contract below; moves to code next.

## The gap this closes

The LangChain middleware runs in-process today: `open_engine()`
(`onedoor/integrations/langchain_middleware.py:60-92`) opens a raw SQLite connection and loads
the policy file directly into the agent's own process, and `_decide()`/`_report()` call
`decide_and_reserve`/`report_result` as plain Python functions on that connection — no HTTP,
no key, no credential of any kind. The class docstring already names this as the open gap:
`allow_same_process_approval` "names that lack of separation rather than silently trusting
it. There is currently no alternative wiring ... that would give a real boundary." The
CHANGELOG's matching "Known limitations" entry: "The LangChain middleware has no wiring that
gives a real process boundary between the agent and whoever approves. It only ever holds a
direct database connection; talking to the decision service over HTTP with nothing but a
decide key ... is not built yet."

## The key already exists; the middleware doesn't use it

The HTTP service (`onedoor/service/app.py`) already has exactly the scope this item asks for
— it does not need to be invented. Two roles, read from comma-separated env vars, each key
holding exactly one:

- **`ONEDOOR_DECIDE_KEYS`** — `require_decide` (app.py:76-80) — may call `POST /v1/decide`
  (propose, and resume by presenting `approval_ref`) and `POST /v1/report` (report an
  enforcement outcome, and only for the same decide key that received that permit — see
  below). Cannot approve, deny, grant, or touch the kill switch.
- **`ONEDOOR_ADMIN_KEYS`** — `require_admin` (app.py:95-99) — may list/approve/grant/deny
  approvals and operate the kill switch. Cannot decide or report.
- `_refuse_overlapping_roles()` (app.py:83-92) stops the service from starting if any key
  appears in both sets.

So "the agent's process holds no database connection and no approver credential" is already
true of a key drawn from `ONEDOOR_DECIDE_KEYS` — it is a decide-only key by construction. The
work this item does is wiring the LangChain middleware to call the HTTP service with one,
instead of opening its own connection.

## The key's scope, where it's created and stored

- **Scope:** exactly the existing `decide` role — `POST /v1/decide` and `POST /v1/report`,
  nothing else. No new, narrower role is proposed; the existing two-role split already draws
  the line this item wants.
- **Created:** by whoever operates the onedoor service, the same way every decide key is
  created today — there is no provisioning API. The operator adds a value to
  `ONEDOOR_DECIDE_KEYS` and separately gives that same value to whatever process will run the
  LangChain middleware (its own environment, its own secret store — outside onedoor's
  concern, exactly as for any other decide-key caller today).
- **Stored:** nowhere, by onedoor. `onedoor/service/keys.py` never persists a key — only its
  fingerprint does: `fingerprint(key, secret)` is `HMAC-SHA-256(secret, key)`, truncated to 16
  hex characters and prefixed `key-hmac:` (keys.py:48-50). The secret itself comes from
  `ONEDOOR_KEY_FINGERPRINT_SECRET` if set, or a `<db_path>.key-fingerprint` file created
  `0o600` beside the database (keys.py:27-45). The middleware's own copy of its key lives only
  in its process's environment, exactly like today's `agent_principal` string does — except
  that string is unauthenticated prose and the key is a real credential checked against
  `ONEDOOR_DECIDE_KEYS` on every call.

## Request and refusal shapes

- Every call carries `Authorization: Bearer <key>` (`_extract_bearer`, app.py:70-73).
- Missing or malformed header: `401 {"detail": "missing bearer token"}`.
- Header present but not in `ONEDOOR_DECIDE_KEYS`: `403 {"detail": "key lacks decide role"}`.
- `POST /v1/decide`: body is `DecideBody` (`action_type`, `params`, `rationale`, `source`,
  optional `request_id`, optional `approval_ref` to resume, optional `presented_audience`);
  reply is `DecideReply` (`decision`, `reason`, `effective_tier`, `request_id`,
  `intent_audit_id` iff permitted, `approval_id` iff pending, `budget` iff a budget-shaped
  denial). The middleware's `_decide()` maps onto this one-to-one — same fields it already
  builds for the in-process call.
- `POST /v1/report`: accepted **only** from the decide key that received the original permit.
  The engine records `decide_principal` (a key fingerprint, never the key) on the audit row at
  decide time; report compares the calling key's fingerprint against it with
  `hmac.compare_digest` (app.py:340-350) and refuses with the same shape an unknown intent
  gets — `404 {"detail": "absent: no pending intent <id>"}` — on any mismatch, including a
  `NULL` row from before this existed. A different process presenting someone else's
  `intent_audit_id` is refused exactly as if that id did not exist; it is never told it was
  close.
- Resuming a granted approval still goes through `POST /v1/decide` with `approval_ref` set —
  there is no separate resume route. `grant`/`approve`/`deny`/`killswitch` all require an
  admin key and stay entirely out of the middleware's reach; the existing `/grant` route
  (app.py:414-424) is already written for exactly this shape — "a human grants here, through
  an authenticated admin key... the holder of the proposal's own principal resumes it later."

## What the in-process mode does from now on

It stays. `allow_same_process_approval=True` remains a supported, explicit opt-in for a
deployment with no real process boundary (a direct-connection constructor, same as today);
nothing about adding the HTTP-with-decide-key path removes or deprecates it. The two modes
are selected by which constructor the integrator uses: `open_engine()` + a live `conn` for
in-process, or a new (code-step, not this note) HTTP-client constructor taking a base URL and
a decide key for the real boundary. No existing test, deployment, or documented call changes
unless the integrator opts into the new path.

## Decided: a retrying client, idempotent by construction

**The server needs no new mechanism.** `request_id` is already the idempotency key
`DecideBody` carries (optional; the service mints one if absent). `decide_and_reserve`'s
first act, before any transaction, is `audit.result_for_request_id` — a repeated
`request_id` returns the already-recorded result outright
(`onedoor/guardrail/decision.py:211-216`), and `app.py`'s `/v1/decide` handler wraps the
whole call in `state.lock` (app.py:307), so even two genuinely concurrent requests carrying
the same `request_id` against one process serialize completely: the second never starts its
own check until the first has committed, and so always finds the first's result rather than
racing it. `actions_audit`'s `UNIQUE(request_id, kind)` constraint is the backstop under
that. **Never a second reservation** was already true; what did not exist is a client that
reuses one `request_id` across retries instead of minting a fresh one each attempt.

**The client (new module, this item's actual code) is what carries the call:**
- Generates one `request_id` per logical `decide()` call, before the first attempt, and sends
  the identical value on every retry of that same call — this is the whole of "a
  client-generated idempotency key, the same on every retry"; no new wire field, no server
  change.
- Retries a bounded number of times (default conservative, e.g. 3 attempts) with backoff
  (default conservative, e.g. exponential from a small base), inside a total deadline (default
  conservative, e.g. a few seconds) — all three settable by the integrator, since "conservative
  defaults" is a starting point, not every deployment's right answer.
- **On the deadline passing with no answer:** stops retrying, takes no action, and reports the
  call as **not attempted**, with a reason naming that the decision was never received —
  distinct from a `denied` reply (which the service did answer) and distinct from a `permitted`
  reply the caller then fails to enforce (which `/v1/report`'s existing design already handles).
  Nothing is assumed granted; the caller that gets "not attempted" back has exactly the
  information a decide call that never reached the service would have, because for all onedoor
  can tell, it may not have.
- This answers the note's own earlier open question: the client is a small, purpose-built
  wrapper (not a published general surface), because its entire reason to exist is this
  specific retry/deadline/idempotency contract — a generic HTTP client would not carry it.
