-- A resume whose rebuilt request does not match the approval row it would have
-- reused (migration 0030's request_digest) is refused outright -- it does not
-- silently reuse the old row, and it does not silently start a new one. These two
-- columns carry the evidence rather than a free-text claim that the digests
-- differed, set only on that one refusal.
--
--   resume_digest_expected -- the digest stored on the approval row that was found.
--   resume_digest_actual   -- the digest of the request that was actually resumed.
--
-- NULL on every row written before this migration, and on every row this specific
-- refusal path never touches afterward -- the same None-is-absence reading
-- `onedoor/decision_digest.py` already gives `resumes_audit_id` and
-- `decide_principal`.
ALTER TABLE actions_audit ADD COLUMN resume_digest_expected TEXT;
ALTER TABLE actions_audit ADD COLUMN resume_digest_actual TEXT;
