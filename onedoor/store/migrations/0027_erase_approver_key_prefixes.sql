-- Approver values recorded as `key:` plus the first characters of an admin key are
-- erased. The approver is now recorded as a keyed fingerprint (`key-hmac:...`), which
-- this pattern does not match. `actions_audit` is not touched: it is append-only and
-- sealed, so a prefix already written into a sealed row's detail stays there.
UPDATE approvals SET decided_by_session = 'key-prefix-erased'
 WHERE decided_by_session LIKE 'key:%';
