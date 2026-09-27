-- WO-D6 part 2: a resumption's own re-evaluation row can name the proposal it
-- resumes. Canary showed, with real fixtures, that a resumption's audit row
-- carries no field linking it to the proposal it resumes -- a link an earlier
-- ruling assumed existed but that no row actually carried.
--
-- Nullable and set only on a resumption (an approval or a mandate
-- ratification resuming through evaluate_and_execute). Existing rows are
-- never rewritten: a pre-0.8.1 resumption simply has no link, read as such
-- rather than guessed at.

ALTER TABLE actions_audit ADD COLUMN resumes_audit_id INTEGER;
