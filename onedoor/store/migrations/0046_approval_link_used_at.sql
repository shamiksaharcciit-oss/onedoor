-- Feature: signed approval links (onedoor 0.11).
--
-- approvals.link_used_at  -- when a presented approval link was resolved
--     and acted on (POST /v1/approvals/by-link/{token}). NULL until a
--     link is ever used for this approval, or if none ever is -- the
--     approval still proposes and waits exactly as today, reachable by
--     Studio or a direct API call either way.

ALTER TABLE approvals ADD COLUMN link_used_at TEXT;
