# `ND-009` — PEP-driven resumption via `approval_ref` · decomposition

**Ticket:** `ND-009`, `0.4.x`, AADP A6. Runs in parallel with the crypto epic.
**Baseline:** `ae56632`; 492 passed / 9 skipped, four gates green, CI green both jobs.
**GO:** R034 §2.
**Settled surface, built to and not rediscovered** (`CONFORMANCE.md` §3.1/§6, E2, R034):
single-use; an invalid or replayed ref **evaluates as if absent**, never an error path
that leaks whether a ref existed; **the kill switch wins** over any approval; refs are
**principal-scoped**; the binding is **action-equivalence**, not a byte-identical
request; `approval_ref_status` writes the seven-value evidence field.

---

## 1. What exists, and the shape of the gap

`approval_ref` **does not exist in the codebase** — the roadmap's "field exists in the
model" was wrong and `CONFORMANCE.md` §3.1 already records that. What exists is the
*PDP-driven* path: `executor.approve_and_resume` calls `approvals.cas_approve`
(`pending → approved`, atomic, expiry-checked), re-runs the request through the full
pipeline with `approved_override=True`, then `mark_executed`.

So the machinery for "resume an approved request" is built and tested. `ND-009` adds
the other door: a **PEP** presents a ref on a *new* `/v1/decide` with a *new*
`request_id`, and the engine decides whether that ref authorises this action.

**Verified rather than assumed, because R034 §2 flagged it:** the frozen request
survives the approval round trip with `params_raw` and `session_id` intact —
`dumps_request`/`loads_request` preserve both. So a resumed request can carry the
original's **received bytes**, and E10's provenance label survives the approval hop
without special handling. The R2 discipline holds unchanged; this was checked by
round-tripping a request with both fields set.

## 2. Finding one: the evidence field collides with the frozen preimage

`approval_ref_status` is an **evidence field on the decision row** — a new column on
`actions_audit`. `ND-001` froze the row preimage, and `TICKETS-ND-010.md` §4 already
wrote the rule this ticket now meets for the second time: **every column is either in
`FIELD_ORDER`, where adding one is a new preimage version, or in `EXCLUDED`, where it
is a field an attacker can edit without breaking the chain.**

For `approval_ref_status` the second option is not available. It records *why an
approval did or did not authorise this action* — flipping it from `expired` to
`honored` is precisely the edit a chain exists to catch. **It must be hashed.**

So `ND-009` forces **`onedoor/row-preimage/2`**. Three facts make that cheap **right
now** and expensive very soon:

- Chaining is **opt-in and off**. No deployment has enabled it; no row has ever been
  sealed under `/1` outside this repository's tests.
- The version is already in the magic string, so `/2` produces visibly different bytes
  and cannot be confused with `/1`.
- Once **one** deployer enables chaining, `/2` becomes impossible for them: the table
  forbids `UPDATE`, so sealed rows can never be re-hashed, and a mixed-version chain
  would need a per-row version marker that the envelope does not have.

**This is the decomposition's first question (§6).** Delivery will not bump a frozen
preimage on its own authority.

## 3. Finding two: "principal" is not a field this system has

R034 says refs are **principal-scoped**, and `CONFORMANCE.md` §6 says a ref presented
under a different principal is `unknown` for the verdict and `principal_mismatch` in
evidence. Both presuppose that a request has a principal the engine can compare.

Checked against the schema and the model:

| Candidate | What it actually is |
|---|---|
| `ActionRequest.session_id` | optional, free-form, set by the caller — **unauthenticated** |
| `approvals.decided_by_session` | who *approved*, not who the approval is *for* |
| the API key on `/v1/decide` | authenticated, but coarse: `require_decide` is one key for the whole deployment |
| `ActionRequest.source` | `llm`/`ui`/`scheduler` — a channel, not a principal |

There is no authenticated per-caller identity in onedoor today. Scoping a ref to
`session_id` would mean **an attacker who can present a ref can also present the
matching `session_id`**, because both arrive in the same untrusted body — a check that
looks like authorisation and is decoration.

Delivery will not implement a security control that cannot hold. **Second question,
§6.** The honest interim is that `principal_mismatch` is a *reserved, never-emitted*
status until an authenticated principal exists (`ND-004`/`ND-005` territory), recorded
the way `sender_mismatch` already is: in the vocabulary, held unemitted by a test, so
the evidence field is complete in one increment without claiming a check that never ran.

## 4. Finding three: two doors into one state machine

`approvals.state` is `pending | approved | denied | expired | executed`. The PDP path
walks `pending → approved → executed`. A PEP-driven resumption must consume a ref
**exactly once**, and the DoD requires two simultaneous resumptions to yield exactly
one execution.

The atomicity primitive already exists and is the right one: `cas_approve`'s
conditional `UPDATE ... WHERE state='pending'` and `rowcount == 0` check. Consumption
is the same shape one state along — a conditional update from `approved` guarded by
`rowcount`, inside the `BEGIN IMMEDIATE` that `decide_and_reserve` already holds.

**The trap to avoid**: reading the approval, deciding, then marking it consumed.
Between the read and the mark, a second resumption reads the same `approved` row and
both proceed. The consume must be the *first* write and its `rowcount` the gate — lose
the CAS, and the ref evaluates **as absent**, which per the ruling means the action
re-evaluates on its own merits and a Tier-3 action simply proposes again. **A lost race
never denies and never errors**; it just does not grant.

## 5. Work order

- **A1** — `approval_ref` on `ActionRequest` and `/v1/decide`; absent stays absent.
- **A2** — the resolver: one function returning `(authorised: bool, status:
  ApprovalRefStatus)`, with **every** failure mode returning `authorised=False` and its
  own status. Uniform treatment is the security property: the caller cannot tell
  `unknown` from `expired` from `consumed` by behaviour, only the *evidence* can.
- **A3** — action-equivalence binding (§6's third question).
- **A4** — atomic single-use consumption per §4, plus the DoD concurrency test.
- **A5** — `approval_ref_status` on the decision row, after §6's first ruling.
- **A6** — kill switch after a valid ref, asserted directly. `decide_and_reserve`
  already clamps under `approved_override`; the test makes it a stated invariant rather
  than an emergent one, the way `ND-040`/U4 taught.

## 6. The questions this decomposition surfaces

**1. Does `ND-009` bump the row preimage to `/2`?** `approval_ref_status` must be
hashed (§2), and hashing a new column is a new preimage version. **Free today,
impossible after the first deployer enables chaining.** If the answer is yes, delivery
proposes bumping **once** and folding in any other column the epic already knows it
needs — `ND-015`'s `sig`/`key_id`/`alg` are *excluded* by construction, so the likely
answer is that `approval_ref_status` is the only addition, but it is worth asking now
rather than bumping twice.

**2. What is a principal?** (§3.) Delivery's proposal: `principal_mismatch` is
reserved and **never emitted** until an authenticated identity exists, held by a test
exactly as `sender_mismatch` is. The alternative — scoping to `session_id` — is a check
an attacker satisfies by copying a value out of the same request body, and shipping it
would put a control in `CONFORMANCE.md` that does not control anything.

**3. What is action-equivalence?** The draft says the approval authorises the action's
**effect identity**, not a byte-identical request. Delivery reads that as: same
`action_type`, and the same resolved **effect set** — so a human approving "move money
to X" cannot have that approval spent on a different action that happens to share a
tool name. But the effect set is computed from `params` at decide time
(`param_effects`), which means a resumed request with different params can resolve to a
different effect set and correctly fail equivalence — while one with *cosmetically*
different params resolving to the same effects passes, which is the point of not
requiring byte-identity. **Delivery will not guess the boundary**: the difference
between "same effects" and "same effects and same bounds-relevant params" is the
difference between an approval that can be spent on a bigger transfer and one that
cannot.

A1, A2 and A6 are unblocked and can start now; A3, A4's evidence half and A5 wait on
the three answers above.
