-- A 0.12 feature's own receipt member (see onedoor.guardrail.preimage.EXCLUDED):
-- `resume_thread_id`/`resume_tool_call_id`, recorded on every `exec_intent` row
-- that carries a caller's resume key (LangGraph's `thread_id`/`tool_call_id`, or
-- any caller's own correlation pair), so a later call at the SAME key can find
-- an intent whose outcome is still unknown -- no `exec_result` row yet -- and
-- hold rather than risk a second execution of the same action
-- ("an unknown tool outcome holds the action", README Roadmap).
--
-- Both columns are deliberately outside the frozen row-preimage: an addition a
-- pre-0.12 verifier already ignores, not a new obligation on one that has never
-- heard of it, the same treatment every 0.11 feature's own receipt members got.
ALTER TABLE actions_audit ADD COLUMN resume_thread_id TEXT;
ALTER TABLE actions_audit ADD COLUMN resume_tool_call_id TEXT;

-- Looked up only for `kind='exec_intent'` rows, by (thread_id, tool_call_id);
-- partial so an ordinary row (the overwhelming majority, with both NULL) costs
-- this index nothing.
CREATE INDEX idx_actions_audit_resume_key_intent
    ON actions_audit (resume_thread_id, resume_tool_call_id)
    WHERE kind = 'exec_intent' AND resume_thread_id IS NOT NULL;
