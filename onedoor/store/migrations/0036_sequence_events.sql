-- Rules across a sequence (onedoor 0.11). The session history a sequence
-- rule reads: one row per settled action whose policy carries a `sequence`
-- block at all (`tag_as` set or not -- `count_over` matches by this row's
-- own `action_type`, never needing a tag). Append-only, never updated;
-- pruned only by the two bounds `onedoor.guardrail.sequence` enforces (the
-- per-session cap, and the cross-session prune by the longest
-- `within_seconds` any loaded policy's rule uses).
--
-- `sequence_evicted` carries one row per session that has ever had a row
-- pruned from it: the time up to which that session's own history is known
-- to be incomplete, so a rule whose own window reaches further back than
-- this can answer honestly (`sequence_history_incomplete: true`) rather than
-- silently evaluating against a partial table and calling it conclusive.

CREATE TABLE sequence_events (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    tag TEXT,
    at TEXT NOT NULL,
    audit_id INTEGER NOT NULL
);

CREATE INDEX idx_sequence_events_session_at ON sequence_events (session_id, at);
CREATE INDEX idx_sequence_events_session_tag ON sequence_events (session_id, tag, at);
CREATE INDEX idx_sequence_events_session_type ON sequence_events (session_id, action_type, at);

CREATE TABLE sequence_evicted (
    session_id TEXT PRIMARY KEY,
    evicted_through TEXT NOT NULL
);
