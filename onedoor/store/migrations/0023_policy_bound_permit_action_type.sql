-- Bound-permit profile §§3-4, §17.3. The registered action-type name a bound
-- permit's authorization_details entry carries for this policy. Same shape as
-- 0021/0022: the policies table is explicit SQL columns, not a JSON blob, so a
-- new Policy field needs its own migration.

ALTER TABLE policies ADD COLUMN bound_permit_action_type TEXT;
