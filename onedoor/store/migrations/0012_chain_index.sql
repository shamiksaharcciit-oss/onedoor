-- ND-001 / C2. One chain ordinal, enforced by the database rather than by the walker.
--
-- The chain COLUMNS already exist: prev_hash, seq and row_hash landed in 0007, dark,
-- so that P1 would not have to migrate an append-only table. This migration adds only
-- an index, and it adds it for a reason that is not performance.
--
-- `seq` is the chain's ordinal because `id` cannot be: the append-only triggers forbid
-- UPDATE, so row_hash must be computed BEFORE the INSERT that assigns `id`. That
-- leaves two orderings over one table, which X-14 warns is a disagreement waiting for
-- its first bug. The resolution is declared rather than hoped for -- seq is
-- authoritative for the chain, id is a storage detail -- and this index makes the
-- database refuse the ambiguity instead of leaving a walker to discover it.
--
-- A partial index, so the unchained prefix is not affected: every row written before
-- ND-001 has seq NULL, and SQLite would otherwise treat many NULLs as distinct
-- anyway. Being explicit about it says what is intended rather than relying on that.
CREATE UNIQUE INDEX IF NOT EXISTS actions_audit_seq_unique
    ON actions_audit(seq) WHERE seq IS NOT NULL;

-- No ordering index is added here: 0007 already created idx_actions_audit_seq for
-- exactly this walk. Checked before writing rather than after -- a second index over
-- the same column would have cost writes on every append forever to buy nothing, and
-- would have looked deliberate to the next reader.
