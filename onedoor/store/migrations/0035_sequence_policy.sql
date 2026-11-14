-- Rules across a sequence (onedoor 0.11). A policy's own sequence
-- configuration: an optional `tag_as` (this action type's own label in
-- `sequence_events`, once it settles) plus a list of rules read against this
-- session's prior settled actions. Same JSON-blob shape as 0033's
-- untrusted_params_json: a typed, nested sub-object, not flat columns. NULL
-- means this action type neither tags itself nor checks history -- the
-- opt-in default every existing policy keeps.

ALTER TABLE policies ADD COLUMN sequence_json TEXT;
