-- ND-024. Retire schema inherited from the pre-onedoor product (Sutradhar M0).
--
-- `intake_policy`, `preferences` and `sessions` were created by 0001 and have never
-- been read by any module under onedoor/. Dead schema in a governance product is not
-- inert: a reader who opens the database sees tables implying governed surfaces --
-- an intake/sensing policy, a preference store, a session model -- that do not exist
-- in this engine. That is the same class of defect as an example demonstrating a
-- contract violation: a published artifact implying something untrue.
--
-- Migrations are forward-only, so 0001 keeps its CREATE statements and the history
-- stays legible; the tables are dropped here rather than edited out of the past.
--
-- `push_subscriptions` is NOT dropped. It is unread today but genuinely planned
-- (ND-026, web-push delivery for Tier-3 approvals, which are Slack-only right now).

DROP TABLE IF EXISTS intake_policy;
DROP TABLE IF EXISTS preferences;
DROP TABLE IF EXISTS sessions;
