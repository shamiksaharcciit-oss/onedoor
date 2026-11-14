-- Two-person rule and escalation (onedoor 0.11, "Two-person rule and
-- escalation"). A policy's own `approval` block (two_person_above_eur,
-- escalate_after_seconds), and the approvals-table state it needs.
--
-- policies.approval_json  -- same JSON-blob shape as untrusted_params_json/
--                             sequence_json: a typed, nested sub-object, not
--                             flat columns. NULL means neither the two-person
--                             rule nor escalation applies -- the opt-in
--                             default every existing policy keeps.
--
-- approvals.approvers_json   -- JSON list of distinct approver identities
--                                recorded so far, in order. '[]' until the
--                                first approver.
-- approvals.backup_approver  -- the identity escalation assigned, once due.
--                                NULL until escalation fires, or if it never
--                                does.
-- approvals.escalated_at     -- when escalation set backup_approver. NULL
--                                until then.
--
-- plans.approvers_json       -- same shape as approvals.approvers_json, for
--                                a design requirement on top of the general
--                                two-person rule: a plan whose
--                                amount_ceiling crosses its own actions'
--                                two-person threshold needs two different
--                                approvers, neither the proposer, before it
--                                activates. '[]' until the first approver;
--                                `approved_by` (0038) still names the LAST
--                                approver once active, same as `approvals.
--                                decided_by_session` does.

ALTER TABLE policies ADD COLUMN approval_json TEXT;

ALTER TABLE approvals ADD COLUMN approvers_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE approvals ADD COLUMN backup_approver TEXT;
ALTER TABLE approvals ADD COLUMN escalated_at TEXT;

ALTER TABLE plans ADD COLUMN approvers_json TEXT NOT NULL DEFAULT '[]';
