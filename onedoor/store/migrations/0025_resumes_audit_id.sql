-- A resumption's own re-evaluation row can name the proposal it resumes.
-- Measured against real fixtures: a resumption's audit row carried no field
-- linking it to the proposal it resumes, though it had been assumed to.
--
-- Nullable and set only on a resumption (an approval or a mandate
-- ratification resuming through evaluate_and_execute). Existing rows are
-- never rewritten: a pre-0.8.1 resumption simply has no link, read as such
-- rather than guessed at.

ALTER TABLE actions_audit ADD COLUMN resumes_audit_id INTEGER;
