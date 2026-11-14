-- Feature: signed approval links (onedoor 0.11).
--
-- approvals.link_sent     -- whether a link was ever built and dispatched
--     for this approval. 0 (false) until the propose path's own notify
--     step runs for a policy declaring approval_notify; stays 0 forever
--     for every other approval, the opt-in default every 0.11 feature
--     field has.
-- approvals.link_channel  -- "email" or "webhook", the channel a link was
--     sent over -- NULL until link_sent is set.

ALTER TABLE approvals ADD COLUMN link_sent INTEGER NOT NULL DEFAULT 0;
ALTER TABLE approvals ADD COLUMN link_channel TEXT;
