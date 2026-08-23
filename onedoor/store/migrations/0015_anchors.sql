-- ND-017 / M2. Published Merkle roots, each covering a contiguous range of chained rows.
--
-- An anchor points at the ROWS; the rows do not point at the anchor. That is not a
-- style choice -- `anchor_ref` on actions_audit CANNOT BE WRITTEN. Anchoring necessarily
-- happens after a row is sealed, and the actions_audit_no_update trigger forbids UPDATE.
-- Verified against a live store rather than assumed: the UPDATE raises
-- "actions_audit is append-only". So membership is resolved by looking up which anchor
-- covers a row's `seq`, and `anchor_ref` stays dark.
--
-- It is also the better shape: a back-reference would be a second answer to a question
-- the range already answers (X-14), and it would need a writable column on the one
-- table whose entire value is that it cannot be written.
--
--   root       the RFC 6962 Merkle root over the range's row_hash leaves.
--   tree_size  leaf count -- an inclusion proof needs it, and it is not derivable from
--              the range alone once rows can be absent.
--   cadence    DECLARED HERE, not in the decision instrument (R040 §2). Cadence
--              schedules anchoring, not deciding: inside `I` an ops-schedule tweak would
--              re-identify the DECIDING instrument for every row after it, splitting
--              i_digest cohorts for a reason no instrument comparison should care about.
--              Recorded on the anchor, where a change is visible in exactly the artifact
--              stream it governs.
--
-- Append-only for the same reason as the keyring: a published root is evidence, and a
-- root someone can quietly withdraw is not an anchor.

CREATE TABLE IF NOT EXISTS anchors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    root       TEXT NOT NULL,
    tree_size  INTEGER NOT NULL,
    first_seq  INTEGER NOT NULL,
    last_seq   INTEGER NOT NULL,
    cadence    TEXT NOT NULL,
    sealed_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anchors_range ON anchors (first_seq, last_seq);

CREATE TRIGGER IF NOT EXISTS anchors_no_update
BEFORE UPDATE ON anchors
BEGIN SELECT RAISE(ABORT, 'anchors is append-only: a published root cannot be withdrawn'); END;

CREATE TRIGGER IF NOT EXISTS anchors_no_delete
BEFORE DELETE ON anchors
BEGIN SELECT RAISE(ABORT, 'anchors is append-only: a published root cannot be withdrawn'); END;
