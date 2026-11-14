-- Feature: signed approval links (onedoor 0.11).
-- Single use: the nonce is recorded on first successful use. A repeat use
-- of the same nonce is refused, evaluated as absent -- the same anti-
-- probing posture as approval_ref/plan_ref (it does not say WHY it failed
-- beyond that).
--
-- Kept only until the token's own expiry, then pruned: the signature
-- already covers the expiry, so a nonce cannot be meaningfully reused
-- past it anyway (a live check refuses it on EXPIRED before this table is
-- ever consulted) -- see the design note's own "State" section.

CREATE TABLE IF NOT EXISTS approval_link_uses (
    nonce TEXT PRIMARY KEY,
    approval_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_approval_link_uses_expires_at
    ON approval_link_uses (expires_at);
