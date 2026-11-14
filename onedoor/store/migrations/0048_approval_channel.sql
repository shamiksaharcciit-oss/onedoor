-- A link vote and an admin-key vote are two different
-- identity spaces that can never collide as strings, so nothing before
-- this stopped one person voting once by link and once by admin key from
-- completing a two-person approval alone.
--
-- approvals.approver_channels_json -- JSON list, same length and order as
--     approvers_json, each entry "key" or "link" naming which channel
--     recorded that approver. NULL (the default, and every row from
--     before this migration) means no channel was ever recorded for this
--     approval -- the mixed-pair check is skipped entirely for it, the
--     same "no snapshot, current behaviour" fallback this engine's other
--     migrations already use.

ALTER TABLE approvals ADD COLUMN approver_channels_json TEXT;
