-- ND-002 / W7. Row-level provenance for the frozen params and payload bytes.
--
-- E10, as finally ruled by R004: received data is frozen VERBATIM at ingress and
-- never re-serialized -- the `parse -> json.dumps(default=str)` round trip is
-- abolished, and the stored bytes are the received bytes. Generated structures
-- (budget_json, the receipt envelope) are canonicalised instead.
--
-- But not every enforcement point receives bytes. The in-process library binding is
-- handed Python objects directly, so there are no received bytes to freeze; R004
-- rules that its frozen form is ONE canonical serialization at ingress, and that
-- **the row must make that provenance distinguishable**. Without this column a
-- reader cannot tell "these are the bytes the PEP sent" from "these are bytes this
-- PDP produced" -- and only the first can be re-derived against what the caller
-- actually transmitted.
--
--   received   -- params_json holds the exact bytes the enforcement point sent
--   serialized -- the caller passed objects; this PDP produced these bytes once,
--                 canonically, at ingress
--   NULL       -- written before 0.4.0, when the round trip was still in force and
--                 the bytes were neither verbatim nor canonical. Absent means
--                 "unknown provenance", by the same absent-value rule as an
--                 unstamped protocol column meaning aadp/0.1. Do not infer either
--                 value for an old row: the whole point is that it cannot be known.
--
-- No `received_digest` column, deliberately (R004): the frozen bytes are stored, so
-- the digest is derivable. A stored digest beside stored bytes is a second answer to
-- a question the bytes already answer (X-14).

ALTER TABLE actions_audit ADD COLUMN params_provenance TEXT;
ALTER TABLE actions_audit ADD COLUMN payload_provenance TEXT;
