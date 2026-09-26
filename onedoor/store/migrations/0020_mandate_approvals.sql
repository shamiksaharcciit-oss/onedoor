-- WO-D2 step 3, AADP -03 §8.1: mandate-layer deferral.
--
-- A PENDING mandate verdict creates a Tier-3-shaped approval row exactly as any
-- propose does, but it MUST resolve only through a verified ratification from the
-- mandate authority (ruling 26e: the existing admin approval routes are not used).
--
--   mandate_authority   -- 1 iff this approval waits on a mandate-layer ratification,
--                          never resolvable via approvals.cas_approve/deny (both
--                          refuse structurally when this is set, not only at the
--                          HTTP layer). NULL/0 on every ordinary Tier-3 approval.
--
--   mandate_core_digest -- the digest (onedoor/guardrail/mandate.py's core_digest())
--                          a ratification must name to resolve THIS approval. Unique
--                          per pending decision, which is what makes a ratification
--                          signed for one record refuse against any other: its
--                          digest simply will not match.
--
-- NULL on every row written before this column existed, and on every non-mandate
-- approval from this point on.

ALTER TABLE approvals ADD COLUMN mandate_authority INTEGER;
ALTER TABLE approvals ADD COLUMN mandate_core_digest TEXT;
CREATE INDEX IF NOT EXISTS idx_approvals_mandate_core_digest ON approvals (mandate_core_digest);
