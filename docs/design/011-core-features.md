# onedoor 0.11: the next seven features

Design for seven features built on top of the engine as it stands. Each is
opt-in in the policy: an action type whose policy declares none of a
feature's own fields decides exactly as before that feature existed — the
same decision, the same reason code, the same receipt shape. Every feature
works through both entry points, the library (`decide_and_reserve`/
`report_result`) and the decision service's own HTTP API, and through the MCP
gateway wherever a gateway call can reach it. Where a feature cannot decide
honestly — state missing, a store unreachable, an input it cannot read — the
action is denied or held exactly as the policy says, never allowed; the
reason code always says which check produced the refusal.

Wording throughout: an action is **stopped** (denied or refused outright),
**held** (proposed, awaiting a person), or **carried out** (permitted, and
reported as executed). A difference between two decisions is stated as what
differed, not narrated as to why one happened and the other didn't — the
receipt records the check that produced each verdict, which is the honest
account; a causal story on top of it would be a claim this engine is not in
a position to make.

## Untrusted-input checks

Extends the existing recipient-only check (an allow-list of recipients per
action, already shipped) to any key argument — recipient, amount, URL, path,
command — and to what makes a value worth stopping on: the caller's own
assertion that the value came from content it does not control, stated
plainly at the call, never a guess onedoor makes from the string's shape.

### How a caller marks a value

A mark travels with the argument path, never with the value's content. The
engine has no way to tell a scraped account number from a typed one by
looking at the bytes, and guessing would be a silent, undocumented heuristic
exactly the shape this project exists to refuse. `ActionRequest` gains:

```python
untrusted: list[str] = Field(default_factory=list)
"""Dotted paths into `params` the caller asserts are derived from content it
does not control (a web page, an email body, a tool's own prior result).
Caller-declared only; never inferred from `params`' own content. Absent
means nothing is marked -- the default, and the only state a 0.10.x caller
can produce."""
```

A path matches a policy's own list by exact string equality — the same
precision discipline as every other exact-location match in this codebase
(a glob or prefix match can silently cover, or silently miss, a path nobody
checked). **A value derived from a marked value is marked by the caller
that derives it** — carried forward the same way `params_raw` is: the
enforcement point that builds each new call is the one place that knows a
value came from a prior marked one, and it is the one place obligated to say
so again. onedoor does not trace a value's lineage across calls itself;
tracing it is the caller's job, and claiming otherwise would be a claim this
engine cannot back.

### Policy syntax

```yaml
policies:
  - action_type: messages.send
    tier: 2
    untrusted_params:
      deny: [command, path]       # any marked path here: denied outright
      hold: [recipient, body.url] # any marked path here: held for a person
```

A path named in `deny` wins over one named in `hold`; a path named in
neither has no effect, whether or not the caller marked it — the policy
author decides which of an action's own arguments are worth this check, the
same opt-in discipline as bounds and caps. Checked before bounds and caps:
an untrusted-input refusal is about where a value came from, not what it
is, and a denied-for-provenance call should never reach budget reservation.

### API

`ActionRequest.untrusted` (library and service — the service's `DecideBody`
gains the same field, same name). No new call; the existing
`decide_and_reserve` reads it as one more input alongside `params`.

### Receipt members

`untrusted_matched: list[str]` — which of the caller's own marked paths
actually matched a `deny` or `hold` entry (empty when none did, even if
`untrusted` itself was non-empty — a caller marking paths the policy does
not check about is not itself news).

### Reason code

`CheckId.UNTRUSTED_INPUT`. A new code, added the same way every prior one
was: nothing reads a stored `reason_code` by switching on which string it
is, so an older reader simply sees a code it has not met yet and goes by
the `Decision` it is attached to, exactly as it already must.

### Fail closed

A caller-declared path absent from both `deny` and `hold` is inert, by the
policy author's own choice — not a second failure mode to guard. A path in
`untrusted` that does not correspond to anything in `params` matches
nothing and is likewise inert; there is no value there to have come from
anywhere.

### State

None kept across calls — this check is evaluated per call, from what the
same call already carries.

### Through the gateway

A tool's own call shape is `arguments`-shaped, not `params`-shaped (see the
mapping file, already shipped) — the caller marks a path in the tool's own
argument shape, `_meta["onedoor/untrusted"]: ["arguments.to"]`, and the
gateway resolves each marked tool-argument path to the onedoor param name
the mapping already maps it to (the mapping's own `{onedoor_name: path}`
table, read in reverse) before it ever builds the `ActionRequest`. A marked
path absent from the mapping is inert the same way an unrecognised policy
path is — nothing to translate it onto.

### Non-claims

onedoor marks only what the caller marks, and trusts the caller's own
declaration at the call it is given on — not a claim that it has audited
where a value truly came from, and not a claim that an unmarked value truly
is trusted. A caller that mismarks a value is not detected. **This check
protects where the marking is done by code outside the model's own
control** — the host or the framework wrapping it, deciding before the model
ever sees a value whether it came from content the model does not control.
An agent misled by injected content does not mark the values it was misled
into; it does not know it was misled. This check does not defend against
that case, which is exactly why "Rules across a sequence" (below) exists as
a second, independent defence that does not depend on the agent noticing
anything at all.

### The defence that does not depend on the agent

A sequence rule (the next feature) tags a *read* of untrusted content, not
the action it later influences — the tag is attached by the same
host-or-framework code this feature already trusts, at the moment of the
read itself, before any model has had a chance to be misled by what it read.
A later action is then held or denied for having followed such a read within
a window, whether or not the model marked anything about it. The example
under "Rules across a sequence" shows exactly this: `web.fetch` and
`email.read` tagged `untrusted_content`; `messages.send` and `payments.*`
held `after_tag: untrusted_content`.

### Tests

a deny-listed marked path is denied outright, at a tier that would
otherwise auto-execute; a hold-listed marked path is proposed, never
executed automatically; an unmarked value at the same path decides as
before this feature existed; a marked path the policy names in neither list
has no effect; a derived value re-marked by the caller on its own later call
enforces there, with no cross-call tracing inside the engine; the gateway
resolves a tool's own argument path to the right onedoor param through the
mapping; a policy naming no `untrusted_params` block decides identically to
its 0.10.x self.

## Rules across a sequence

Policies over what came before, in the same session: "after a read labelled
secret, hold any message to an outside recipient"; "no second refund over a
threshold within a day."

### Session state

`ActionRequest` already carries a `session_id` field, unused by the engine
today (confirmed by reading every call site: nothing currently reads it off
a request at decision time). This feature adopts it as the sequence key —
**a different `session_id` from `onedoor.guardrail.approvals`' own parameter
of the same name**, which identifies an *approver*, not a caller's session;
the two are unrelated, and this note does not touch the approvals one.

A new, bounded, append-only table, `sequence_events` (`session_id`,
`action_type`, `tag`, `at`, `audit_id`), records one row per EXECUTED action
whose policy opts into tagging it:

```yaml
policies:
  - action_type: web.fetch
    tier: 0
    sequence:
      tag_as: untrusted_content     # a read of content this caller does not control

  - action_type: email.read
    tier: 0
    sequence:
      tag_as: untrusted_content

  - action_type: messages.send
    tier: 2
    sequence:
      rules:
        - after_tag: untrusted_content
          within_seconds: 3600
          effect: hold

  - action_type: payments.*
    tier: 2
    sequence:
      rules:
        - after_tag: untrusted_content
          within_seconds: 3600
          effect: hold
        - count_over:
            action_type: payments.refund
            amount_param: amount_eur
            threshold_eur: 500
            max_count: 1
            within_seconds: 86400
          effect: deny
```

`count_over` without `max_count` is not meaningful on its own — **`max_count`
is required** wherever `count_over` appears (a `count_over` block missing it
fails to load, the same fail-at-load-time discipline every other required
sub-field in this codebase already has). It names how many prior matching
actions within the window are tolerated before this one is stopped — the
example above, `max_count: 1`, tolerates one prior refund over the
threshold and stops the second. **The call being decided right now counts
toward its own threshold check but is never itself in `sequence_events`
yet** (a row is written only once the action settles, after this decision):
a `count_over` rule compares the window's own past rows against
`max_count`, and this call is the one that is held or denied when that
count is already at or past it — it does not retroactively count itself
among the past rows it is being compared to.

**Bound**: at most `EngineConfig.sequence_max_events_per_session` (default
500) rows per `session_id`; the oldest is dropped first once the bound is
reached, regardless of a rule's own `within_seconds` — storage is bounded
independently of what any one rule asks for. A rule whose own window
reaches further back than the bound still holds can keep can honestly only
answer for what the bound still holds, and the receipt below says exactly
how much it consulted, never more.

**Eviction must not fail open.** A session's own oldest *retained* row has a
timestamp, `evicted_through` — the time up to which this session's history
has definitely been pruned, kept in its own row only once something has
actually been evicted for that session; before that, the session has no
`evicted_through` row at all, and no rule's own window can reach past
history that was never trimmed, so its first windowed call is decided on
its own (empty) history, not stopped as incomplete. When a rule's own
`within_seconds` window
reaches further back than `evicted_through`, the rule cannot honestly answer
for the whole window it was asked about — rather than silently evaluating
against only the partial history it still holds and reporting it as
conclusive, the rule applies its own configured `effect` (`hold` or `deny`,
whichever the rule itself names) and the receipt records
`sequence_history_incomplete: true`. This is the fail-closed reading: an
incomplete window can hide a match this rule would otherwise have caught,
so the honest answer when the window cannot be fully read is the rule's own
stop, never a silent pass. `evicted_through` is kept per session, updated
every time this session's own oldest row is dropped for the per-session
bound above.

**The table grows across sessions too, not only within one.** Across every
session, rows older than the longest `within_seconds` any currently loaded
policy's `sequence` block uses may be pruned — no loaded rule can ever
legitimately need to look further back than that, so a row past it is dead
weight regardless of which session it belongs to. This is a second,
independent prune from the per-session bound above: the per-session bound
caps one session's own footprint; this one caps the table's total size
against a fleet of sessions that individually never hit their own per-
session bound. Both prunes apply the same `evicted_through` bookkeeping, per
session, so a cross-session prune is indistinguishable from a per-session
one to any rule reading it.

**With only `tag_as`-style policies loaded (tagging only, no rule), this
still prunes.** No loaded rule's own `within_seconds`
then exists to key the cross-session cutoff to — corrected from an earlier
reading of this section, which took that case for "no rule means nothing
could be looking at history, so nothing to prune," and skipped the
cross-session pass entirely, growing unbounded. It instead falls back to a
fixed default (`sequence.DEFAULT_PRUNE_SECONDS`, 30 days): bounded either
way, never left unbounded just because nothing is currently checking
history. `sequence_evicted` is pruned on the same pass, by the same
cutoff: a marker older than it cannot affect any currently-loaded rule's
own `history_incomplete` check either, the same reasoning that bounds the
events table, so it was dead weight the same way, kept forever until this
fix.

**A call with no session, where the policy has rules, must not pass
silently.** `session_id` is caller-supplied (or gateway-assigned), never
required by the engine itself before this feature — so a policy declaring
`sequence.rules` and a caller that simply omits `session_id` would otherwise
have nothing to check against, and silently decide as if no rule existed.
That is exactly the case these rules exist for, so it is held instead, not
passed: a request with no `session_id` against a policy whose own `rules`
is non-empty is held with its own reason code, unless the policy declares
`sequence: {session_optional: true}` for a caller that genuinely has no
session concept. A policy carrying only `tag_as` (no `rules`) is unaffected
either way — there is nothing to evaluate a session against.

```yaml
policies:
  - action_type: payments.anonymous_tip
    tier: 2
    sequence:
      session_optional: true    # this caller genuinely has no session concept
      rules:
        - count_over: {...}
```

### API

`EngineConfig.sequence_max_events_per_session: int = 500`. No change to
`decide_and_reserve`'s own signature; it already takes `session_id`
implicitly through the request. `SequencePolicy.session_optional: bool =
False`.

### Receipt members

`sequence_events_considered: int`, `sequence_rule_matched: str | None`,
`sequence_history_incomplete: bool`.

### Reason code

`CheckId.SEQUENCE_RULE`; `CheckId.SEQUENCE_NO_SESSION` for a policy whose
own `rules` is non-empty, presented with no `session_id`, and no
`session_optional: true`.

### Fail closed

A `session_id`-keyed read that cannot be served honestly (the store is
unreachable, a row is unreadable) denies the action outright — a sequence
rule is never evaluated against an assumed-empty history; an engine that
cannot read its own state does not get to decide as if the state were
clean. The same reading applies to an incomplete window from eviction,
above: the rule's own configured effect fires rather than a silent pass.

### State

See "Bound" and "Eviction must not fail open," above: a per-session cap
(default 500 events), a per-session `evicted_through` marker (itself
pruned once stale), and a cross-session prune keyed to the longest
`within_seconds` any loaded policy uses, falling back to a fixed default
when none is loaded at all.

### Through the gateway

`_meta["onedoor/session_id"]`, caller-supplied (an MCP host's own
conversation id, most naturally) — absent means no sequence tracking for
that call, the same opt-in default as every other feature here. **The
gateway can also give a session without relying on the caller supplying
one**: a mapping-file setting, `session: per_connection`, makes each stdio
connection its own session (the connection's own lifetime is the session's
lifetime) and each distinct HTTP bearer token identifies one session (the
token the caller authenticates with over the HTTP transport's own
`Authorization` header) — so a session need not depend on a `_meta` value an
MCP host's own implementation may not send. The default stays `none`: no
gateway-assigned session unless a mapping file explicitly asks for
`per_connection`, the same opt-in default as every other setting here.

### Non-claims

A tag applies only to an action that actually executed *through onedoor*;
an action taken outside its view, however related, never appears in this
history.

**A caller choosing its own fresh session id escapes `after_tag`.**
A session with no prior history satisfies no `after_tag`
rule, whatever it actually did under a different id a moment before — the
rule reads this session's own settled rows, nothing a caller did not
present a session id for. The gateway's own `session: per_connection`
(above) is the documented mitigation, assigning its own session id per
connection rather than trusting whatever the caller claims; the library
and the HTTP service have no such mitigation of their own, since neither
owns a connection to key one to — a caller of either that wants
`after_tag` to actually hold across calls has to present the same
`session_id` honestly itself.

### Tests

a tag-then-hold sequence fires within its window and not after it expires;
a count-over-threshold rule fires on the right call, not the ones before
it, and `max_count` is honoured exactly (one over tolerates exactly that
many); a `count_over` block with no `max_count` fails to load; writing past
the per-session event bound evicts the oldest row and advances
`evicted_through`, confirmed by direct inspection of the store, not
inferred from behaviour; a rule whose window reaches past `evicted_through`
applies its own effect and the receipt shows
`sequence_history_incomplete: true`, rather than evaluating as if the
missing history matched nothing; a row older than every loaded policy's
longest `within_seconds` is pruned across sessions, not only within one; a
store read failure denies rather than proceeding as if no history existed;
`session: per_connection` in the mapping file gives each stdio connection
its own session and each distinct bearer token its own session, with no
`_meta` value sent; a policy whose own `rules` is non-empty, presented with
no `session_id`, is held with `CheckId.SEQUENCE_NO_SESSION`, through the
library, the service and the gateway; the same call with `session_optional:
true` decides normally instead; a policy naming no `sequence` block decides
identically to its 0.10.x self.

## Approving a plan once

A person approves a bounded plan; calls inside it go through without asking
again; a call outside it goes back for approval exactly as if no plan
existed.

### What a plan holds

Exact action names (each with its own `amount_param`/`recipient_param`
naming which of that action's own params to read an amount and a recipient
from), a count ceiling, an amount ceiling, a recipient set, an absolute
expiry — never an open-ended authorization. A new table, `plans`
(`plan_id`, `approver`, `action_specs` (a JSON map, action name to its own
`amount_param`/`recipient_param`), `count_ceiling`, `amount_ceiling`,
`recipients`, `expires_at`, `consumed_count`, `consumed_amount`).

### How a call is matched

A call matches an existing plan when: its own action type is in the plan's
`action_names`; its own amount parameter (where that action name's own
`amount_param` names one), added to the plan's own `consumed_amount`, does
not exceed `amount_ceiling`; its own `consumed_count + 1` does not exceed
`count_ceiling`; its own recipient (where that action name's own
`recipient_param` names one) is in `recipients`; and `now` is before
`expires_at`. A call for an action name the plan declares with its own
`amount_param`/`recipient_param`, but which the call itself does not carry
that param on, does not match — a plan that promises to bound an amount or a
recipient cannot honestly match a call it cannot read either from. Anything
that does not match — wrong action name, over either ceiling, an unlisted
recipient, a missing declared param, an expired plan — is evaluated with no
plan at all, falling back to whatever tier the policy already declares,
exactly as if `plan_ref` had never been sent. A match increments
`consumed_count`/`consumed_amount` atomically — the same compare-and-swap
discipline `approvals.cas_approve` already uses, so two calls racing a
near-exhausted ceiling can never both spend past it.

**A plan replaces exactly one thing — the approval step — and nothing
else.** Every other check this engine already makes still applies to every
call inside a plan precisely as it would outside one: bounds, caps,
budgets, the kill switch, untrusted-input checks, sequence rules, bound
permits, and `irreversible_requires` are not plan-aware and do not become
lenient because a call matched a plan. A plan answers only "does a person
need to be asked again right now," never "is this call otherwise allowed."

### Policy syntax

```yaml
policies:
  - action_type: payments.refund
    tier: 3
    bounds:
      numeric: {amount_eur: {min: 0.01, max: 500}}
      required: [payee, amount_eur]
```

A plan is created against one or more existing action types with no new
field on the policy itself — the plan's own ceilings are the only new
bounds, held on the plan row, not on the policy. The plan itself names,
per action name, which of that action's own params are its amount and its
recipient:

```python
plans.propose(
    conn,
    approver,
    action_specs={
        "payments.refund": {"amount_param": "amount_eur", "recipient_param": "payee"},
    },
    count_ceiling=5,
    amount_ceiling=Decimal("2000"),
    recipients={"acme"},
    expires_at=...,
    now=...,
)
```

### Who makes a plan

A plan is **proposed**, by an agent or an operator, and only becomes active
once **approved**, through the same approval machinery every other
threshold-gated action already uses — `plans.propose` creates a proposal
row, never an active plan, and an active plan exists only after that
proposal is approved. A plan whose own ceilings reach above the two-person
threshold (above) requires two different approvers on the proposal itself,
exactly as any other action above that threshold would — a plan is not a
side door around the rule that governs what it would otherwise take to
authorize the same ceiling one call at a time.

### API

`ActionRequest.plan_ref: int | None` — presented by the caller, the same
reference semantics `approval_ref` already has: a bad, expired or exhausted
reference evaluates as if absent, never as an error (the same anti-probing
reasoning `approval_ref`'s own docstring already gives: an error path would
tell a prober whether the id existed). `plans.propose`/`plans.approve`/
`plans.deny` are proposed and approved through the library only
(this corrects an earlier claim of "a new library/service
call"): no HTTP route, gateway path, or Studio action exists for any of
the three. A caller presenting `plan_ref` through the service or the
gateway can still have that reference RESOLVED against an already-active
plan, which is the one piece of this feature those two expose; creating,
approving or denying a plan is itself a human-or-operator act available
only to a direct library caller, and not yet an active plan until
approved:

```python
plans.propose(
    conn, approver, action_specs, count_ceiling, amount_ceiling, recipients, expires_at, now
)
```

### Receipt members

`plan_ref: int | None`, `plan_consumed_count_after: int | None`,
`plan_consumed_amount_after: Decimal | None`.

### Reason code

`CheckId.PLAN_REF`.

### Fail closed

An invalid, expired, exhausted or mismatched `plan_ref` is absent, never an
error — the action re-evaluates on its own merits and proposes again at
Tier 3, same as a bad `approval_ref` already does.

### State

Bounded by the plan's own ceilings and expiry; no separate storage bound —
a plan is one row, not a growing log.

### Through the gateway

`_meta["onedoor/plan_ref"]`, the same shape `onedoor/approval_ref` already
has.

### Non-claims

A plan covers exactly what it names — an amount one cent over its ceiling,
or a recipient not on its list, goes back to ordinary approval, never
silently stretched to fit what the plan's own author probably meant.

**A plan is bound to no principal or session.** Any
caller presenting its id, through the library, the HTTP service, or the
MCP gateway, can spend it — `plan_ref` names which plan, nothing more; it does not name
which caller is allowed to present it. A deployment that wants to
restrict which callers may draw on a given plan has to arrange that
itself, outside this feature (gating who can learn or forward a
`plan_ref` in the first place), the same way `approval_ref` already
leaves that to its own caller.

**A failed call still spends a plan's count and amount.**
`apply_match` runs inside the same transaction as the decision
itself, before any connector is ever called — "a plan is spent only by a
call that actually executes" means decided to execute, not that the
connector call that followed succeeded. A dry run still matches (and
reports what it would have spent) but never calls `apply_match` itself,
the same "rehearsal must not spend a real budget" reasoning this step
already applies to caps, so it never actually spends anything; a
permitted call that goes on to fail at the connector already spent its
room, the ceiling having done its job the moment the call was authorized
to be attempted. Intentional, not a defect this round changes — a plan's
own ceiling bounds how many times, and for how much, a human let this
run, not how many of those attempts a downstream system happened to
carry out.

### Tests

a call inside a plan's own ceilings is permitted with no fresh prompt; one
over either ceiling, with an unlisted recipient, with a declared
`amount_param`/`recipient_param` the call does not carry, or after expiry
falls back to ordinary Tier-3 approval; two calls racing a near-exhausted
ceiling never both succeed (a concurrency test against the compare-and-swap
path); a call inside a plan's own ceilings is still denied by a bound, a
cap, an exhausted budget, the kill switch, an untrusted-input check, a
sequence rule, a missing bound permit, or `irreversible_requires`, each
checked in its own test — a plan answers only the approval question, never
any of these; `plans.propose` creates a proposal, not an active plan, until
it is itself approved; a plan whose ceilings cross the two-person threshold
requires two different approvers on its own proposal; a policy with no plan
ever presented against it decides identically to its 0.10.x self.

## Two-person rule and escalation

Above a threshold, two different approvers; the requester can never approve
their own action; an unanswered approval escalates to a backup approver,
then is denied, recorded as expired.

### What `approvals.sweep` already does

Checked first, since this is the foundation escalation builds on: an approval past its own TTL
already resolves to denied, recorded as expired, and a caller's retry
against it already evaluates as absent (the same `approval_ref`-absent path
named above). This holds already; nothing here changes it. Escalation is a
new step inserted *before* that existing expiry, not a replacement for it.

### Two-person rule

`approvals` gains `approvers: list[str]` in place of a single approver
identity. A policy above its own threshold requires two *different*
recorded identities before the state flips to approved — the same
identity approving twice does not count twice, and the proposer's own
identity is excluded from ever counting as an approver, extending the
single-approver self-approval refusal `cas_approve` already enforces today
to a second approver as well.

### Escalation

```yaml
policies:
  - action_type: payments.wire
    tier: 3
    approval:
      two_person_above_eur: 1000
      escalate_after_seconds: 1800
```

At `escalate_after_seconds` (shorter than the approval's own full TTL), the
approval's own `backup_approver` column is set to whatever
`EngineConfig.escalation_resolver(action_type)` returns — a deployment-
supplied callable, the same shape `mandate_resolver` already is: onedoor
supplies the ordering, the deployment supplies who a backup approver
actually is. The backup approver may then approve or deny the same as any
other approver. **A backup approver set by escalation counts as one
approver, never two** — it occupies the same `approvers: list[str]` slot
any other approver would, so a two-person action still needs a second,
different identity beyond it; and it is excluded from counting at all when
it is the proposer's own identity, the same self-approval refusal every
other approver identity already gets. If nobody — original or backup —
approves before the full TTL, the existing expiry behaviour above applies
unchanged: denied, recorded as expired.

### API

`EngineConfig.escalation_resolver: Callable[[str], str | None] | None =
None` — `None` (the default) means escalation never fires, whatever a
policy's own `escalate_after_seconds` says, the same "a mechanism configured
by its own hook, absent by default" shape `mandate_resolver` and
`permit_issuer` already use.

### Receipt members

`approvers: list[str]`, `escalated_to: str | None`, `escalated_at: datetime
| None`.

### Reason code

None new — the terminal decision (approved, or expired-and-denied) already
has its own existing code; escalation changes the path to it, not the
verdict's own vocabulary.

### Fail closed

No `escalation_resolver` configured, or it returns `None`: escalation simply
never fires, falling straight through to the existing full-TTL expiry —
never an error, never a block.

### State

Rides the existing `approvals` table; two new columns and one new list
field, not a new unbounded structure.

### Through the gateway

Unaffected: a human still approves "outside the agent's channel," through
the same `_meta["onedoor/approval_ref"]` retry mechanism the gateway
already has, whichever approver — original or backup — acts.

### Non-claims

"Two different approvers" means two different *recorded* identities;
onedoor cannot verify two humans did not share one login to produce them.

### Tests

one approver alone does not release an action above the two-person
threshold; a second, different approver does; the same identity approving
twice does not count as two; a requester attempting to approve their own
action is refused, as already true today, confirmed still true with the
second approver slot added; escalation sets a backup approver after its own
window and that approver can release the action, but alone still does not
release a two-person action without a second, different approver beyond it;
a backup approver who is also the proposer is excluded, the same as any
other approver; with no resolver configured, an approval still
expires-and-denies exactly as before this feature existed; a policy with no
`approval` block decides identically to
its 0.10.x self.

## Signed approval links

A single-use, expiring, signed approve/deny link for email or a webhook,
recorded against the approver. No Teams or Slack adapter; no message sent
anywhere real by anything in this codebase or its tests.

### The link

A compact, signed token carrying the approval id, **the action it performs
(approve or deny — baked into the token itself, never a URL parameter)**,
**the identity of the approver it was issued to**, an absolute expiry no
longer than the approval's own TTL, **the id of the signing key that signed
it**, and a random single-use nonce. An approve link and a deny link for the
same approval are therefore two distinct tokens, never one token plus a
query parameter choosing between them — a forwarded or logged URL cannot
silently have its action changed by whoever reads it, because there is no
URL-level action to change.

**The token names its own approver.** It carries the recipient identity the
link was sent to (the `approval_notify.recipient` the policy names, below),
and that is the identity it counts as for the two-person rule when this
approval needs two.

**This does not rest on the same self-approval
exclusion every other approver identity has.** `cas_approve`'s self-approval
check compares `approvals.proposed_by` (a decide key's fingerprint) against
the approver identity just presented; a link's approver identity is always
`approval_notify.recipient` (an email address or a webhook URL) — a value
from a different identity space that can never equal a decide key's
fingerprint as a string. The check as written can *never fire* for a link
vote, for any policy, not merely "does not fire in this deployment's
configuration" — there is no proposer identity a link's own recipient could
ever be read back as. What actually keeps a proposer from voting its own
action by link is channel separation, not identity: `approval_notify.recipient`
is an operator-set policy field, not something the holder of a decide key
chooses or can read off its own key — a proposer who cannot read that
channel cannot present a link for it at all. A deployment that configures a
link's recipient to be the proposer's own inbox (or hands the proposer that
channel by some other means) is not caught here; nothing in this engine
checks that the two are different, because nothing here *can* compare them.
Stated plainly as what the code actually does, replacing an earlier,
incorrect claim here that two links could count as two approvers: a
policy names exactly one `approval_notify.recipient`, so every link this
policy ever issues carries that SAME identity. Two link presentations
under one policy are the same approver voting twice, caught by the
ordinary same-identity check before the channel even matters — a link
vote is one recipient, one vote, never two. A two-person approval with
links turned on completes only once a second, different identity votes
through a different channel. Every channel this engine tracks is its
own identity space; two votes through two DIFFERENT tracked channels are
refused outright, never counted as two people, regardless of which two
channels they are:

| First vote | Second vote | Completes a two-person approval? |
|---|---|---|
| key | key, different identity | Yes |
| key | link | No -- mixed channel |
| key | library | No -- mixed channel |
| link | link, same policy | No -- same recipient identity, not two votes |
| link | library | No -- mixed channel |
| library | library, different identity | Yes |

A vote recorded before this channel tracking existed carries no channel
at all and is not "known" to this check either way -- it pairs freely
with anything, the same as it always has.

**Signed with its own key, apart from the permit key.** A separate signing
key (never `onedoor.guardrail.signing`'s own permit key — a different
artifact, verified by a different relying party, with a different rotation
schedule) under `NotifyConfig.approval_link_signing_keys: dict[str, bytes]`
(key id to key material) and `NotifyConfig.approval_link_signing_key_id:
str` (which key in that set signs a new link). The token itself carries
the signing key's id, so an old link signed under a since-rotated key still
verifies as long as that key id remains in the accepted set — rotation adds
a new key id and, once every outstanding link under an old one has expired,
retires it from the set.

Presenting the link is possession-based, the same security model an email
password-reset link already has: **what the approver must prove is
possession of the link**, delivered only to the intended recipient's own
inbox or webhook endpoint — not a separate proof of identity beyond that,
stated here as a non-claim rather than implied.

### Single use

The nonce is recorded, on first successful use, in a new
`approval_link_uses` table. A repeat use of the same nonce is refused,
evaluated as absent — the same anti-probing posture as every other
reference in this design: it does not say *why* it failed beyond that.

### A GET must never approve or deny

Mail scanners, link-preview generators and security gateways fetch a link
appearing in an email or a chat message by themselves, automatically,
before any person sees it — a `GET` that itself approved or denied would be
silently actioned by one of these, never by the named approver. `GET
/v1/approvals/by-link/{token}` therefore only ever shows a confirmation
page naming the action the token performs and the approval it is for;
**only a `POST` from that confirmation page acts.** A test asserts directly
that issuing the `GET` alone leaves the approval's own state completely
unchanged — not inferred from the route's implementation, checked against
the store.

### Policy syntax

```yaml
policies:
  - action_type: payments.wire
    tier: 3
    approval_notify:
      channel: email            # or: webhook
      recipient: approver@example.test   # or a webhook URL, for channel: webhook
```

Absent `approval_notify`: no link is ever built or sent for that action
type's approvals — they still propose and wait exactly as today, reachable
by Studio or a direct API call, the same as every account that predates this
feature.

### Reason code

None new on the decision itself — the approval mechanics an approve/deny
link resolves against are the engine's own existing ones; the link is a
delivery and single-use mechanism layered on top, not a new decision path.
A link's own verdict (valid, expired, already used, malformed) is its own
small, separate vocabulary, not a `CheckId`.

### API

A new, deliberately unauthenticated-by-design service route (the token
itself is the credential): `GET /v1/approvals/by-link/{token}` (shows the
confirmation page only) and `POST /v1/approvals/by-link/{token}` (acts —
approves or denies, whichever the token itself names). A new adapter
module, `onedoor.integrations.approval_notify`, given an approval id and a
policy-configured recipient, builds the approve link and the deny link (two
separate tokens, signed under the currently-configured signing key id) and
calls a deployment-supplied `send_email(to, subject, body)` or
`send_webhook(url, payload)` — the same "deployment supplies the mechanism"
shape as `mandate_resolver` and `escalation_resolver`, configured on a new
`NotifyConfig` (`approval_link_base_url`, `approval_link_signing_keys`,
`approval_link_signing_key_id`). Tested against stand-in senders only;
nothing here ever opens a real socket to a mail server or a webhook host.

### Receipt members

`approval_link_sent: bool`, `approval_link_channel: "email" | "webhook" |
None`, `approval_link_used_at: datetime | None`.

### Fail closed

A malformed, expired, or already-used link verifies as refused, never as
valid, and never with a stack trace. A notify callable that itself fails
(the send errors) does not touch the underlying approval's own state — the
Tier-3 hold stands exactly as it would have if no link had ever been sent,
reachable by any other means (Studio, a direct API call); a failed
notification is logged, never mistaken for a denied or approved action.

### State

The `approval_link_uses` table keeps a nonce **until its own token's
expiry, then prunes it.** A reused nonce must be detectable only for as
long as its token could still verify at all — once a token is past its own
`exp`, presenting it is refused on expiry before the nonce table is ever
consulted, so keeping that nonce any longer detects nothing a live check
would not already catch from the signature alone. This settles the
tension between "never pruned" (unbounded growth, the audit-log instinct)
and "not meaningfully longer than necessary" (the actual bound the
signature already provides): the signature covers the expiry, so pruning at
expiry loses no real protection.

### Through the gateway

Unaffected — links are a notification convenience over the same underlying
approval row the gateway's existing `_meta["onedoor/approval_ref"]` retry
already uses.

### Non-claims

Possession of the link is the proof; a compromised inbox or endpoint can
approve. This does not identify a person beyond "reached where the
recipient was told to deliver it." **Two different links, if both are
presented by one real person who happens to hold both, still count as two
approvers** — this mechanism verifies that two links sent to two named
identities were each presented, not that two different humans did the
presenting.

### Tests

a valid link approves exactly once; a second presentation of the same link
is refused; an expired link is refused, and its nonce is no longer
consulted once pruned past that expiry; a malformed token is refused, never
raising; a `GET` on a valid, unused link leaves the approval's own state in
the store completely unchanged, checked directly, and shows a confirmation
page naming the action and the approval; only the following `POST` acts; an
approve token and a deny token for the same approval are two different
tokens, neither accepted in place of the other; the identity a link was
sent to is the identity recorded as having approved, confirmed against the
store; a link sent to a recipient the proposer's own decide key cannot read
(channel separation, not identity -- see the correction above) does not
reach the proposer in the first place, so it cannot be presented to vote on
its own action; a token signed under a since-rotated key id still
verifies as long as that key id remains in the accepted set, and stops
verifying once retired; the email adapter calls its own stand-in sender
with the right link and never constructs a real network socket (asserted
directly, not inferred); the webhook adapter, the same shape; a send
failure leaves the underlying approval reachable by other means, confirmed
by then approving it through the ordinary API; a policy configuring no
notify adapter decides identically to its 0.10.x self.

## Shadow mode and policy tests

A candidate policy evaluated beside the live one, on live traffic, its
differences logged, nothing it decides ever enforced.

### Where the differences are logged

`EngineConfig.shadow_policy_path: Path | None = None`. When set, every
`decide_and_reserve` call also evaluates the same request against the
shadow policy's own table, loaded once as a read-only snapshot — the shadow
evaluation takes no reservation, creates no approval row, touches no
budget, whatever it would have decided; it may only *read* the live store's
current budget/kill-switch/approval state to compute what it would have
done, never write to it. **The state the shadow reads is the state as it
stood before the live decision's own writes** — both evaluations run inside
the one transaction `decide_and_reserve` already opens, with the shadow
read happening first, before the live path reserves a budget, creates an
approval row, or consumes anything: the shadow's own verdict is never
computed against state its own sibling call just changed. For the same
reason, **a shadow evaluation never consumes a plan or an approval link** —
consuming either is itself a write (a plan's `consumed_count`/
`consumed_amount`, a link's single-use nonce), and the shadow path has no
access to the write side at all (below); a shadow policy that would have
matched an active plan or an unused link is scored as having seen it,
without ever spending it. A new table, `shadow_differences` (`audit_id`,
`live_decision`, `shadow_decision`, `shadow_reason_code`, `at`), is written
only when the two decisions differ — not on every call, which would grow
without bound against a shadow policy that mostly agrees with the live one.
**Bound**: the newest `EngineConfig.shadow_differences_max_rows` (default
5,000) rows are kept; the oldest is dropped first past that, the same
storage discipline as the sequence-state table above.

### How a shadow policy can never enforce

By construction, not by convention: the function that evaluates a shadow
policy has no access to the store's write path at all — it is given a
read-only connection, so there is no call it could make that reserves a
budget, creates an approval, or releases a kill switch, whatever the shadow
policy itself says. The live decision proceeds exactly as if shadow mode
were off.

### `onedoor policy test`

A new top-level command (onedoor ships no single top-level command today;
this is new entry-point infrastructure, declared as `onedoor =
"onedoor.__main__:main"`). **Cases live in a file of their own,
`<policy>.cases.yaml`, never inside the policy file** — a case edited
alongside the policy's own rules would change the ratified policy's own
digest (the bytes a ratification seals), and the live loader reading that
ratified file would then meet an unknown top-level key it was never asked
to tolerate. Keeping cases in a separate, sibling file means ratifying a
policy and adding or editing its test cases are two unrelated acts, exactly
as they should be:

```yaml
# policies.yaml -- ratified, unchanged by anything below
policies:
  - action_type: payments.transfer
    tier: 2
    bounds: {numeric: {amount_eur: {min: 0.01, max: 500}}}
```

```yaml
# policies.cases.yaml -- never ratified, edited freely
cases:
  - action_type: payments.transfer
    params: {payee: acme, amount_eur: 10}
    expect: permitted
  - action_type: payments.transfer
    params: {payee: acme, amount_eur: 9000}
    expect: denied
  # a case can also be a sequence: several calls, in order, against one
  # store -- the only way to exercise a sequence rule or a
  # plan from `policy test` at all, since either needs more than
  # one call's own history to mean anything.
  - name: a second refund over the threshold is stopped
    steps:
      - action_type: payments.refund
        params: {payee: acme, amount_eur: 400}
        expect: permitted
      - action_type: payments.refund
        params: {payee: acme, amount_eur: 400}
        expect: denied
```

`onedoor policy test FILE` loads `FILE` as the policy and
`FILE`-with-`.cases.yaml` in place of its own extension as its cases, into a
throwaway, in-memory store. A plain `cases:` entry evaluates with a fresh
budget state per case (a case tests the policy's own shape, not a sequence
of them); a `steps:` entry runs its calls in order against one shared store,
so each later step sees the earlier ones' own effects — exactly what a
sequence rule or a plan needs to be tested at all. Reports pass or fail per
case (or per `steps:` block); a failing case or step names itself and its
expectation. Non-zero exit on any failure, runnable as a CI gate the same
way the rest of this project's own suite already is. Built on the same
read-only evaluation path shadow mode uses — `onedoor.guardrail.policy_test.
run_cases(path) -> list[CaseResult]` — rather than a second implementation
of "evaluate a policy without touching the store."

### API

`EngineConfig.shadow_policy_path: Path | None = None`,
`EngineConfig.shadow_differences_max_rows: int = 5000`.

### Receipt members

None on the live decision's own receipt — shadow mode's own output lives in
`shadow_differences`, a separate, queryable record, not an addition to
every live receipt whether or not a shadow policy is even configured.

### Reason code

None new — a shadow decision carries the engine's own existing reason
codes, exactly as a live one does.

### Fail closed

A shadow policy that itself fails to evaluate (malformed, a missing
required field) is recorded as its own `shadow_error` row, never
interpreted as "the shadow would have denied it," and never touches the
live decision either way.

### Through the gateway

Not a per-call gateway concern — the gateway's own mapping and policy file
can themselves be the subject of `onedoor policy test` before a deployment
changes them, which is the integration point, not a new `_meta` key.

### Non-claims

Shadow mode measures what a candidate policy would decide against the
inputs live traffic actually produced; it does not simulate what would have
happened further downstream had that decision been the live one — an action
the live policy already permitted already executed, and the shadow's own
hypothetical verdict changes nothing about that.

### Tests

a shadow policy that differs from the live one on a given call is logged,
and the live decision is unaffected; confirmed directly against the store
that no reservation, approval or budget change resulted from the shadow
side; a shadow policy that would have matched an active plan or an unused
approval link is scored without the plan's own counters or the link's own
nonce ever being touched, confirmed directly against the store; a shadow
policy identical to the live one logs nothing; writing past
`shadow_differences_max_rows` evicts the oldest row; a case written into the
policy file itself (not its own `.cases.yaml`) is rejected by the ratified
loader as an unknown key, confirming the separation holds; `policy test`
against a fully-passing `.cases.yaml` exits zero; against a file with a
failing case, exits non-zero and names the failing case; a `steps:` case
exercising a sequence rule across two calls, and another exercising a plan
across three, both pass against a correct policy and fail by naming
themselves against a broken one; with no `shadow_policy_path` configured,
behaviour is byte-identical to 0.10.x (the existing parity test
already covers this, since the default is `None`).

## Undoing an action

Declaring whether an action can be undone, first; running the undo, second.

### Reversibility, declared

A new policy field, distinct from the existing `compensating_command` (which
already exists, and is already required for Tier-1/2 auto-execution
specifically):

```python
reversibility: Literal["reversible", "compensable", "irreversible"] | None = None
```

Absent means not declared — never read as reversible by default, and
behaving exactly as a 0.10.x policy already does. Declaring
`reversibility: compensable` additionally requires `compensating_command`
be set, validated at policy load the same way Tier 1/2 already requires it
— extended, not replaced.

```yaml
policies:
  - action_type: payments.wire
    tier: 3
    reversibility: irreversible
    irreversible_requires:
      bound_permit: true
      approval: always          # or: {above_eur: N}
      deny_if_ambiguous: true   # a required or bounds-checked param missing
                                # or type-ambiguous denies outright, never a
                                # best-effort guess at what was meant
```

**`approval: always | {above_eur: N}`, never a bare `approval_above_eur: 0`**
— a zero-amount call is not "above" zero, so a threshold spelled as an
amount can never honestly mean "every call, including the free ones": that
reading needs its own word, `always`, rather than a number chosen to stand
in for it by accident.

Studio shows the declared value per action; a decision's own receipt
records it from the policy snapshot already captured at decision time
(`reversibility: str | None`); backtest can later report by it (a later
item, not this one — the field exists now so that reading does not need a
second migration). onetrace's own `effect="write"` label is a related but
separate vocabulary — a write-effect action with no `reversibility`
declared is a fact for a policy review to notice, not something this engine
infers or auto-denies on its own initiative.

### Compensation

Triggered three ways: a person rejects an outcome after the fact
(`undo.reject_outcome(conn, intent_audit_id, person, reason, now)`); a step
of an approved plan (see "Approving a plan once," above) fails and the
plan's own policy asks for compensation on failure (below); or a person
undoes an undo (below, "Who may reject an outcome"). Every way, onedoor
looks up the original action's own `compensating_command`, builds a new
`ActionRequest` with `action_type=compensating_command` and
`parent_audit_id` set to the original's own audit id (already an existing
field — no new one needed here), and runs it through the ordinary
`decide_and_reserve`/`report_result` pipeline: **the compensating action is
itself decided and recorded like any other action** — its own tier, its own
bounds, its own approval if its own policy asks for one, its own kill-switch
exposure. It is not an unconditional bypass of anything.

**Receipts are never updated in place.** An earlier reading of
`compensation_status` as a field updated on the original action's own
receipt would change a record that has already been written — exactly what
this project's own audit discipline exists to refuse everywhere else. A
compensation is instead its own new record, linked to the original by
`compensation_of: int` (the original's own audit id). The original's own
status is read by **following these links** — the newest compensation
record linked to a given original is that original's own current
compensation status, computed by the reader, never stored back onto a
record that already exists.

### A failed plan step's compensation

A plan carries `compensate_on_failure: true | false` (default `false`, the
opt-in default every other field here has). When `true` and a step inside
an approved plan is held, denied, or itself fails, the plan's own
already-carried-out steps are compensated **newest first** — reversing in
the order they were done, not the order they were declared — **each
decided entirely on its own**, exactly as any other compensation is.
Compensating one step can itself be held, denied, or fail; when it is, the
run **stops at that first non-carried-out compensation**, and the plan's
own record says exactly where it stopped (which step, and why) — it does
not skip past a stuck step to keep compensating the ones behind it, which
would leave a gap in the record no reader could later reconstruct.

### When the compensating action itself fails

Recorded, never auto-retried: a new compensation record (above) with its
own `compensation_status: "pending" | "succeeded" | "failed"`, written once
the compensating action's own `report_result` lands — never an update to
any earlier record. A failed compensation is left for a person to resolve
(Studio surfaces it); an automatic retry of a side-effecting compensating
action is its own hazard, and this design does not take it on.

### Who may reject an outcome

Rejecting an outcome (the first trigger above) is a **Studio role**,
distinct from an ordinary operator login — recorded on the compensation
record itself as the identity that rejected it, the same way an approver's
identity is recorded on an approval. **An undo of an undo is allowed only
by a person, acting again through this same role, never chained
automatically** — a compensation record is itself just another action with
its own outcome, and nothing in this design lets a compensation's own
rejection trigger a further compensation without a person separately
deciding to reject that one too.

### API

`Policy.reversibility`, `Policy.irreversible_requires` (a small typed
block: `bound_permit: bool`, `approval: Literal["always"] |
{"above_eur": Decimal} | None`, `deny_if_ambiguous: bool`),
`Plan.compensate_on_failure: bool = False`.
`onedoor.guardrail.undo.reject_outcome(conn, intent_audit_id, person, reason,
now)` where `person` is a Studio-role identity.

### Receipt members

`reversibility: str | None` on every action's own receipt.
`compensation_of: int | None` (the original's own audit id) and
`compensation_status: "pending" | "succeeded" | "failed"` on a
**compensation record** — its own new row, never written onto the original
action's receipt (see "Receipts are never updated in place," above).

### Reason code

`CheckId.NO_COMPENSATION_REGISTERED` — a genuinely new failure mode: an
action declared `compensable` whose `compensating_command` is no longer
configured by the time an undo is attempted (configuration can drift
between the original decision and a later undo) refuses the undo outright,
rather than guessing at a reversal nobody registered.

### Fail closed

`irreversible_requires.deny_if_ambiguous` denies on any required or
bounds-checked parameter the action is missing or that arrives
**type-ambiguous — defined, not left as a judgment call: a param is
type-ambiguous when it fails the strict parse its own bounds declare (a
numeric bound given a value that cannot parse as that number without
guessing a locale or a format), or when it arrives under two spellings the
mapping file folds together (the gateway's own mapping maps two distinct
argument paths onto one onedoor param name, and both are present on the
same call with different values — which one is "the" value is exactly the
ambiguity this flag exists to refuse rather than silently pick one)** —
rather than proceeding on a best-effort reading of what was probably meant.
A compensating command no longer registered refuses the undo (above). A
compensation that itself fails is recorded as failed, never silently
retried, never reported as if it had succeeded.

### State

A compensation record is its own new row per compensation, linked to the
original (and, for a chain, to its own predecessor) by `compensation_of` —
unbounded the same way the audit trail it extends already is, never pruned;
no separate storage bound beyond what the audit log already has.

### Through the gateway

Undo is an operator or plan-engine act, not an agent-side one — the
proxy's existing refusal of every `onedoor/*` method already covers this if
it is ever exposed over MCP; stated here as a boundary, not a new refusal
this round writes.

### Non-claims

A compensating action asks onedoor's own record, and (if permitted) the
tool it is forwarded to, to reverse what was done — it is not a claim that
the original effect is now provably undone in the world; that is exactly as
true of a compensating action as it already is of the original one, which
onedoor also does not itself verify beyond what it is told.

### Tests

a policy declaring `compensable` with no `compensating_command` fails to
load, extending the existing Tier-1/2 check rather than duplicating it; a
policy declaring `irreversible` with `deny_if_ambiguous` denies a call
missing a required param rather than guessing; the same flag denies a
value that fails its bound's own strict parse, and a value arriving under
two mapping-folded spellings at once; the same declared action requires a
bound permit and `approval: always`, and separately `approval: {above_eur:
N}`, as configured — a zero-amount call under `{above_eur: 0}` is not
treated as always-required, confirming the two forms are genuinely
distinct; an undo triggered by a rejected outcome runs the compensating
action through the ordinary pipeline, with its own tier and bounds, and
writes a **new** compensation record rather than editing the original's own
receipt, confirmed directly against the store; the original's own current
compensation status, read by following `compensation_of` links, reflects
the newest such record; a failed plan step with `compensate_on_failure:
true` compensates its plan's own already-carried-out steps newest first,
each as its own decided action; a compensation in that chain that is itself
held, denied, or fails stops the run there, and the plan's own record names
exactly which step it stopped at; with `compensate_on_failure: false` (the
default), a failed step compensates nothing; a compensating action that
itself fails is recorded failed, as a new record, and not retried
automatically; an undo attempted with no compensating command registered is
refused by name (`NO_COMPENSATION_REGISTERED`); rejecting an outcome
requires the Studio role, refused for an ordinary operator identity, and
the rejecting identity is recorded on the resulting compensation record;
undoing an undo requires a person acting through that same role again, and
is refused if attempted automatically; a policy declaring no
`reversibility` at all decides identically to its 0.10.x self.
