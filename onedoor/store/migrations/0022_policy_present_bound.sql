-- AADP -03 §6. The per-action-type declared audience URI a permit
-- is bound to. Same shape as 0021: the policies table is explicit SQL columns,
-- not a JSON blob, so a new Policy field needs its own migration.

ALTER TABLE policies ADD COLUMN present_bound TEXT;
