-- A candidate policy's own verdict for a request that was actually decided
-- under the live policy, recorded for later comparison. Never read by the
-- decision engine itself and never affects a live decision: this table is
-- write-only from the engine's own point of view, a side record, not a
-- second source of truth. `coverage`, `live_reason_code` and `comparison`
-- are added by `0050_shadow_decisions_coverage.sql`.

CREATE TABLE shadow_decisions (
    id              INTEGER PRIMARY KEY,
    request_id      TEXT NOT NULL,
    live_audit_id   INTEGER,
    action_type     TEXT NOT NULL,
    policy_label    TEXT NOT NULL,   -- caller-chosen name for the candidate policy
    decision        TEXT NOT NULL,   -- executed | proposed | denied (Decision's own values)
    effective_tier  INTEGER NOT NULL,
    reason_code     TEXT,
    detail          TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (live_audit_id) REFERENCES actions_audit(id)
);

CREATE INDEX idx_shadow_decisions_request_id ON shadow_decisions(request_id);
CREATE INDEX idx_shadow_decisions_policy_label ON shadow_decisions(policy_label);
