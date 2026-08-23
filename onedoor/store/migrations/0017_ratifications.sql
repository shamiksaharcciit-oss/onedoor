-- ND-052 / S2-T4. The ratification receipt: the act that turned a candidate into a
-- version, recorded so the act itself can be checked later rather than inferred from
-- the fact that a version exists.
--
-- `policy_versions` already answers "what was in force"; it cannot answer "who put it
-- there, from what, on the strength of which evidence, and with the door open or shut".
-- That is what this table holds, and none of it is derivable from the version alone.
--
--   from_version          NULL is the first ratification on a fresh store -- ABSENT,
--                         not empty, and distinguishable from a store whose previous
--                         version happened to go unrecorded. R015 in a column.
--
--   backtest_digest       NULLABLE, and its absence is INFORMATIVE (R045 §4). Ratifying
--                         without a backtest is allowed -- refusing would block the
--                         first policy on a fresh store, where there is nothing to
--                         backtest against. Where a digest IS present, the ceremony has
--                         already verified that it resolves in this store and that its
--                         `policy_digest` equals `candidate_digest`: a citation nobody
--                         checks is decoration, and citing someone else's homework is
--                         made structurally impossible rather than discouraged.
--
--   kill_switch_engaged   R045 §5. The switch does NOT block ratification -- it wins
--                         over every action, so nothing ratified can move while it
--                         holds, and the moment of risk is the LIFT, not the
--                         ratification. So the state is recorded instead of enforced,
--                         and it is inside the receipt's digest: visible forever,
--                         deniable never.
--
--   ratified_by_session   NOT `ratified_by`. onedoor has no authenticated per-caller
--                         identity, so this is a DECLARED session string, and the
--                         longer name carries its own caveat where the shorter one
--                         would read as an identity claim to every future reader of an
--                         export. A field's name is part of its honesty (R045 §3). An
--                         authenticated principal is `onedoor/ratification/2`.
--
--   ratification_digest   the receipt's own content address, over the canonical body
--                         with this field absent -- the manifest pattern, as in
--                         `backtest_receipts`.
--
-- Append-only, like everything else here that holds evidence. A record of who changed
-- the rules that the rule-changer can quietly revise is not a record.

CREATE TABLE IF NOT EXISTS ratifications (
    ratification_digest TEXT PRIMARY KEY,
    from_version        TEXT,
    to_version          TEXT NOT NULL,
    candidate_digest    TEXT NOT NULL,
    backtest_digest     TEXT,
    kill_switch_engaged INTEGER NOT NULL,
    ratified_by_session TEXT NOT NULL,
    body_json           TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ratifications_to_version ON ratifications(to_version);

CREATE TRIGGER IF NOT EXISTS ratifications_no_update
BEFORE UPDATE ON ratifications
BEGIN SELECT RAISE(ABORT, 'ratifications is append-only'); END;

CREATE TRIGGER IF NOT EXISTS ratifications_no_delete
BEFORE DELETE ON ratifications
BEGIN SELECT RAISE(ABORT, 'ratifications is append-only'); END;
