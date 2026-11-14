-- Approving a plan once (onedoor 0.11): a bounded,
-- pre-approved set of action types, ceilings, a recipient set and an
-- expiry, that a later call can match against to satisfy the ordinary
-- approval step its own nominal tier would otherwise require, with no
-- fresh prompt. Proposed by an agent or an operator; active only once a
-- different identity approves it (`approved_by` stays NULL until then).
--
-- `action_specs_json` maps action type name to its own `amount_param`/
-- `recipient_param` (which of that action's own params carries an amount or
-- a recipient, if any). `recipients_json` is a JSON array (a set has no
-- native column type). `amount_ceiling`/`consumed_amount` are canonical
-- decimal strings, the same convention every other money-shaped column on
-- this store already uses.

CREATE TABLE plans (
    id INTEGER PRIMARY KEY,
    proposed_by TEXT NOT NULL,
    approved_by TEXT,
    action_specs_json TEXT NOT NULL,
    count_ceiling INTEGER NOT NULL,
    amount_ceiling TEXT NOT NULL,
    recipients_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_count INTEGER NOT NULL DEFAULT 0,
    consumed_amount TEXT NOT NULL DEFAULT '0',
    state TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    approved_at TEXT
);

CREATE INDEX idx_plans_state ON plans (state);
