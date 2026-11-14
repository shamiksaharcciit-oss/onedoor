-- the decision RECEIPT (actions_audit), not only the
-- approvals-table state migration 0040 already carries, must name who
-- approved a two-person resumption.
--
-- actions_audit.approvers_json  -- every distinct identity recorded on the
--                                   approval this decision resumed, in order.
--                                   NULL on a decision that did not resume an
--                                   approval at all (every row before this
--                                   feature existed, and every ordinary
--                                   propose/deny/permit today); a real value
--                                   -- even '[]' for a mandate-only
--                                   resumption with no approver -- on one
--                                   that did.
-- actions_audit.escalated_to    -- the backup approver escalation assigned
--                                   to that approval, if it ever fired. NULL
--                                   under the same condition as approvers_json
--                                   being NULL, or if escalation never fired.
-- actions_audit.escalated_at    -- when escalation set escalated_to. NULL
--                                   under the same condition as escalated_to.
--
-- Outside the frozen row preimage (onedoor/row-preimage/7 stays /7); inside
-- the decision digest when set, the same OMIT_WHEN_NONE treatment as
-- untrusted_matched_json, the sequence columns, and the plan columns before
-- it -- see onedoor/guardrail/preimage.py's EXCLUDED and
-- onedoor/decision_digest.py's OMIT_WHEN_NONE.

ALTER TABLE actions_audit ADD COLUMN approvers_json TEXT;
ALTER TABLE actions_audit ADD COLUMN escalated_to TEXT;
ALTER TABLE actions_audit ADD COLUMN escalated_at TEXT;
