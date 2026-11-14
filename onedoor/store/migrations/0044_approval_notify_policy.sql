-- Feature: signed approval links (onedoor 0.11).
--
-- policies.approval_notify_json  -- same JSON-blob shape as approval_json/
--                                    sequence_json: a typed, nested sub-
--                                    object, not flat columns. NULL means
--                                    no link is ever built or sent for this
--                                    action type's approvals -- the opt-in
--                                    default every existing policy keeps.

ALTER TABLE policies ADD COLUMN approval_notify_json TEXT;
