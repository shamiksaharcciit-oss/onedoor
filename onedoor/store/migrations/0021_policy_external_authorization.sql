-- WO-D2 step 3, AADP -03 §8.1. The per-action-type declaration that a mandate
-- authority must be consulted before any other check runs. Same seam shape as
-- requires_step_up: a boolean column, defaulted off, so every existing policy is
-- unaffected until a deployer opts an action type in.

ALTER TABLE policies ADD COLUMN requires_external_authorization INTEGER NOT NULL DEFAULT 0;
