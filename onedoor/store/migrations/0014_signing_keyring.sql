-- ND-015 / K1. The keyring: public keys as evidence, append-only.
--
-- Public keys are evidence, and evidence is never deleted (R037 §2). Rotation GROWS
-- this table: a new key gets a new derived key_id, and the old key stays so the
-- receipts it signed verify forever. There is no "current key" column and no update
-- path, deliberately -- a keyring that could be replaced is a keyring an attacker can
-- replace.
--
--   key_id        DERIVED, never assigned: `ed25519:` + sha256 of the raw public key
--                 bytes. A chosen label can drift from what it names; a digest cannot.
--   public_key    the raw 32-byte Ed25519 public key. PUBLIC -- no private key material
--                 ever enters this database, this repository, or any receipt.
--   alg           `ed25519` (RFC 8032). The ALGORITHM, never the library: Ed25519's
--                 output is deterministic, so recording a library version here would
--                 assert a dependence that does not exist (R038 §3).
--
-- WHAT THIS TABLE IS NOT, and it matters more than what it is: a signature checked
-- against a key found HERE proves internal consistency, not authenticity. An attacker
-- who can write this database supplies both the altered row and the key that vouches
-- for it. So a match against this keyring is reported as `self_consistent`, never as
-- `verified` -- verification requires a trust anchor the CALLER supplies from outside
-- the store. R038 §1: a receipt system must not be its own witness.
--
-- The triggers below are the same append-only discipline as actions_audit. They do not
-- close the hole above (they stop UPDATE and DELETE; a keyring must accept INSERTs or
-- rotation is impossible) -- they stop a rotated-out key from being quietly removed,
-- which is a different and also necessary guarantee.

CREATE TABLE IF NOT EXISTS signing_keys (
    key_id        TEXT PRIMARY KEY,
    public_key    BLOB NOT NULL,
    alg           TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    note          TEXT NOT NULL DEFAULT ''
);

CREATE TRIGGER IF NOT EXISTS signing_keys_no_update
BEFORE UPDATE ON signing_keys
BEGIN SELECT RAISE(ABORT, 'signing_keys is append-only'); END;

CREATE TRIGGER IF NOT EXISTS signing_keys_no_delete
BEFORE DELETE ON signing_keys
BEGIN SELECT RAISE(ABORT, 'signing_keys is append-only: a rotated-out key still has receipts'); END;
