-- plans.py's own `_required_approvers`/`approve()`
-- had the identical stale-threshold gap fixed in approvals.py --
-- the two-person threshold for a plan's own proposal was read fresh from the
-- current policy at approval time, with no snapshot of what the policy
-- required when the plan was proposed.
--
-- plans.required_approvers_at_proposal  -- how many approvers this plan's
--     own covered actions' policies, AS THEY STOOD AT PROPOSAL TIME,
--     required (1 or 2). NULL on every row from before this migration --
--     no snapshot recorded, so approve() falls back to the current policy
--     alone, the same behaviour this program always had, not retroactively
--     stricter.

ALTER TABLE plans ADD COLUMN required_approvers_at_proposal INTEGER;
