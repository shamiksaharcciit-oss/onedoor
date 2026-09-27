# Design note: `external_authorization` and `present_bound`

**Status: design note only. No code in this file's tree changes wire-observable
behaviour.** Both features add a new reason code / a new obligation type — that is a
wire change onedoor does not make on its own authority (CLAUDE.md's standing
boundary). This note exists so core can rule on the open questions before either
becomes a ticket.

Source: `draft-saha-aadp-03.txt` §8.1 (mandate-layer deferral) and §6 (obligations,
`present_bound`), fetched directly — quoted below rather than paraphrased, so the
citations are checkable against the same text a future reader can fetch.

> §8.1: "A PDP consuming a mandate-layer verdict must not return 'permit' while that
> verdict denies or defers the action." DENY → the PDP returns `deny` with reason
> `external_authorization`. PENDING → the PDP returns `propose` with reason
> `external_authorization`, creating an approval record as for any propose verdict —
> unless another check already denies the action, in which case that denial takes
> precedence. "An approval that waits on a mandate-layer deferral is resolved... by
> the mandate authority's ratification and by nothing else; an approver of the AADP
> deployment cannot resolve it on the mandate authority's behalf." The PDP verifies
> the ratification record in three states: verified and approved, verified and
> disapproved, or could not be dereferenced. Resumption re-evaluates fully, a kill
> switch blocks even if the external authority approves, and the approval is
> single-use.

> §6: `present_bound`'s value is "an absolute URI naming the recipient that will
> perform the action." "This permit MUST NOT be exercised by the PEP acting itself,
> and may be exercised only by presenting the permit... to that audience." A PEP
> that doesn't recognize the obligation type must refuse and report `not_attempted`
> per the fail-closed rule. Discharge evidence: "the recipient's confirmation of the
> presented permit, by digest, or the recipient's refusal reason."

---

## 1. `external_authorization`

### Where it would attach

A new ordered-pipeline step in `onedoor/guardrail/decision.py::decide_and_reserve`,
**after policy lookup (step 2) and before effect resolution (step 2b)** — it needs
the resolved `Policy` to know whether this action type is even governed by a mandate
authority, but its verdict (DENY especially) should pre-empt everything downstream,
the same way the kill switch pre-empts policy arithmetic. Concretely: a new function
`onedoor/guardrail/mandate.py::resolve(conn, policy, request, now) -> MandateResolution`,
called and folded into `evaluation_trace` as its own check
(`"external_authorization"`) — the trace design already generalises to a new check
without touching `Trace` itself.

The PENDING → `propose` path reuses the shape of the existing Tier-3 flow
(`approvals.create`, `PolicyDecision(decision=Decision.PROPOSED, ...)`) but **must
not** reuse the `approvals` table's resolution path unmodified: `/v1/approvals/{id}/
approve` (`onedoor/service/app.py`) calls `approvals.cas_approve`, which any admin
key can invoke. §8.1 requires the opposite — resolvable *only* by the mandate
authority. See Q1.

The DENY path is a terminal `ActionResult` exactly like the existing kill-switch and
bounds denials — same `audit.append(..., kind="decision", reason_code=CheckId.
EXTERNAL_AUTHORIZATION)` shape, new `CheckId` member.

Resumption ("resumption re-evaluates fully") is the same idempotency/replay
discipline `decide_and_reserve` already has via `audit.result_for_request_id` plus a
**new** request-carried reference, analogous to `approval_ref` but distinct from it
(§8.1's "and by nothing else" is the reason it cannot just be `approval_ref` — see
Q1 again).

### New inputs

- `Policy.external_authorization: ExternalAuthorization | None` (new model,
  `onedoor/guardrail/models.py`), naming which mandate authority governs this action
  type — analogous to `cost_param` naming which parameter carries money. Shape TBD
  pending Q2 (a registered connector name vs. an endpoint URI).
- A registry seam analogous to `onedoor/guardrail/registry.py::ConnectorRegistry`:
  `MandateRegistry` mapping an authority name to a callable that returns one of
  `{permit, deny, pending}` plus whatever reference is needed to later verify a
  ratification. The engine must stay agnostic of *how* a mandate authority is
  reached (HTTP, gRPC, in-process stub) — same seam discipline the connector
  registry already enforces for `act_*`.
- `ActionRequest` gains a field to carry the mandate-authority's ratification
  reference on resumption — new, not reusing `approval_ref` (Q1).
- `CheckId.EXTERNAL_AUTHORIZATION` (new wire vocabulary — a genuine addition, not a
  reuse of an existing code the way `ND-040` reused `malformed`).
- Evidence: a `mandate_status` column on `actions_audit`, parallel to
  `approval_ref_status` (`absent | pending | approved | disapproved |
  undereferenceable`), so a denial's forensic trail names *which* of the three
  verification states applied — mirroring why `approval_ref_status`'s seven-value
  vocabulary exists at all (R035 §1).

### Tests that would prove it

- A mandate DENY produces `decision=denied, reason_code=external_authorization`,
  with `evaluation_trace`'s failing entry naming it, and no further check runs
  (mirrors `test_a_short_circuited_pipeline_shows_no_entries_after_it_stopped`).
- A mandate PENDING produces `decision=proposed, reason_code=external_authorization`
  and an approval record, UNLESS bounds/default-deny/etc. would already deny —
  "another check already denies the action... that denial takes precedence" is
  directly testable by constructing a request that is both mandate-pending and
  bounds-invalid, asserting `bounds` wins.
- The onedoor admin `/v1/approvals/{id}/approve` route **refuses** to resolve a
  mandate-pending approval (a negative test — this is the sharpest test in the set,
  since it is the one thing the current `approvals` table cannot express today).
- Verified-approved / verified-disapproved / could-not-be-dereferenced each produce
  a distinct, testable outcome and a distinct evidence value (three outcomes, never
  two — the same discipline this session's own standing rules already name).
- A resumed request re-evaluates fully: change a bound between the original
  proposal and the ratification, and the resumed decision reflects the new bound
  rather than replaying the old verdict.
- The kill switch still denies a mandate-approved action (mirrors the existing
  `approved_override`+`kill` test in `tests/guardrail/test_approval_ref.py`).
- Single-use: two simultaneous resumptions of the same ratification, exactly one
  executes (mirrors `test_approval_ref.py`'s race test for `approval_ref`).

### Questions

- **Q1 (the load-bearing one).** Can a mandate-pending approval share the
  `approvals` table and the existing admin approve/deny routes at all, given
  `/v1/approvals/{id}/approve` today lets *any* admin key resolve *any* pending
  approval? Two shapes seem possible: (a) a new `authority` column on `approvals`
  that, when set, makes `cas_approve`/`deny` refuse (mirroring how
  `ApprovalRefStatus.PRINCIPAL_MISMATCH` is reserved-but-unemitted because onedoor
  has no way to check it yet) — cheap, but leaves the admin route "trusted not to
  misuse" rather than structurally unable to; or (b) a wholly separate table the
  admin routes never touch. `approval_ref.py`'s own history argues for (b): "a
  control that does not control anything" was exactly the finding that reserved
  `principal_mismatch` rather than pretending to enforce it.
- **Q2.** Is the mandate authority a registered in-process callable (like a
  connector), an HTTP endpoint declared in policy, or both? This determines whether
  `MandateRegistry` is a pure Python seam or needs a network client with its own
  timeout/retry policy — and whether "could not be dereferenced" is a transport
  failure onedoor must classify itself or a state the authority hands back
  explicitly.
- **Q3.** Does "could not be dereferenced" settle as a denial, stay pending for a
  later resumption, or need a fourth reported outcome? The quoted text names it as
  one of three *verification* states but the spec text available to this note does
  not say what the PDP does with it — recommend: never grant on it (fail-closed,
  same rule as every other absent/unresolved case in this codebase), but whether it
  denies outright or leaves the approval pending for retry is a real behavioural
  choice, not an implementation detail.
- **Q4.** Relative order against `approval_ref`: can one request carry both a
  mandate ratification reference and an onedoor `approval_ref`? If so, which
  resolves first? This note assumes mandate authorization sits between policy
  lookup and effect resolution, i.e. *after* `approval_ref` (which decision.py
  resolves before policy lookup) — meaning an already-honoured `approval_ref` would
  set `approved_override=True` before external authorization is even consulted,
  which seems backwards for an action a mandate authority is supposed to gate.
  Needs a ruling, not an inference.

---

## 2. `present_bound`

### Where it would attach

Purely declarative once the mandate is decided — no new ordered check, no new
`evaluation_trace` entry. Rides along with the permit exactly the way
`compensating_command` and `undo_until` already do:

- `Policy.present_bound: str | None` (new field, `onedoor/guardrail/models.py`) — the
  audience URI, declared per action type.
- `PermittedIntent` (`onedoor/guardrail/decision.py`) gains `present_bound: str |
  None`, copied from `policy.present_bound` at the point `PermittedIntent` is
  constructed (mirrors `compensating_command=policy.compensating_command` two lines
  above it).
- `DecideReply` (`onedoor/service/app.py`) gains `present_bound: str | None`, set in
  `_decide_reply`'s `PermittedIntent` branch — this is the field an external PEP
  actually reads.
- **onedoor's own packaged PEPs must fail closed on it.** `onedoor/guardrail/
  executor.py` (the in-process executor) and `onedoor/mcp/proxy.py` both act on a
  permit directly today; neither implements audience presentation. Per §6's own
  words — "a PEP that doesn't recognize the type must refuse and report
  `not_attempted`" — both must check `present_bound is not None` before calling a
  connector and report `not_attempted` instead of executing, until onedoor actually
  implements presentation. This is the one place the note recommends a concrete,
  unconditional behaviour rather than raising a question: doing anything else would
  be exactly the "PEP acted despite the obligation" defect §6 exists to prevent.

### New inputs

- `Policy.present_bound: str | None` — validated as an absolute URI. Whether it
  needs the same canonicalization treatment `ND-040` gave `param_effects` URL
  matching (percent-encoding, IDNA, etc.) is Q5 below — a policy-declared value is
  trusted input today (`opaque` classes aside), which is a materially different
  threat model from a request-carried URL.
- `PermittedIntent.present_bound`, `DecideReply.present_bound` (wire exposure).
- Discharge evidence on report: §6 wants "the recipient's confirmation... by digest,
  or the recipient's refusal reason" in the report payload. `report_result`
  (`onedoor/guardrail/decision.py`) already accepts a free-form `payload:
  dict[str, JsonValue] | None` — the note leans toward a **documented payload
  shape** (`payload["present_bound_confirmation_digest"]` /
  `payload["present_bound_refusal"]`) rather than new typed fields on `ReportBody`,
  since onedoor does not verify the confirmation today and inventing typed fields
  for evidence the engine cannot check would overclaim (Q6).

### Tests that would prove it

- A policy declaring `present_bound` produces a `PermittedIntent`/`DecideReply`
  carrying the exact URI, unchanged.
- A policy without it produces `present_bound: null` — regression, unchanged wire
  shape for every existing deployment.
- `executor.py`'s in-process path, given a permit with `present_bound` set, calls no
  connector and reports `outcome=not_attempted` — this is the test that would fail
  today if `present_bound` were wired in without the fail-closed guard, i.e. exactly
  the defect this note flags before it can be built.
- Same test for `mcp/proxy.py`.
- A report against a `present_bound` permit carrying the documented payload shape
  round-trips through the export as ordinary payload JSON — no new
  column needed unless Q6 is ruled the other way.

### Questions

- **Q5.** Does `present_bound`'s URI need canonicalization/validation at policy-load
  time (`policy_loader.py`), the way `ND-040` canonicalizes `param_effects` URL
  rules? A malformed or attacker-shaped audience URI in a *policy* is a deployer
  error today (policies are trusted input), but if a future ticket lets
  `present_bound` be templated from request params, the threat model changes to
  exactly the one `ND-040` was built for.
- **Q6.** Should discharge evidence get typed fields (a `present_bound_evidence`
  column, hashed or dark like `evaluation_trace_json`) or stay inside the free-form
  `payload_json` this note recommends? A typed field is checkable by other tooling
  (the export, a future Studio panel) without knowing the payload convention; an
  untyped one costs nothing today and invents no schema for a feature that is not
  built yet. Leaning untyped until `present_bound` itself is authorized.
- **Q7.** Is `present_bound` exclusive with `approval_ref`/mandate authorization, or
  can a single permit carry both an external-authorization gate *and* a
  present-bound obligation (e.g. a mandate authority approves a payment that must
  then be presented to a specific payment processor)? If both are possible, the
  wire shape and the ordering of obligations needs to be decided once, not per
  ticket.
