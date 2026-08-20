-- Reservation reclamation (AADP section 6: explicit, audited release of the
-- budget held by a permit that is never reported).
--
-- A permit reserves budget in cap_counters at decide time. If the enforcement
-- point never reports, that reservation would otherwise sit in the counter
-- until the accounting window rolled over -- budget spent by no action, with
-- nothing at the sink to detect. This table records, per permit, the exact
-- counter deltas it reserved and a deadline; once the deadline passes with no
-- report, the deltas are subtracted back and an "expired" row is appended to
-- the audit log. The release is an audited event, not a silent timeout, and
-- the permit is void from that point.

CREATE TABLE IF NOT EXISTS cap_reservations (
    intent_audit_id INTEGER PRIMARY KEY,   -- the exec_intent row this reserves for
    request_id      TEXT NOT NULL,
    deadline_utc    TEXT NOT NULL,         -- execute_within: void after this instant
    deltas_json     TEXT NOT NULL,         -- [[key, window_kind, window_key, count_delta, eur_delta], ...]
    status          TEXT NOT NULL DEFAULT 'held',  -- held | settled | expired
    created_utc     TEXT NOT NULL
);

-- The reclaimer scans open reservations by deadline; keep that lookup cheap.
CREATE INDEX IF NOT EXISTS idx_cap_reservations_open
    ON cap_reservations (status, deadline_utc);
