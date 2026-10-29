# Conformance

Per-requirement status against the AADP Internet-Draft (`draft-saha-aadp`) and
the bound-permit profile (`draft-saha-aadp-bound-permit`), stated plainly:
implemented and tested, or a disclosed gap. Nothing here is aspirational --
every vector's status is traced to a real test in `VECTOR_STATUS`
(`tests/permit/test_conformance_vectors.py`); every gap names where the open
work is tracked.

## 1. The decision pipeline

One ordered sequence, read from `onedoor.guardrail.decision.decide_and_reserve`'s
own numbered step comments, every one, in the code's own order. A test
(`tests/test_conformance_md.py`) reads both this section's step labels and
the code's and fails if either side gains, loses or reorders one.

Two steps run before the kill switch is even read, outside the deciding
transaction: the replay guard (a repeated `request_id` returns the stored
result outright, never re-evaluated) and the reclaim of any reservation
whose deadline has passed unreported. Inside the transaction:

- `1` the kill switch is READ here -- not decided here. An engaged switch
  denies only at `7`, for a fresh request (or at its own point mid-resumption,
  immediately after default-deny); every refusal reachable before that --
  `2b`'s malformed exit, `3a`'s default-deny, `4b`'s external-authorization
  denial, `5`'s observe, and `6`/`6b`/`6c`'s bounds and `present_bound` exits
  -- wins over it first. A read (`observe`) is exempt from the switch
  entirely.
- `1b` the approval reference is resolved, straight after the kill-switch
  read and before policy lookup.
- `1c` the approval a resumption resumes is consumed, in the same
  transaction, right after.
- `2` policy lookup, which does not itself exit.
- `2b` effect resolution (declared labels plus deterministic parameter
  rules), which exits `malformed`.
- `3/4` the effective tier is resolved, with every escalation that can raise
  it: the effect-tier floor, the opaque-host invariant, the
  no-compensating-command demotion, and the kill-switch clamp (to `CONFIRM`,
  not an exit).
- `3a` default-deny exits here -- after effect resolution, not at policy
  lookup itself.
- `4b` external authorization: consulted only when a policy declares it and
  a resolver is configured; denies outright, or escalates a `PENDING`
  verdict to the approval step; never re-consulted on resumption.
- `5` observe: a read, audited and returned, never a proposal or a
  reservation.
- `6` bounds, which can exit `bounds`.
- `6b` `present_bound`'s audience match, which can exit `present_bound`.
- `6c` the bound permit's own issuance preconditions, which can also exit
  `present_bound`.
- `7` the approval step: a fresh request's kill-switch denial lands here if
  nothing above already exited; a resumption's own resume-key check can
  exit `resume_request_mismatch` here too; otherwise a proposal is created.
- `8` dry-run (terminal).
- `9` caps, checked and reserved inside this same deciding transaction.
- `10` the intent is recorded, minting the bound permit's `jti` where one is
  owed.
- `10b` the reservation ledger row, if caps were actually reserved.

After the transaction commits: the bound permit itself is signed, and the
caller's consumed approvals are linked to the audit row -- neither is a
numbered step inside the pipeline; both still run before this function
returns.

Not four outcomes: a fresh evaluation's `ActionResult.decision` is one of
`executed`, `dry_run`, `proposed` or `denied`, or the function returns a
`PermittedIntent`, which carries no `Decision` value at all -- the
obligation-bearing case the caller must still report. A fifth value,
`failed`, exists on the same `Decision` enum; it is not reachable from a
fresh evaluation, but it is reachable from this same function two other
ways: the replay guard (above) can return a stored result whose `decision`
is `failed` (an executed-then-failed request, replayed), and the reclaim
step writes `failed` expiry rows of its own, though it never returns them to
the caller.

- An action type absent from the policy table is denied (`default_deny`),
  never proposed.
- A Tier-1 policy with no `compensating_command` cannot boot and cannot
  execute (runtime demotion to Tier 3).
- Bounds are validated before a proposal exists, so an approver only ever
  sees an in-bounds request.
- A dry run never consumes caps.
- Two concurrent requests cannot share a cap's last slot (AADP §6: the
  reservation and the reclaim of an unreported one are both audited events,
  never a silent timeout).
- `report_result`'s outcome vocabulary (AADP -03 §4.1) is four values, not a
  boolean; `no_effect` releases the value dimension of a reservation, never
  the rate dimension.

## 2. The audit log and its chain

Append-only; every row carries the policy hash in force when it was decided
(AADP §10), so a verdict re-derives against the exact rules that produced it.
Each row's `row_hash` covers the previous row's hash, held in that row's own
`prev_hash` (the audit chain's own signing and hash design); the preimage --
the exact bytes `row_hash` is computed over -- is normatively defined in
[`docs/row-preimage.md`](docs/row-preimage.md),
with a second, independent implementation in
`tests/guardrail/test_row_preimage.py` built from that text rather than from
the code it checks.

Versioned, never silently: `onedoor/row-preimage/1` through `/7`, each
addition classified as hashed or excluded with a stated reason
(`onedoor.guardrail.preimage.FIELD_ORDER`/`EXCLUDED`), enforced by a test that
fails the moment a migration adds a column nobody classified.

## 3. Bound permits (bound-permit profile)

`onedoor.permit` is the standalone recipient-side package; `onedoor.guardrail.bound_permit`
is the issuer side. Appendix B's 24 conformance vectors
(`tests/permit/vectors/manifest.json`), traced against real tests in
`tests/permit/test_conformance_vectors.py`'s `VECTOR_STATUS`:

| Vector | Checks | Status |
|---|---|---|
| V01 | Body changed after signing -> `content-mismatch` | Implemented |
| V02 | Path changed after signing -> `request-signature-invalid` | Implemented |
| V03 | Presented to a different recipient -> `audience-mismatch` | Implemented |
| V04 | `aud` carries two values -> `audience-mismatch` | Implemented |
| V05 | Presented after `exp` -> `expired` | Implemented |
| V06 | `exp` later than `execute_within` -> `lifetime-invalid` | Implemented |
| V07 | Same permit, same body, presented twice -> stored result returned | Implemented |
| V08 | Same `jti`, different body -> `idempotency-conflict` | Implemented |
| V09 | Signed by a key other than `cnf.jkt` -> `presenter-key-mismatch` | Implemented |
| V10 | No signature at all (bearer presentation) -> `request-signature-missing` | Implemented |
| V11 | Signature omits a covered component -> `binding-incomplete` | Implemented |
| V12 | Same meaning, different bytes -> `content-mismatch` | Implemented |
| V13 | Same bytes, `A` derived differently -> `action-mismatch` | Implemented |
| V14 | Unknown `authorization_details` type -> `unknown-authorization-type` | Implemented |
| V15 | Action type outside the issuer's scope -> `issuer-out-of-scope` | Implemented |
| V16 | Amount above the issuer's limit -> `issuer-out-of-scope` | Implemented |
| V17 | `status-checked`, policy version superseded -> `stale-policy` | **Gap** -- no status mechanism exists; see §4 |
| V18 | `status-checked`, endpoint unreachable -> `status-unavailable` (could-not-check) | Implemented |
| V19 | Mandate digest differs from the evaluated AAE -> `mandate-mismatch` | Implemented |
| V20 | Referenced AAE evaluates to `PENDING` -> `mandate-pending` | Implemented |
| V21 | Permit carries a `parent` -> `chained-permit-unsupported` | Implemented |
| V22 | The recipient confirmation (profile §10) | **Gap** -- not in this release; under review, see §4 |
| V23 | Consume store unavailable -> could-not-check, not a denial | Implemented |
| V24 | Local policy denies -> permit not consumed | Implemented |

22 of 24 implemented; 2 disclosed gaps (V17, V22).

`jti` is minted independently of any other record onedoor keeps (at least
128 random bits), per profile -00 §3.2; the mapping back to the intent it
was issued for is recorded on the audit row (`actions_audit.permit_jti`).
The request's `Idempotency-Key` MUST equal the permit's own `jti` (profile
-00 §12), checked at `recipient.verify`'s step 8.

## 4. Open gaps, and where they are tracked

- **V17 (status-checked currentness).** `currentness: "status-checked"`
  always reports `could-not-check`; no status mechanism (list lookup or
  stapled freshness) is wired in. Design options are laid out in
  [`docs/design/bound-permit-next.md`](docs/design/bound-permit-next.md) §1.
- **V22 (the recipient confirmation).** Closing bound-permit profile §10 is
  under active review, not in this release. Design is in
  [`docs/design/bound-permit-next.md`](docs/design/bound-permit-next.md) §3.
- **The mandate reference, issuer side.** The recipient side of a referenced
  mandate (step 11) is implemented; nothing on the issuer side yet populates
  a permit's `mandate` claim from onedoor's own mandate-layer deferral. See
  [`docs/design/bound-permit-next.md`](docs/design/bound-permit-next.md) §2.
