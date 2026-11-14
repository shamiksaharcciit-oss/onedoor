-- Untrusted-input checks (onedoor 0.11). Which of the request's own
-- `untrusted` paths actually matched this action type's own
-- `untrusted_params.deny`/`hold` -- a receipt member, not part of the
-- cryptographic preimage (digests.py/preimage.py build their own explicit,
-- frozen field lists and do not read this column): a 0.10.x reader that has
-- never heard of this field still verifies every row's chain and signature
-- exactly as before. NULL for every row written before this migration, and
-- for a row whose decision never reached the untrusted-input check at all.

ALTER TABLE actions_audit ADD COLUMN untrusted_matched_json TEXT;
