-- Approving a plan once (onedoor 0.11). The receipt a
-- plan-satisfied decision carries: which plan, and its own ceilings'
-- running totals immediately after this call's reservation. NULL on every
-- decision a plan did not satisfy -- the opt-in default every 0.11
-- feature's own receipt member already has.

ALTER TABLE actions_audit ADD COLUMN plan_ref INTEGER;
ALTER TABLE actions_audit ADD COLUMN plan_consumed_count_after INTEGER;
ALTER TABLE actions_audit ADD COLUMN plan_consumed_amount_after TEXT;
