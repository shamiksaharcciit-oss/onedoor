-- 0052's unique index folds every unauthenticated proposer into one bucket
-- using the text 'onedoor:no-principal-resume-key' -- a fold distinct from
-- the one `onedoor.guardrail.approvals.principal_matches` already uses for
-- the same purpose (`_NO_PRINCIPAL`, a NUL-prefixed byte string, chosen
-- because `onedoor.guardrail.keys.fingerprint` never produces a NUL byte).
--
-- Both sentinels are individually safe -- neither is a value a real
-- fingerprint can ever produce -- but a principal whose identity happened
-- to equal 0052's literal text would share the no-principal bucket in this
-- index while `principal_matches` would still correctly tell the two
-- apart: an asymmetry between the two layers that should not exist even
-- though nothing reachable today can trigger it. This migration recreates
-- the index with the SAME fold `principal_matches` uses, so a principal
-- can never share the no-principal bucket in one layer and not the other.
--
-- Safe on a store that has already run 0052: the new sentinel is just as
-- unproducible by a real fingerprint as the old one, so the index's
-- equivalence classes -- which rows collide with which -- are unchanged;
-- only the unused placeholder text changes. No row's data changes, and the
-- one case that mattered (two genuinely unauthenticated proposals
-- colliding at one key) still collides exactly as before.
DROP INDEX IF EXISTS idx_approvals_resume_key;

CREATE UNIQUE INDEX idx_approvals_resume_key ON approvals (
    thread_id, tool_call_id, COALESCE(proposed_by, CHAR(0) || 'onedoor/no-principal')
) WHERE state IN ('pending', 'ratified', 'approved');
