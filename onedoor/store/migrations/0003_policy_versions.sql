-- Policy provenance. Without this, a decision cannot be re-derived after any
-- policy edit: `policies` is upserted in place with no history, so the rules that
-- produced a past verdict simply stop existing. AADP section 10 requires the
-- evidence record to be sufficient to re-derive every verdict it contains, given
-- the policy version in force at the time.
--
-- A version is the content hash of the whole normalized policy set (action
-- policies + effect policies). Editing anything produces a new version; editing
-- something back produces the *original* hash again, which is correct — the rules
-- really are the same — while the audit trail still shows both transitions.

CREATE TABLE IF NOT EXISTS policy_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    version_hash  TEXT NOT NULL UNIQUE,   -- sha256 of the normalized snapshot
    snapshot_json TEXT NOT NULL,          -- the full policy set, verbatim
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_hash ON policy_versions (version_hash);

-- Append-only, same discipline as actions_audit: a policy version that can be
-- rewritten is not provenance.
CREATE TRIGGER IF NOT EXISTS policy_versions_no_update
BEFORE UPDATE ON policy_versions
BEGIN
    SELECT RAISE(ABORT, 'policy_versions is append-only: UPDATE forbidden');
END;

CREATE TRIGGER IF NOT EXISTS policy_versions_no_delete
BEFORE DELETE ON policy_versions
BEGIN
    SELECT RAISE(ABORT, 'policy_versions is append-only: DELETE forbidden');
END;

-- Every decision records the rules that produced it. NULL only for rows written
-- before this migration existed.
ALTER TABLE actions_audit ADD COLUMN policy_version TEXT;

CREATE INDEX IF NOT EXISTS idx_audit_policy_version ON actions_audit (policy_version);

-- A pointer to whichever recorded version is currently in force. This one row IS
-- mutable, deliberately: provenance lives in policy_versions (append-only), while
-- this is only a cursor into it. Reverting an edit re-points here at the original
-- version row rather than creating a duplicate.
CREATE TABLE IF NOT EXISTS policy_current (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    version_hash TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
