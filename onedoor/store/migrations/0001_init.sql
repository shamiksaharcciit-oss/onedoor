-- Sutradhar M0 schema. Forward-only migration.
-- The actions_audit table is APPEND-ONLY, enforced structurally by triggers below
-- (CLAUDE.md invariant 5: no UPDATE or DELETE on actions_audit, ever).

-- Engine-wide key/value config (kill switch, etc.).
CREATE TABLE IF NOT EXISTS config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Action policy table. Numeric bounds and caps live here, not in code
-- (CLAUDE.md invariant 6). bounds/caps stored as JSON.
CREATE TABLE IF NOT EXISTS policies (
    action_type          TEXT PRIMARY KEY,
    tier                 INTEGER NOT NULL,          -- 0..3
    bounds_json          TEXT NOT NULL DEFAULT '{}',
    caps_json            TEXT NOT NULL DEFAULT '{}',
    dry_run              INTEGER NOT NULL DEFAULT 1, -- new types start dry (invariant 7)
    dry_run_until        TEXT,                       -- 14-day graduation clock
    compensating_command TEXT,                       -- required iff tier == 1 (invariant 10)
    undo_window_seconds  INTEGER NOT NULL DEFAULT 900,
    requires_step_up     INTEGER NOT NULL DEFAULT 0, -- seam for money (M4)
    updated_at           TEXT NOT NULL
);

-- Append-only audit log. Two-row model: 'exec_intent' then 'exec_result' for
-- executed actions; single row for denied/proposed/dry_run/observe.
CREATE TABLE IF NOT EXISTS actions_audit (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id     TEXT NOT NULL,
    kind           TEXT NOT NULL,          -- decision | exec_intent | exec_result | exec_unknown
    parent_id      INTEGER,                -- exec_result -> exec_intent
    action_type    TEXT NOT NULL,
    source         TEXT NOT NULL,
    params_json    TEXT NOT NULL,
    decision       TEXT NOT NULL,          -- executed|dry_run|proposed|denied|failed
    reason_code    TEXT NOT NULL,
    nominal_tier   INTEGER NOT NULL,
    effective_tier INTEGER NOT NULL,
    detail         TEXT NOT NULL DEFAULT '',
    connector_ok   INTEGER,                -- NULL unless executed
    error          TEXT,
    payload_json   TEXT,
    approval_id    INTEGER,
    undo_until     TEXT,                   -- set on Tier-1 exec_intent that will attempt execution
    undo_of        INTEGER,                -- set on rows of an undo action -> original exec_intent id
    created_at     TEXT NOT NULL,
    UNIQUE (request_id, kind)              -- idempotency/replay backstop
);
CREATE INDEX IF NOT EXISTS idx_audit_request ON actions_audit (request_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON actions_audit (created_at);
CREATE INDEX IF NOT EXISTS idx_audit_parent  ON actions_audit (parent_id);
CREATE INDEX IF NOT EXISTS idx_audit_undo_of ON actions_audit (undo_of);

-- Structural append-only enforcement.
CREATE TRIGGER IF NOT EXISTS actions_audit_no_update
BEFORE UPDATE ON actions_audit
BEGIN
    SELECT RAISE(ABORT, 'actions_audit is append-only: UPDATE forbidden');
END;

CREATE TRIGGER IF NOT EXISTS actions_audit_no_delete
BEFORE DELETE ON actions_audit
BEGIN
    SELECT RAISE(ABORT, 'actions_audit is append-only: DELETE forbidden');
END;

-- Tier-3 approvals.
CREATE TABLE IF NOT EXISTS approvals (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    request_json       TEXT NOT NULL,       -- frozen original ActionRequest
    action_type        TEXT NOT NULL,
    state              TEXT NOT NULL,        -- pending|approved|denied|expired|executed
    created_at         TEXT NOT NULL,
    expires_at         TEXT NOT NULL,
    decided_at         TEXT,
    decided_by_session TEXT,
    resulting_audit_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_approvals_state ON approvals (state);

-- Cap accounting counters. window_kind in {rate, eur_day, eur_month}.
CREATE TABLE IF NOT EXISTS cap_counters (
    action_type TEXT NOT NULL,
    window_kind TEXT NOT NULL,
    window_key  TEXT NOT NULL,   -- 'YYYY-MM-DD' or 'YYYY-MM'
    count       INTEGER NOT NULL DEFAULT 0,
    eur_total   TEXT NOT NULL DEFAULT '0',
    PRIMARY KEY (action_type, window_kind, window_key)
);

-- Event bus log (in-process bus also publishes live; this is the durable trail).
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    topic        TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_created ON events (created_at);

-- Web Push subscriptions.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint   TEXT NOT NULL UNIQUE,
    p256dh     TEXT NOT NULL,
    auth       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Single-user sessions.
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- Intake policy: the sensing-side twin (invariant 18). Default-deny: an
-- unclassified source ingests nothing.
CREATE TABLE IF NOT EXISTS intake_policy (
    source         TEXT PRIMARY KEY,
    sensitivity    TEXT NOT NULL,        -- low|medium|high
    retention_days INTEGER NOT NULL,
    redaction      TEXT NOT NULL,        -- named redaction rule ref
    egress         TEXT NOT NULL,        -- none|redacted_summary|raw
    updated_at     TEXT NOT NULL
);

-- Explicit-memory / profile store (invariant 14). Confirmation-gated.
CREATE TABLE IF NOT EXISTS preferences (
    key          TEXT PRIMARY KEY,
    value        TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'ui',
    confirmed    INTEGER NOT NULL DEFAULT 0,
    confirmed_at TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
