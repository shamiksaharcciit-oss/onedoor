-- Adds `coverage`, `live_reason_code` and `comparison` to `shadow_decisions`
-- as a forward-only migration rather than an in-place amendment to 0049
-- itself: `schema_migrations` (see `onedoor/store/db.py`'s
-- `run_migrations`) tracks a migration by filename alone, never by
-- content, so a store that already applied 0049 before these columns
-- existed could not otherwise gain them by changing 0049 in place. Runs
-- once, on top of 0049 exactly as this release ships it (see
-- `0049_shadow_decisions.sql`).
--
-- See `onedoor/store/migrations/UPGRADE_NOTES.md` for a shape of 0049 this
-- migration does not run against.
--
-- `coverage` is NOT NULL with a default so this still works against a store
-- that already holds rows written before this column existed -- SQLite
-- requires one for a NOT NULL column added via ALTER TABLE. The default
-- matches `shadow.COVERAGE_ID`'s own value at the time this migration was
-- written; a row written under a later coverage id always states its own
-- value explicitly, this default only backfills rows that predate the
-- column entirely.

ALTER TABLE shadow_decisions ADD COLUMN coverage TEXT NOT NULL DEFAULT 'limits-v1';
ALTER TABLE shadow_decisions ADD COLUMN live_reason_code TEXT;
ALTER TABLE shadow_decisions ADD COLUMN comparison TEXT;
