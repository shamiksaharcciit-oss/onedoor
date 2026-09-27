-- AADP -03 §10 (a MUST). Every verdict carries an evaluation_trace: the
-- ordered list of checks the engine actually evaluated for that decision (kind
-- 'decision' or 'exec_intent'), each entry naming the check, the rule it enforces,
-- the condition tested, the value/bound/state read, and the result
-- (pass | fail | unresolved). onedoor/guardrail/trace.py builds it; decision.py is
-- the only caller.
--
-- Deliberately DARK (unhashed): not in FIELD_ORDER (docs/row-preimage.md). Hashing a
-- brand-new evidence field in means a preimage version bump (/2 -> /3) and every
-- consequence R035 §1 catalogued for that -- a decision this ticket does not make on
-- delivery's own authority, since it changes wire-observable chain behaviour. Left
-- dark for now and disclosed as such; whether the trace should be tamper-evident is
-- an open question for core, not a code decision.
--
-- NULL on every row written before this column existed, and on any row this build
-- writes for a kind other than 'decision'/'exec_intent' (report_result never sets it
-- -- the trace is about how a verdict was reached, not what was reported afterward).

ALTER TABLE actions_audit ADD COLUMN evaluation_trace_json TEXT;
