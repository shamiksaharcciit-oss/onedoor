-- Migration 0030's unique index enforced at most one in-flight row per
-- (thread_id, tool_call_id) GLOBALLY -- which is exactly the shape the
-- cross-principal finding (migration 0051) needs undone: once the lookup
-- itself is scoped to the caller's principal, a second principal presenting
-- the same key must be free to get its OWN fresh, in-flight row, not crash
-- against the first principal's.
--
-- The replacement index adds the principal to the uniqueness key, so
-- dedup/race-protection applies per (thread_id, tool_call_id, principal), not
-- globally per (thread_id, tool_call_id). `COALESCE(proposed_by, ...)` folds
-- every unauthenticated proposer into one shared bucket -- the same bucket
-- `approvals.principal_matches` already treats `None` as its own distinct,
-- but still single, identity -- rather than relying on SQL's own NULL-is-
-- never-equal-to-NULL uniqueness semantics, which would otherwise drop
-- race-protection entirely for every unauthenticated proposer.
--
-- The sentinel string is chosen only to be a value no real principal can
-- equal: `onedoor.guardrail.keys.fingerprint` always produces a fixed-length
-- hex digest, never this literal text.
DROP INDEX IF EXISTS idx_approvals_resume_key;

CREATE UNIQUE INDEX idx_approvals_resume_key ON approvals (
    thread_id, tool_call_id, COALESCE(proposed_by, 'onedoor:no-principal-resume-key')
) WHERE state IN ('pending', 'ratified', 'approved');
