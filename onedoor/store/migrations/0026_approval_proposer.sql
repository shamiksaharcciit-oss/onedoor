-- The principal that proposed an approval, so the store can refuse an approval by
-- that same principal. Supplied by whoever authenticated the caller, never read from
-- the request. NULL for approvals written before this column existed, and for callers
-- that authenticate nobody: there is then nothing to compare.
ALTER TABLE approvals ADD COLUMN proposed_by TEXT;
