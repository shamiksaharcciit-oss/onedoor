-- ND-002 / ND-003 / ND-039. The `0.4.0` row format: protocol stamp, structured
-- budget, report outcome, and the WHOLE receipt envelope.
--
-- `actions_audit` is append-only by trigger, so a column cannot be back-filled after
-- the fact. Every column therefore lands NULL-able, and the entire receipt envelope
-- lands NOW even though most of it stays empty until later increments -- otherwise
-- `0.4.1` (ND-001) and P3 (ND-017) would each need a migration against a table whose
-- past rows can never be updated. Migrate once, fill progressively.
--
-- DARK SURFACE, NOT UNUSED COLUMNS (E11, restated in R015). The receipt fields below
-- are declared and governed from the day they exist; ND-038's enforcement-before-
-- emission rule covers anything read from them. Nothing may emit or rely on a value
-- these columns do not yet carry.
--
-- NULL VERSUS EMPTY (R015, ruled in R016 section 1). A NULL meaning "not yet
-- produced" must be distinguishable from one meaning "produced empty":
--   * digest columns -- free, because a produced-but-empty digest is sha256("") =
--     e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855, a real value
--     that is not NULL;
--   * prev_hash -- NOT free, and ruled: the genesis row carries SIXTY-FOUR ASCII '0'
--     characters, an affirmative in-band statement that no predecessor exists. NULL
--     then retains exactly one meaning: not yet chained. A `chain_state` column was
--     refused as a second answer to a question prev_hash already answers (X-14), and
--     putting the last unchained row's id here was refused as a kind violation -- a
--     hash-typed field must not carry an identifier.

ALTER TABLE actions_audit ADD COLUMN protocol TEXT;
-- Absent => read the row under aadp/0.1 (E6). Rows written from 0.4.0 always stamp it.

ALTER TABLE actions_audit ADD COLUMN budget_json TEXT;
-- ND-003. Present iff the verdict is deny and the reason is cap_value or cap_rate.
-- Persisted, not merely returned: cap_value collapses the day and month windows, so
-- without this the evidence store cannot tell which window a denial broke -- a
-- granularity regression against 0.3.5, where the reason code alone carried it.

ALTER TABLE actions_audit ADD COLUMN outcome TEXT;
-- ND-039. success | failure | timeout | not_attempted, on exec_result rows.
-- Settlement is outcome-dependent: settle on the first three, RELEASE on
-- not_attempted as an audited event (R005). Settle-on-doubt -- release requires a
-- positive assertion of non-occurrence, never an absence of information.

-- ND-001 (0.4.1): the chain. Dark until then.
ALTER TABLE actions_audit ADD COLUMN prev_hash TEXT;
ALTER TABLE actions_audit ADD COLUMN seq INTEGER;
ALTER TABLE actions_audit ADD COLUMN row_hash TEXT;

-- ND-015 (P2): signatures. Dark until then.
ALTER TABLE actions_audit ADD COLUMN sig TEXT;
ALTER TABLE actions_audit ADD COLUMN key_id TEXT;
ALTER TABLE actions_audit ADD COLUMN alg TEXT;

-- ND-017 (P3): the re-derivable verdict manifest and its anchor. Dark until then.
-- E/I/T are carried as opaque content-addressed digests and NEVER as inlined
-- structures: I's preimage will generalise from verdict instruments to
-- stage-attribution instruments, and inlining it would re-hash frozen rows, which is
-- fatal on an append-only store.
ALTER TABLE actions_audit ADD COLUMN e_digest TEXT;
ALTER TABLE actions_audit ADD COLUMN i_digest TEXT;
ALTER TABLE actions_audit ADD COLUMN t_digest TEXT;
ALTER TABLE actions_audit ADD COLUMN v_digest TEXT;
ALTER TABLE actions_audit ADD COLUMN anchor_ref TEXT;

-- The chain walks in row order; ND-001's verifier and ND-017's anchoring both need
-- that lookup cheap, and adding the index now costs nothing while the table is small.
CREATE INDEX IF NOT EXISTS idx_actions_audit_seq ON actions_audit (seq);
