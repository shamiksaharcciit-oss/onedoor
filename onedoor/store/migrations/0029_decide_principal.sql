-- The decide key that received a permit, recorded so a report can be
-- refused from any other key the same way an unknown handle is refused.
-- A keyed fingerprint (HMAC with a server-side key, onedoor/service/keys.py,
-- the same shape already used for an approver's identity) -- never any
-- part of the key itself. NULL for a row written before this migration, or
-- by an in-process caller that never authenticated with a decide key; a
-- report against either kind of row is refused with the same unknown-handle
-- shape: this fails closed on an upgrade rather than
-- trusting a row that predates the identity this column records.
ALTER TABLE actions_audit ADD COLUMN decide_principal TEXT;
