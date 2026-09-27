-- A retired reason code's row can no longer carry its own "before or after
-- retirement" marker once a `protocol` bump did not accompany the
-- retirement: `cap_value` and `cap_rate` retired without one, so every row
-- from their birth onward carries the identical stamp either way, and a
-- timestamp is not a verified claim about when a row was sealed.
--
-- The upgrade itself is an event this database CAN record, once, honestly:
-- whatever the last audit row's id was at the moment this migration ran is
-- a real boundary, not an inference. A row at or before it predates the
-- upgrade that retired the code; a row after it was written under a
-- vocabulary that no longer had the code at all, so using it is either a
-- bug or a forgery, never an honest record.
--
-- Written once, by this migration, never touched again -- the same
-- append-only shape `actions_audit` already has, for the same reason: a
-- boundary that could be edited after the fact is not a boundary.

CREATE TABLE IF NOT EXISTS vocabulary_epochs (
    code                  TEXT PRIMARY KEY,
    retired_in_version    TEXT NOT NULL,
    last_audit_id_before  INTEGER NOT NULL
);

INSERT INTO vocabulary_epochs (code, retired_in_version, last_audit_id_before)
VALUES
    ('cap_value', '0.8.0', COALESCE((SELECT MAX(id) FROM actions_audit), 0)),
    ('cap_rate',  '0.8.0', COALESCE((SELECT MAX(id) FROM actions_audit), 0));

CREATE TRIGGER IF NOT EXISTS vocabulary_epochs_no_update
BEFORE UPDATE ON vocabulary_epochs
BEGIN
    SELECT RAISE(ABORT, 'vocabulary_epochs is append-only: UPDATE forbidden');
END;

CREATE TRIGGER IF NOT EXISTS vocabulary_epochs_no_delete
BEFORE DELETE ON vocabulary_epochs
BEGIN
    SELECT RAISE(ABORT, 'vocabulary_epochs is append-only: DELETE forbidden');
END;
