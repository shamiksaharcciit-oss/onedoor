-- The bound permit's `jti`, minted independently of this row's own id: the
-- issuer must be able to look up the decision from `jti` (-00 §3.2), which
-- this column is the other half of. NULL for every row with no bound
-- permit, and for every row written before this migration.
ALTER TABLE actions_audit ADD COLUMN permit_jti TEXT;
CREATE INDEX IF NOT EXISTS idx_actions_audit_permit_jti ON actions_audit (permit_jti);
