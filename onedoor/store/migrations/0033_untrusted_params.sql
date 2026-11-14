-- Untrusted-input checks (onedoor 0.11). The per-action-type `deny`/`hold`
-- lists checked against the request's own caller-marked `untrusted` paths.
-- Same JSON-blob shape as 0002's effects_json/param_effects_json: a typed,
-- nested sub-object, not flat columns. NULL means this action type never
-- checks provenance -- the opt-in default every existing policy keeps.

ALTER TABLE policies ADD COLUMN untrusted_params_json TEXT;
