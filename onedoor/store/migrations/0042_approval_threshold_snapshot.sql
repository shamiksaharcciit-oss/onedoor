-- the two-person threshold must be the stricter of the
-- policy snapshot recorded with the proposal and the current policy.
-- `_required_approvers` (approvals.py) previously read only the live policy
-- at approval time -- a policy edited between proposal and approval (the
-- threshold raised, or the two-person block removed) let an action proposed
-- under the stricter rule complete with only one approver.
--
-- approvals.required_approvers_at_proposal  -- how many approvers this
--     request's own policy, AS IT STOOD AT PROPOSAL TIME, required (1 or
--     2). NULL on every row from before this migration -- no snapshot
--     recorded, so cas_approve falls back to the current policy alone, the
--     same behaviour this program always had, not retroactively stricter.

ALTER TABLE approvals ADD COLUMN required_approvers_at_proposal INTEGER;
