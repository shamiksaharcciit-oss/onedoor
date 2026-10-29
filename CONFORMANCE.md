# Conformance

Per-requirement status against the AADP Internet-Draft (`draft-saha-aadp`) and
the bound-permit profile (`draft-saha-aadp-bound-permit`), stated plainly:
implemented and tested, or a disclosed gap. Nothing here is aspirational --
every vector's status is traced to a real test in `VECTOR_STATUS`
(`tests/permit/test_conformance_vectors.py`); every gap names where the open
work is tracked.

## 1. The decision pipeline

One ordered check sequence, read from `onedoor.guardrail.decision.decide_and_reserve`
as it stands today: kill switch; policy lookup and the effective tier
(default-deny for an unknown action type, the opaque-host and
no-compensating-command escalations); external authorization, when a policy
declares one and a resolver is configured (a mandate-layer deferral may deny
outright or escalate to the approval step, never re-consulted on resumption);
observe (a read, audited and returned, never a proposal or a reservation);
bounds, including the bound-permit presentation's own preconditions; the
approval step, for whatever still needs one; dry-run; caps, checked and
reserved inside the deciding transaction; intent recorded.

Not four outcomes: `decide_and_reserve` returns either an `ActionResult`,
whose `decision` is one of `executed`, `dry_run`, `proposed` or `denied` (a
fifth value, `failed`, exists on the same `Decision` enum but is only ever
set by `report_result`, never by this function), or a `PermittedIntent`,
which carries no `Decision` value at all -- the obligation-bearing case the
caller must still report. `observe` and `permitted` both resolve to
`executed` in spirit, but only `observe` is terminal on the spot; a
permitted action's own row is recorded `executed` immediately, while the
caller's own report is what the ledger's second row states actually
happened.

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
