-- ND-052 / S1-B2. The Studio's own table. It is not the ledger, and that is the point.
--
-- R042 §3: a backtest writes NOTHING to the decision ledger -- not a decision row, not
-- a marker, not a "backtest ran" breadcrumb. `actions_audit` is the enforcer's record;
-- the Studio is a proposer, and constitution principle 1 does not bend for evidence's
-- sake. The evidence question has a better answer, and the crypto epic already built it:
-- the backtest BORROWS the ledger's witness by citing the sealed chain.
--
--   row_hash_at_last_seq  NOT NULL, deliberately. This is the citation that does the
--                         work: a forged "we tested against production" claim now
--                         requires forging the chain -- the thing ND-001 through ND-017
--                         made hard. A receipt whose citation is null would be the store
--                         vouching for itself, so the engine REFUSES to run against an
--                         unchained store rather than writing one (R043 §2).
--
--   ledger_provenance     `live` | `fixture`, and there is no third value. It describes
--                         the CITED RANGE, not the store: a sealed chain with an
--                         unchained prefix is `live` over the chained span with the
--                         prefix counted as a skip, because a range that cannot be cited
--                         is not replayed.
--
--   backtest_digest       the receipt's own content address, over the canonical body
--                         with this field absent -- the manifest pattern. Same run twice
--                         gives the same digest, which makes re-runs comparable for free.
--
-- Append-only like everything else that holds evidence: a backtest result someone can
-- quietly revise is not a result.

CREATE TABLE IF NOT EXISTS backtest_receipts (
    backtest_digest      TEXT PRIMARY KEY,
    policy_digest        TEXT NOT NULL,
    ledger_provenance    TEXT NOT NULL,
    first_seq            INTEGER NOT NULL,
    last_seq             INTEGER NOT NULL,
    row_hash_at_last_seq TEXT NOT NULL,
    body_json            TEXT NOT NULL,
    created_at           TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS backtest_receipts_no_update
BEFORE UPDATE ON backtest_receipts
BEGIN SELECT RAISE(ABORT, 'backtest_receipts is append-only'); END;

CREATE TRIGGER IF NOT EXISTS backtest_receipts_no_delete
BEFORE DELETE ON backtest_receipts
BEGIN SELECT RAISE(ABORT, 'backtest_receipts is append-only'); END;
