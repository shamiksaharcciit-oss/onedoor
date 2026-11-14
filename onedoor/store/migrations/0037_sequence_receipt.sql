-- Rules across a sequence (onedoor 0.11). Receipt members: how many of this
-- session's own settled events a `sequence` rule actually consulted, which
-- rule (if any) matched, and whether the window it was asked to read reached
-- further back than this session's history still holds (`sequence_evicted`).
-- NULL on every row before this migration, and on every row whose policy
-- carries no `sequence` block at all -- a 0.10.x reader already ignores an
-- addition like every other optional member here.

ALTER TABLE actions_audit ADD COLUMN sequence_events_considered INTEGER;
ALTER TABLE actions_audit ADD COLUMN sequence_rule_matched TEXT;
ALTER TABLE actions_audit ADD COLUMN sequence_history_incomplete INTEGER;
