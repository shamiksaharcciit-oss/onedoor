-- A LangGraph resume re-executes the interrupted node from the top, including the
-- code that proposes the action -- so a resumed proposal attempt must find its
-- original approval row rather than create a second, never-granted one.
--
--   thread_id       -- the caller's session identity (e.g. LangGraph's own
--                      `configurable.thread_id`), when the caller has one.
--   tool_call_id    -- the specific call within that session a proposal answers.
--   request_digest  -- resume_digest(action_type, params) at the moment this row
--                      was created (onedoor/guardrail/approvals.py), so a later
--                      resume can be CHECKED against what was actually proposed,
--                      never trusted to match just because the keys do.
--
-- NULL on every row written before this migration, and on every row from a caller
-- that never passes the pair (the HTTP service, the MCP integration, direct engine
-- calls) -- SQLite's unique index below never collides two NULLs, so none of that
-- is constrained by it.
ALTER TABLE approvals ADD COLUMN thread_id TEXT;
ALTER TABLE approvals ADD COLUMN tool_call_id TEXT;
ALTER TABLE approvals ADD COLUMN request_digest TEXT;

-- Partial, on state IN ('pending', 'ratified', 'approved'): at most one row IN
-- FLIGHT per resume key, not one EVER -- the same three states
-- `find_by_resume_key` (approvals.py) treats as reusable, and only those: a
-- resume reuses its row for as long as it is in flight AND not past its own
-- `expires_at` (which `find_by_resume_key` itself expires on the way out),
-- and gets a fresh one otherwise. All three in-flight states are covered
-- because `wrap_tool_call`'s own re-execution on resume decides twice --
-- once with no reference (must find the row whichever of the three a human,
-- or the mandate authority, has left it in) and once with the reference
-- (consumes it) -- so the row the first of those two decisions finds must
-- still be there for the second, never a second pending row created beside
-- it. A row that has been consumed, denied or expired is done with -- and a
-- later resume with the same key must be free to get a fresh pending
-- approval of its own. A plain (non-partial) unique index would make that
-- INSERT fail outright once the original row left this set, turning an
-- ordinary later resume into a crash.
CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_resume_key ON approvals (thread_id, tool_call_id)
    WHERE state IN ('pending', 'ratified', 'approved');
