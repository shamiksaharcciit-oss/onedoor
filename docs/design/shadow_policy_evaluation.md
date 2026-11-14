# Shadow policy evaluation

A candidate policy's own verdict for a request that was (or will be) actually
decided under the live policy, recorded for later comparison — never read by
the decision engine, never affecting a live decision.

## What it is

`onedoor.guardrail.shadow.evaluate(conn, policy, request, *, now, tz,
kill_switch_engaged)` answers one question: what would `policy` have decided
for `request`, right now? It checks, in the live engine's own order:

1. **Default-deny** — a policy with no real entry is denied, same as live.
2. **Tier, clamped by the kill switch**, resolved first as live's own first
   clamp does: `Tier.OBSERVE` is exempt; otherwise an engaged switch forces
   `Tier.CONFIRM`, and is recorded as *why*, even when the policy's own
   declared tier was already `CONFIRM`. `kill_switch_engaged` is a
   caller-supplied fact, never read from the database inside `evaluate` —
   so comparing several candidate policies against the same moment reads
   the switch once, and a caller studying a hypothetical can pass a value
   with no real switch to back it.
3. **An `OBSERVE` read returns here** — before bounds or caps are checked
   at all, matching live's own step 5.
4. **Bounds** — `onedoor.guardrail.bounds.validate`, the same pure function
   the live engine calls. Shared code, not a reimplementation that could
   drift from it.
5. **An engaged switch denies outright here**, after bounds and before
   caps, matching live's own step 7 — it does not propose, which would
   still fill the approval queue during an incident.
6. **Caps** — `onedoor.guardrail.caps.check_only`, a read-and-check-only
   sibling of `check_and_reserve` that shares every helper
   (`_read_all`/`_check_one`) with the real path, differing only in that it
   never calls `_reserve_all`. Checked against the action's own caps AND
   its effects' shared caps together (`policy.effects`, resolved through
   the same `PolicyStore.get_effect` live uses for them — a `param_effects`
   rule that would add more is outside this coverage, the rule itself not
   modeled), the same sources a live decision reserves. A held reservation
   already past its own deadline is counted as reclaimed in memory, the
   same way a real decision's own reclaim step would leave it, but without
   writing that reclaim — the one write `check_only` itself never performs,
   on top of never reserving.

`onedoor.guardrail.shadow.record(conn, request, shadow_decision, *,
policy_label, now, live_audit_id=None, live_decision=None)` persists the
verdict to a new table, `shadow_decisions` (migration 0049, extended by 0050) — a side record
the engine itself never reads back, linked by `request_id` and, optionally,
the real decision's own `actions_audit` row id.

## The coverage id

Every `ShadowDecision` and every `shadow_decisions` row carries a `coverage`
field: one stable id, `shadow.COVERAGE_ID = "limits-v1"`, naming exactly what
`evaluate` checked — default-deny, bounds, caps, tier clamped by the kill
switch. Not free text written fresh at each call site: a single constant,
defined once in `onedoor/guardrail/shadow.py`, read by `record` off the
`ShadowDecision` it is given, and read by `policy_tests.compare` to stamp its
own report. A future version of `evaluate` that checks more gets its own id
(`limits-v2`, or a new name) rather than redefining what `limits-v1` means —
a row recorded under `limits-v1` stays interpretable exactly as written,
whatever a later version adds.

**One sentence on what a shadow verdict answers, and what it does not:** it
answers what a policy's own default-deny, bounds, caps and tier (clamped by
the kill switch) would have decided; it does not answer what the live
engine's further escalation paths would have done, and a live decision
reached through one of those paths is marked as outside coverage, never
silently compared as though it agreed or disagreed (next section).

## A live decision beside the shadow verdict: marked, not blindly compared

`record`'s own `live_decision` parameter takes the real `PolicyDecision` a
request was actually given, when the caller has one -- specifically **the
decision the intent itself carries**, not one built fresh with its
resumption facts left out. `report_result` reads `approvers`/
`escalated_to`/`escalated_at` back from the intent's own audit row for
exactly this reason: an executed decision built without them would be
indistinguishable here from one that never resumed anything. Those
facts are attached only to the decision a caller is handed back, never
to the audit row itself -- `report_result`'s own row, and the intent's,
go on recording exactly what they always have.

A caller holding only a `PermittedIntent` -- never a `PolicyDecision` at
all, because nothing has executed or failed yet to report one -- has no
`live_decision` to pass. `record` still links the row to that intent by
`live_audit_id`, but with `live_decision=None` its own `comparison`
column is `None`: no agreement, no disagreement, not even "not modeled",
because nothing was compared. The shadow verdict is recorded, the intent
it sits beside is named, and that is the whole of what this case claims.

Its own resumption facts, not its reason code, take it out of comparison
first: `onedoor.guardrail.shadow._is_resumption` is the one place this
coverage decides whether a decision resumed an approval, an approval
reference, or a mandate ratification -- today, exactly
`live_decision.approvers is not None` (never `None` on a decision
`_decide_and_reserve` resolved a resumption for, even `[]` for a
mandate-only resumption no human approver acted on, or for a bare admin
override with no approval row to read one from). This is checked ahead of
the reason code entirely, since a resumed Tier-3 action executes with
reason code `passed` — itself in the modeled set below, and a comparison
that looked only at the reason code would wrongly compare a path this
coverage never modeled. Short of that, its own `reason_code` is
checked against a small, explicit set of reason codes `limits-v1` can be
compared against — the ones default-deny, bounds, caps, and the plain
tier/kill-switch clamp actually produce (`default_deny`, `bounds`,
`rate_exhausted`, `budget_exhausted`, `cost_unknown`, `kill_switch`,
`tier_confirm`, `passed`, `observe`). A live reason code outside that set —
`effect_floor`, a sequence-policy code, `dry_run`, `no_compensating_command`,
and a few others besides — names a path `limits-v1` does not model, and the
row's own `comparison` column says so in words: `"live decided by <path>;
not modeled"`, never folded into an `"agree"` or `"disagree"` it was never
actually compared against. The reason-code set is explicit and closed, not
"everything evaluate() doesn't deny for" — a reason code this module has
never heard of falls to "not modeled" too, by construction, the safer
default for a code added later that nobody has taught this module about
yet.

The row's own `decision`/`effective_tier`/`reason_code`/`detail` are always
the **shadow** verdict, never the live one — `live_reason_code` holds the
live decision's own reason code separately, so a reader can see both without
either overwriting the other.

## What it deliberately does not model, and why

The live engine's ordered pipeline (`decision._decide_and_reserve`) has grown
several further escalation paths beyond default-deny/bounds/caps/tier:
effect-level tier floors (an effect label can raise the tier a specific
action would otherwise get), sequence policies, approval-ref and mandate
resumption, dry-run, and the compensating-command check. None of these are
modeled here.

This is a disclosed scope cut, not an oversight. Replicating every escalation
path correctly — and keeping a second copy of that logic in step with the
first as it keeps growing — is a materially larger undertaking than the rest
of this round, and getting it subtly wrong would be worse than not having it:
a shadow verdict that silently disagrees with the live one for a reason
nobody wrote down defeats the point of the comparison. A shadow verdict
answers "what would this policy's own declared limits have allowed",
not "what would every escalation path the live engine has grown have done to
this exact request" — the two agree whenever no such path fires, which is
the common case for the kind of broad policy change (a bound moved, a cap
raised, a tier changed) this tool exists to preview. Full parity, if wanted,
is its own, later undertaking.

Nothing here is wired into `decide_and_reserve` itself. `evaluate`/`record`
are standalone, callable alongside a real decision by whatever already has
the connection and the request — a script, a scheduled job reading recent
`actions_audit` rows, or (later) an opt-in hook inside the engine's own
transaction. Not auto-wiring it into the hot path this round is itself a
disclosed choice: the live pipeline's own correctness is what every other
invariant in this engine depends on, and this feature's own correctness has
not yet had a release's worth of real use. Composing it in from outside costs
nothing in risk to the live decision; wiring it into the transaction that
decides real actions is real, valuable future work, done once shadow mode
itself has been exercised.

## Policy tests

`onedoor.guardrail.policy_tests.compare(conn, old_policy, candidate_policy,
requests, *, now, tz, kill_switch_engaged)` runs `shadow.evaluate` for each
request against both policies and returns a `PolicyTestReport`: a `coverage`
id (the same `shadow.COVERAGE_ID` every decision it compares was itself
stamped with) and `moved`, the cases where the decision differs — "which
decisions a policy change moves." Built on the same `evaluate`, so a policy
test and a shadow-mode run agree about what a policy decides by
construction, not by two implementations staying in sync by hand.
