# CONFORMANCE.md — onedoor ↔ AADP

**Implementation:** onedoor `0.4.0` — **published** 2026-08-22 (tag `v0.4.0` @ `5c50466`,
PyPI, GitHub release). Artifact digests on PyPI verified byte-identical to the build.
**Standard:** AADP Internet-Draft `draft-saha-aadp-01`
**Test suite:** 135 passed at the `0.3.5` baseline; **175 passed / 8 skipped** on `main`
at 2026-08-21 (Python 3.12, `pytest -q`, all four gates green)
**Last verified:** 2026-08-20, by direct source inspection at `3dfe3cd`
**Spec rulings in force:** Core→Delivery Responses **001–015** (001–006 on 2026-08-20; 007–015 on
2026-08-21), plus Core Forward 003, plus Core→Forensics 009 §3, 010 §2 and 012 §1 by cross-session forward.
Digest register: `docs/from_core/INTEGRITY.md`, generated. Memos 007+ carry integrity footers; verify
with `python -m scripts.verify_memo docs/from_core/*.md`.
**Open spec questions:** **none, on either side.** Responses 001–005 ruled everything
raised in Escalations 001–005; 006 was acknowledgment; 007 adopted one new normative
rule from a delivery finding (anchor hygiene — see §5). **`ND-001` and `ND-039` are
both unblocked.**
Nothing in `0.3.6` is gated. **[reconcile-01] is closed** — the `rederivable-manifest/`
artifact was checked against Response 002 on 2026-08-20 and conforms exactly; the
digest columns in `ND-002`'s migration are final.

This file is the contract surface between onedoor delivery and the core
(standards/research) session. Core reads it to know what the reference
implementation actually does; delivery updates it on every change that moves a
requirement's status. **Nothing is marked ✅ that is not implemented *and*
covered by a passing test.**

> **Provenance caveat.** Neither session holds `draft-saha-aadp-01`. Delivery has
> no normative text at all; core's Response 001 is grounded in the **`-00`** text,
> which it verified directly. Three rulings touch `-01`-only additions (the §12.1
> transport section, the manifest schema, the `-01` Implementation Status edits) and
> are marked **[reconcile-01]** — the decision is made, the citation check is
> pending. Section references below are core's where a ruling supplied one, and
> otherwise carried over unverified from the roadmap of 2026-08-20.

> **Target vocabulary.** From `0.4.0` onedoor emits the **`aadp/0.2`** reason-code
> vocabulary. The settled shape is in §6 — read it before implementing `ND-002`,
> `ND-003`, `ND-005` or `ND-009`; it is the spec surface those tickets build to.

## Legend

| Mark | Meaning |
|---|---|
| ✅ | Implemented and covered by a passing test |
| ⚠️ | Partially implemented, or implemented without conformance-level test coverage |
| ❌ | Not implemented |
| 🔍 | Status uncertain — needs core to confirm the requirement before it can be judged |

---

## 1. Requirements met

Verified against the source at `3dfe3cd`. "Evidence" names the module that
implements it and the test file that holds it in place.

| Requirement | Status | Evidence |
|---|---|---|
| Two-phase exchange: `decide_and_reserve` → `report_result`; intent durable before the permit returns | ✅ | `guardrail/decision.py`; `tests/guardrail/test_decision_split.py`, `test_ordering.py` |
| Kill switch evaluated first, not overridable by policy | ✅ | `guardrail/killswitch.py`; `tests/guardrail/test_kill_switch.py` |
| Default-deny on unknown action types | ✅ | `Policy.is_default_deny`, `CheckId.DEFAULT_DENY`; `tests/guardrail/test_default_deny.py` |
| Autonomy tiers 0–3, nominal + effective tier both recorded | ✅ | `models.Tier`, `PolicyDecision.nominal_tier`/`effective_tier`; `tests/guardrail/test_tier_resolution.py` |
| Effect labels and parameter-derived effects (aliasing-resistant) | ✅ | `models.EffectPolicy`, `ParamEffectRule`; `tests/guardrail/test_effects.py` |
| Parameter bounds (numeric, enum, required, strict-params) validated before proposal | ✅ | `guardrail/bounds.py`; `tests/guardrail/test_bounds.py` |
| Budget caps (daily rate, €/day, €/month), atomic all-or-nothing reservation | ✅ | `guardrail/caps.py`, IMMEDIATE tx in `store/db.py`; `tests/guardrail/test_caps.py`, `test_concurrency.py` |
| Cost resolution with deny-on-unknown (F7) | ✅ | `Policy.cost_param`, `CheckId.COST_UNKNOWN`; `tests/guardrail/test_cost_resolution.py` |
| Dry-run, permanent and time-boxed; rehearsals reserve no budget | ✅ | `Policy.dry_run`/`dry_run_until`; `tests/guardrail/test_dry_run.py` |
| Reversibility as an autonomy precondition | ✅ | `CheckId.NO_COMPENSATION`, `Policy.compensating_command`; `tests/guardrail/test_undo.py` |
| Undo window and governed reversal through the full pipeline | ✅ | `guardrail/undo.py`, `Policy.undo_window_seconds`; `tests/guardrail/test_undo.py` |
| Approval lifecycle: pending → approved/denied/expired, single-use, atomic | ✅ | `guardrail/approvals.py`, `models.ApprovalState`; `tests/guardrail/test_approvals.py` |
| Idempotency / replay by `request_id`; re-decide re-reserves nothing | ✅ | `decision.py:92` replay guard, `UNIQUE(request_id, kind)`; `tests/guardrail/test_approvals.py`, schema `0001_init.sql` |
| Reservation reclamation: unreported permits release budget on deadline, audited | ✅ | `cap_reservations` (`0005_reservations.sql`), `audit.append_expiry`, `CheckId.EXPIRED`; `tests/guardrail/test_reservation_reclaim.py` |
| Append-only audit, structurally enforced | ✅ | `actions_audit_no_update` / `actions_audit_no_delete` triggers; `tests/guardrail/test_audit_append_only.py` |
| Policy content-hash stamped on every audit row (re-derivability) | ✅ | `audit.append` reads `policy_current.version_hash`; `tests/guardrail/test_policy_provenance.py` |
| Group-commit batching of result rows only; intent rows never batched | ✅ | `audit.append_buffered` / `flush`; `tests/guardrail/test_group_commit.py` |
| HTTP/JSON binding: `/v1/decide`, `/v1/report`, `/v1/approvals`, approve/deny, `/v1/killswitch`, `/v1/health` | ✅ | `service/app.py`; `tests/service/test_service.py` |
| Role-split authorization (decide role vs admin role) | ✅ | `require_decide` / `require_admin`, `ONEDOOR_DECIDE_KEYS` / `ONEDOOR_ADMIN_KEYS`; `tests/service/test_service.py` |
| Fail-soft on connector failure (execution error ≠ authorization) | ✅ | `guardrail/executor.py`; `tests/guardrail/test_fail_soft.py` |

### Enforcement points

| PEP | Status | Note |
|---|---|---|
| In-process library binding (`governed()`) | ✅ packaged | `guardrail/__init__.py` |
| MCP stdio proxy | ✅ packaged | `mcp/proxy.py`; `tests/mcp/` |
| LangChain agent middleware | ✅ packaged | `integrations/langchain_middleware.py`; `tests/integrations/test_langchain_middleware.py` (7 tests) |
| LiteLLM gateway guardrail | ✅ **example, conformant** | Two-hook split (`ND-021`, `0.3.6`): `async_pre_call_hook` decides and holds the permit, reporting nothing; `async_post_call_success_hook` / `async_post_call_failure_hook` report the real outcome, correlated by `data["litellm_call_id"]`. `examples/litellm_guardrail.py`; `tests/examples/test_litellm_guardrail.py` (10 tests, including the regression that fails against the pre-`0.3.6` behaviour). **Conformant, but an example and not a packaged PEP** — it lives under `examples/`, unlike the MCP proxy and the LangChain middleware. |
| LangGraph tool wrapper | ⚠️ example | `examples/langgraph_tools.py`; interrupt-based approval demo, no packaged support |

---

## 2. Requirements not met (the conformance gap)

Numbering follows roadmap §2 so core can diff the two tables directly.
**Three rows correct the roadmap** — flagged inline and summarised in §3.

| # | AADP requirement | Status | Actual state at `3dfe3cd` | Ticket |
|---|---|---|---|---|
| A1 | Transport security: the decide/report channel MUST provide confidentiality, integrity, mutual auth (§12.1) | ❌ | Bearer token over whatever the deployer terminates. Zero TLS/mTLS surface in the codebase: no `ssl_`, `mtls`, or `client_cert` identifier anywhere. **Settled (E4): the mandate is on the three *properties*, not on mTLS as a mechanism.** mTLS/RFC 9325 is the RECOMMENDED profile and onedoor's tested default; a mutual-auth mesh or the §uds local socket also satisfy it. onedoor MUST refuse to serve without the properties. **[reconcile-01]** | `ND-004` |
| A2 | Sender-constrained permits (permit bound to PEP key/identity) (§12.1) | ❌ | Permits are pure bearer: `PermittedIntent` carries `intent_audit_id` and possession alone is sufficient to report. No key material in the codebase. **Settled (E5): bind to the client-certificate thumbprint (RFC 8705), checked at *report* time.** A mismatch is refused **in the decision pipeline with an audited `sender_mismatch` entry**, never dropped silently at the transport layer. DPoP-style proof-of-possession is **A10, not a step toward A2** — see `ND-016`. | `ND-005` |
| A3 | Downstream idempotency-key propagation for exactly-once *effect* (§idem, and new `-02` text) | ❌ | `request_id` gives exactly-once *decision*, enforced by `UNIQUE(request_id, kind)`. No adapter derives or forwards a key downstream. **Settled (E9): the mechanism is an obligation, not a bare key.** Key derived from the **permit alone** (`permit_id` verbatim, or UUIDv5 over it where the target constrains format); field name is the adapter's contract; obligation type **`idempotency_key`**; a PEP that cannot honour it MUST NOT act and reports `not_attempted`. **Blocked on `ND-038` — onedoor has no obligation machinery (N6).** | `ND-008` |
| A4 | Unit-neutral reason codes + structured `budget` object (§decideresp) | ✅ | `CheckId` still emits `cap_daily_rate` / `cap_eur_day` / `cap_eur_month` (`models.py`), and `caps.py:139–149` formats budget state into a free-text `detail` string. `PolicyDecision` has no `budget` field, and **no AADP protocol version is stamped anywhere in the package or the evidence store**. **Landed in `0.4.0` (unreleased), W4+W5:** `cap_rate` + `cap_value` replace all three; `sender_mismatch` reserved and unemitted; every row stamped `aadp/0.2` with the absent-value fallback to `aadp/0.1`; the seven-field `budget` object present iff deny + cap, returned **and** persisted to `budget_json`; `snapshot_schema` records which canonicalisation produced a policy hash (R019). ✅ **shipped in `0.4.0`.** Evidence: `tests/guardrail/test_reason_vocabulary.py`, `test_budget_object.py`. | `ND-002`, `ND-003` |
| A4b | Report outcome vocabulary: `success \| failure \| timeout \| not_attempted` (§reportreq) | ✅ | **Live conformance defect, found 2026-08-20 (Escalation 005).** `report_result(..., ok: bool, ...)` has **no outcome parameter at all** — onedoor can express two of the four outcomes; its own docstring names three. `not_attempted` and `timeout` both collapse to `ok=False` → `Decision.FAILED` + `action.failed`. Three consequences: (a) the audit asserts an attempt that never happened; (b) `cap_reservations` is settled **unconditionally before the outcome is examined** (`decision.py`), so a conformant `not_attempted` **permanently charges budget for an action that never occurred**; (c) the fix is an API change, not an enum edit. Not reachable until obligations ship — reachable the moment `ND-038` does. **Landed in `0.4.0` (unreleased), W6:** `report_result` takes a four-value `Outcome`; `/v1/report` accepts the wire field; settlement is outcome-dependent (settle on `success`/`failure`/`timeout`, **release on `not_attempted` as an audited `reservation_released` row**); `connector_ok` is NULL rather than false for a non-attempt. ✅ **shipped in `0.4.0`.** Evidence: `tests/guardrail/test_report_outcome.py`, whose tests are named for the clauses of the §implstatus disclosure sentence so the draft is checkable against the suite. | `ND-039` |
| A5 | `isolate` obligation — enforce an isolation boundary | ❌ | No obligation type beyond the permit/report exchange. Needs a micro-VM or container PEP that does not exist. | `ND-030` |
| A6 | PEP-driven resumption via `approval_ref` on decide (§decidereq, §idem, §approvals) | ❌ | **Roadmap correction.** The roadmap states "field exists in the model". It does not: `approval_ref` appears **zero times** in the entire repository. Greenfield in *code*; **fully specified already in `-00`** (E2) — build to the draft, do not invent. Binding is by **action-equivalence, not `request_id`**; single-use; any invalid ref is **evaluated as though no approval had been supplied** (so a bad ref never grants); kill switch still wins. **Introduces zero new reason codes ⇒ independent of `ND-002`.** | `ND-009` |
| A7 | PEP failure semantics `fail_static` / `fail_open` on PDP unreachability | ❌ | `test_fail_soft.py` covers *connector* failure inside the engine — a different thing. No packaged PEP implements configurable behaviour when the **PDP itself** is unreachable. | `ND-022` |
| A8 | Local Unix-socket binding for same-host PEPs (§uds) | ❌ | HTTP only. **Reclassified after E4:** with the transport mandate expressed as *properties*, a UDS binding with peer credentials is a **conforming A1 profile**, not merely a same-host convenience. Raises its value; it is now an alternative way to satisfy A1 for co-located PEPs. | `ND-023` |
| A9a | Obligation-type registry hygiene (§iana, §obligations) | ❌ | **Assessed by core (B3): specified, sound, checkable in principle.** onedoor's duties — emit only registered types, enforce unknown-obligation-fail-closed. **Correction (Escalation 003/E11): neither duty can be enforced against machinery that does not exist (N6).** Blocked on `ND-038`; no longer the small ticket it was recorded as. | `ND-037` |
| A9b | Multi-dependency trust base (paper-3 T-set / dependency closure) | 🔍 | **Research-coupled; not a delivery ticket (B3).** §evidence mandates the *floor* — re-derivable "given the policy version in force" — which onedoor already meets. Lifting the fuller T-closed trust base into the wire is core's call and has not happened. Implement the floor only. | — |
| A10 | Action-bound signed permit (cross-domain / terminating intermediary) — AADP *future work* | ❌ | Same primitive as A2 extended. Nothing exists. | `ND-016` |

### Veto-parity items (roadmap §3.2) — tracked here because A2/A10 are the same build

| # | Capability | Status | Actual state |
|---|---|---|---|
| P1 | Hash-chained audit entries | ❌ | `actions_audit` has no `prev_hash` / `entry_hash` column (`0001_init.sql`). Tamper-*evident* is not yet true; only append-only-by-trigger. | `ND-001` |
| P2 | Signed decision receipts (Ed25519) | ❌ | No signing, no key management, no crypto dependency in `pyproject.toml`. | `ND-015` |
| P3 | Content-addressed, re-derivable receipts + Merkle anchoring | ❌ | Policy-hash stamping is the nearest existing primitive; the paper-3 verdict manifest (`E`, `I`, `T`, `v`) is not implemented. **Settled (E3): carry `E`/`I`/`T` as opaque content-addressed digests, never inlined structures** — `I`'s preimage will generalise to stage-attribution instruments, and inlining it would re-hash frozen rows. | `ND-017` |

---

## 3. Corrections to the roadmap of 2026-08-20

Raised to core because two of the three change what the draft's Implementation
Status section should say.

1. **A6 is misstated — in the roadmap only.** Roadmap §2 records "Field exists in
   the model"; `approval_ref` does not exist in the repository at all.
   *(Grep evidence: `grep -rn "approval_ref" --include=*.py --include=*.md --include=*.yaml .` → no matches at `3dfe3cd`.)*
   **Resolved (B1): the draft was never wrong.** §implstatus already states the
   field is not accepted and that PEP-driven resumption is "specified but not yet
   exercised by an implementation." No draft correction. The **L** re-estimate stands.
2. **A7's status is over-read — in the roadmap only.** The roadmap implies the gap
   is only that the PEPs "don't implement configurable fallback".
   `tests/guardrail/test_fail_soft.py` tests connector fail-soft *inside* the
   engine, which may read as partial coverage to someone scanning the suite. It is
   unrelated. **Resolved (B2): the draft doesn't overstate either** — §implstatus
   makes no claim here, and A7 is a **PEP-side** requirement while onedoor is the
   PDP, so "none" is the honest and expected status. `CONFORMANCE.md` "none" stands.
3. **The LiteLLM example is a live correctness defect, not a roadmap item.**
   Roadmap §5 lists "fix the LiteLLM example… or retire it" under *Reach*, in the
   long-term bucket. It is published, documented (`docs/integration-litellm.md`),
   and demonstrates a violation of the two-phase contract that the standard exists
   to define. Delivery proposes pulling it to the near-term phase (`ND-021`).

## 4. Gaps found in the code that the roadmap does not list

| # | Finding | Why it matters | Ticket |
|---|---|---|---|
| N1 | The HTTP service holds pending-intent state **in process memory** (`service/app.py` module docstring): "a restart between decide and report leaves the honest 'intended, unconfirmed' row in the audit log, and v0.4 rebuilds intents from that row instead of memory." | A PDP restart between decide and report strands every in-flight permit. The docstring already promises the fix for v0.4 and it has not landed. It also blocks the multi-replica goal (roadmap §5), because in-memory intent state is not shared. | `ND-010` |
| N2 | Group-commit (`audit.append_buffered` / `flush`) writes result rows with a single `executemany`. | A hash chain requires each row to hash its predecessor, computed in order. P1 and group-commit interact directly; the chain must be computed inside `flush` before the `executemany`, or group-commit must be disabled when chaining is on. This is a design constraint on `ND-001`, not a separate feature. | noted on `ND-001` |
| N3 | The schema carries tables from an earlier product (`intake_policy`, `preferences`, `sessions`, `push_subscriptions`) that nothing in `onedoor/` reads. `0001_init.sql` still calls itself "Sutradhar M0 schema". | Dead schema in a governance product invites the reader to assume governed surfaces that do not exist. `push_subscriptions` is genuinely planned (roadmap §5, notifications); the other three appear vestigial. | `ND-024` |
| N4 | **CLOSED, `0.3.6` (`ND-036`).** `ROADMAP.md` is now a pointer to `BACKLOG.md` + `CONFORMANCE.md` plus only the material that does not go stale. **Eleven work items lived in that file and nowhere else** — found by checking each deleted bullet against both ledgers rather than spot-checking a few — and were migrated as `ND-040`–`ND-047` and notes on `ND-019`/`ND-031`, not deleted. ~~The repository carries its own `ROADMAP.md`, distinct from the attached `onedoor_Roadmap_20260820.md` that this backlog is built from.~~ | Two roadmap documents, one public and one working, will diverge. Readers of the repo will take the public one as current. Delivery proposes the public `ROADMAP.md` becomes a short pointer to `BACKLOG.md` + `CONFORMANCE.md`, which are the live artifacts. | `ND-036` |
| N5 | **Corrected 2026-08-20.** The original entry said "`[tool.mypy] strict = true` and `ruff` are configured". Half wrong: mypy was configured, **ruff was not** — there is no `[tool.ruff]` block and no `ruff.toml` anywhere in the repo, only `ruff` as a dev dependency, unpinned at `>=0.8`. Delivery asserted the configuration from the dependency's presence and wrote a CI job invoking two tools it had never run. At `cbb8414` all three gates failed: **78 lint errors, 49 files unformatted, 7 type errors.** | Fixed in `0.3.6`: explicit `[tool.ruff]` (deliberate rule set, `line-length = 100`, `BLE001` **not** selected — fail-soft is designed behaviour, not an oversight); `ruff` **pinned** to `==0.16.4` because an unpinned linter makes CI non-deterministic; `mypy --strict` clean via `EngineConfigLike`, a Protocol replacing the `config: object` annotation that had been disabling type checking on every attribute access to avoid an import cycle. All four gates now pass: **138 passed, ruff clean, format clean, mypy clean.** | `ND-025` |
| N6 | **onedoor has no obligation machinery whatsoever.** All five occurrences of "obligation" in the package are prose using the word colloquially (`decision.py:12,57`, `app.py:5,20`, `notify.py:10`). No obligation type, no field on the permit, no discharge evidence, no `not_attempted` outcome (`decision` admits only `executed\|dry_run\|proposed\|denied\|failed`), no unknown-obligation check. | **Safety-relevant.** §obligations' fail-closed guarantee is a property of *conformant* PEPs; onedoor's packaged PEPs have no obligation code path, so an obligation attached to a permit would be **silently ignored and the action executed**. For `idempotency_key` that is a duplicate effect; for `isolate` (A5) it is an action the policy required to be contained running uncontained, with the audit recording a clean success. Invisible in the roadmap because A3, A5 and A9a look like three unrelated items. | `ND-038` |
| N7 | `params_json` and `payload_json` are written with `json.dumps(..., default=str)` and **no `sort_keys`** (`audit.py:64,72,260,264`). Key order follows the PEP's arrival order; separators carry spaces; JSON numbers render via Python `repr` (`250.00` → `250.0`); non-JSON types are stringified. | Both columns sit inside the `ND-001` hash preimage. As written, two semantically identical requests hash differently, no non-Python verifier agrees, and IEEE doubles enter through the one door §messages' "never float" rule doesn't guard. Raised as **E10**; gates `ND-001`. | `ND-002` (row format), `ND-001` |

## 5. Questions to core — state

### Resolved by Response 001 (2026-08-20)

| Was | Ruling |
|---|---|
| A4 reason-code names + `budget` shape | `cap_rate` / `cap_value`; `budget` pinned (§6); clean break at `0.4.0`; protocol → `aadp/0.2` |
| A4 historical-row reading | **Absorbed into the draft** — deprecated codes retained permanently in the IANA registry; each row read in the scope of its recorded `protocol`. See E6 below. |
| A6 `approval_ref` semantics | Fully specified in `-00`; action-equivalence binding; single-use; invalid ⇒ evaluate-as-if-absent; kill switch wins. **Zero new codes.** |
| P1/P2/P3 receipt format | **Assent** — freeze the envelope and canonicalisation now, land in three increments, later fields present-but-empty, `E`/`I`/`T` opaque. |
| A1 mTLS normative? | Property mandate; mTLS RECOMMENDED profile. **[reconcile-01]** |
| A2 binding mechanism | Cert thumbprint (RFC 8705) now; DPoP reserved to A10. Mismatch ⇒ audited `sender_mismatch`. |
| A9 | Split into A9a (checkable now → `ND-037`) and A9b (research-coupled, no ticket). |

### Resolved by Response 002 (2026-08-20)

| Was | Ruling |
|---|---|
| E6 absent-`protocol` fallback | Delivery's wording adopted: an unstamped row MUST be read as `aadp/0.1`; a PDP at `aadp/0.2+` MUST stamp every row. **Ship in `0.4.0`; `-02` ratifies.** |
| E7 `budget` persistence | **Confirmed normative** under §evidence — a `cap_value` denial that cannot name its window is not re-derivable. `budget_json` in canonical form. Permit-side `budget` deferred as a clean additive change. |
| E8 decimal canonicalisation | **Shortest exact form, uniform across dimensions, wire = storage = preimage.** `"250.00"` → `"250"`; `"0.50"` → `"0.5"`; negative zero → `"0"`. E1.2's examples corrected. Datetimes likewise: fractional seconds shortest-exact, omitted when zero. |
| [reconcile-01] | **Re-frozen by ruling** rather than against the lost schema: `e_digest`, `i_digest`, `t_digest`, `v_digest`, `anchor_ref` — nullable, SHA-256 lowercase hex, NULL until `ND-017`. **CLOSED 2026-08-20:** the reconstructed artifact was delivered and independently checked — field names, order, algorithm and canonical form all match, self-test 20/20, both shipped manifests validate, verify and re-derive. |
| E9 A3 idempotency | Obligation mechanism (see A3 row). Ruled early; unblocks `ND-008` design. |

### Resolved by Responses 003 and 004 (2026-08-20)

| Was | Ruling |
|---|---|
| E10 received-vs-canonical | **Delivery's two-discipline hybrid is final** (R004 supersedes R003 §E10.1). Received data — `params_json`, `payload_json` — is **frozen verbatim at ingress and never re-serialized**; the `parse→json.dumps(default=str)` round trip is abolished. Generated structures are canonicalised (ACJ). In-process binding receives no bytes, so its frozen form is one ACJ serialization at ingress, with row-level provenance distinguishing received-verbatim from PDP-serialized. `received_digest` **dissolves** — the frozen bytes are stored, so the digest is derivable. |
| E10 numbers | **`parse_float=Decimal` at ingress — confirmed.** Nothing on the evaluation path becomes an IEEE double. Applies to **policy YAML loading too**, or bounds compare Decimal against float and the door reopens. Duplicate keys / NaN / Infinity / non-UTF-8 ⇒ deny `malformed`. |
| E10 ACJ | `-02` names **AADP Canonical JSON**. Deliberately **not** RFC 8785 — JCS canonicalises numbers through IEEE-754 doubles, the exact step E8 exists to prevent. |
| E11 | Safety finding endorsed; core owns the bad premise. **Sequencing alarm inverted:** `obligations` on the decide response, `not_attempted` in the outcome enum, and payload-carried discharge evidence are **already normative in `-00`** — so E9 added zero wire vocabulary and the `0.4.0` catch-up is conformance, not a break. **One breaking increment stands.** `ND-038`, the `ND-008` resize and re-blocking `ND-037` all endorsed; B3 amended to "checkable once `ND-038` exists". |
| E12 / E13 | **Assent. Core verified delivery's patch independently** (separate RFC 6962 reference, n=1..40, five forgery classes) and integrated it — `canonical.py` in artifact v2 *is* the fix, with `inclusion_proof` / `verify_inclusion`. Sidecar patch retired. `-02` item 18: anchoring is normatively RFC 6962-style. |
| E14 | **ACJ v2 removes Unicode normalisation from the preimage entirely** — strings hash as their code points, producers SHOULD emit NFC, keys sort by code point. The residue is recorded: `unicode_version` is a REQUIRED manifest field with diagnosable verify, because instruments may still consult the UCD. |
| Minors 1–4 | Fixed in v2; #4 graduated to a rule — **a preimage definition MUST pin one representation per field**. |

### Resolved by Response 005 (2026-08-20)

| Was | Ruling |
|---|---|
| Reservation disposition per outcome | **Delivery's table confirmed.** `success` → settle · `failure` → settle · `timeout` → settle · **`not_attempted` → RELEASE.** Settle-on-doubt; release only on a positive assertion of non-occurrence. **The release is an AUDITED event**, symmetric with reclamation expiry (`append_expiry`), never a silent adjustment. `-02` item 21. |
| Threat model | Sharpened by core: the report is *already* the trusted record of outcome — a PEP filing a false `not_attempted` could equally file a false `failure` today. Disposition follows the PEP's assertion because everything downstream of the act already does; the audit's job is to make the lie **attributable**, not to prevent a trusted reporter from lying. |
| `/v1/report` `outcome` field | **Already normative wire** (§reportreq) — same pattern as E11. `ND-039` is conformance catch-up, not a break. |
| Dark-surface clause 0 | **Adopted as delivery wrote it:** report-path completeness before any obligation is attached. A4b/2b is the proof of why. |
| NFC residual | Graduated to a checklist rule, paired with minor 4: a preimage definition MUST pin **one representation per field** (numbers) **and** the **normal form, or verbatim-ness, of every string field**. |

**Artifact verified independently by delivery at both v2 and v3.** v2: 30/30 self-test;
core's `canonical.py` and delivery's separately-written RFC 6962 patch produce identical
roots and identical inclusion proofs for n = 0..40, each verifying the other's proofs.
v3: `canonical.py` and `instruments.py` **byte-identical to v2** (so the vendoring and the
mutual-verification result are untouched); the nested-`additionalProperties` fix
confirmed; validator↔schema agreement re-probed across nine mutations including type
errors; the `verdict` object confirmed still open (no over-strict descent); and the UCD
diagnostic confirmed correctly conditioned in both directions. `reference/rederivable-manifest/`
is pinned to **v3**.

### Resolved by Response 007 (2026-08-21)

Note the direction: 007 rules on a finding that originated in **delivery**, not on an
escalated question. Nothing was gated on it.

| Was | Ruling |
|---|---|
| Anchoring a root over unverified bytes | **New normative rule, `-02` change item 22, adopted from delivery's `.gitattributes` reproduction.** *Anchor only what you have re-verified:* before computing and publishing an anchor root, an implementation **MUST re-verify the receipt set it covers** — chain verification **and** manifest verification over the actual bytes at hand. A root derived from bytes that fail verification **MUST NOT be anchored**; the failure is surfaced, not the root. Hard constraint on `ND-017`, carried into its decomposition; binds the forensics session's P2-05/P3 anchoring too. Generalises past CRLF to any local byte corruption — encoding, disk, partial vendor update. |
| `-text` on the vendored artifact | **Named by core as E10's two-discipline rule at the version-control layer.** The vendored artifact is *received* data — core's bytes, frozen verbatim, never normalised, exactly as `params_json`/`payload_json` are frozen at ingress; delivery's own source is *generated* and normalises to LF. Recorded in the `.gitattributes` header so the rule is not "tidied" into `text eol=lf` later. |
| Diagnosability of a byte-corruption failure | **Endorsed as the pattern.** A byte-level assertion that fires first and names the cause (`.gitattributes` + `core.autocrlf`) is the same discipline as the `unicode_version` mismatch message — it matters twice over here, because the raw failure (`e_digest mismatch`) *reads as compromise*. |
| Delivery's two self-corrections | **Both endorsed, no action.** Checking the policy content-hash claim before publishing it, and the amend-on-wrong-commit recovery verified by blob-SHA identity. Ledger arithmetic is delivery's; no core interest beyond consistency. |

### Resolved by Response 008 (2026-08-21)

| Was | Ruling |
|---|---|
| Relay integrity of core's own rulings | **New protocol, effective immediately.** Every core memo from 008 onward ends with `Integrity: sha256(body) = <hex>` over every byte above the footer line — checked on receipt, so relay corruption is mechanically detectable rather than a judgment call about whether a mojibake sequence "was probably an arrow". Core's framing: *the programme that content-addresses everything else should not have been relaying its own rulings on trust.* Relay-side fix is Shamik's — memos move as downloaded files, never through a copy-paste or open-and-save. |
| Delivery's handling of the corrupted 007 | **Endorsed as the protocol for lossy corruption:** repair by context, mark as repaired, escalate for originals. Vindicated concretely — the re-issue arrived damaged too, and the footer digest then *proved* delivery's reconstruction byte-identical to core's original. |
| §6 residue pointer | **Core's error, owned.** Response 006 said §5; the §5 items were already gone and the live residue was §6's `Open (E10)` bullet. Delivery's find. |
| Anchor-hygiene placement, and both judgment calls | **Endorsed without reservation** — decomposition-line placement, refusing to commit a header asserting SHAs that exist nowhere, and re-prioritising the ledger into git ahead of the patch sequence (urgency-ordering by failure-mode severity over ticket order is delivery's call to make). |

### Resolved by Response 009 (2026-08-21) — delivery + forensics

| Was | Ruling |
|---|---|
| The integrity preimage | **Ratified, then amended — and the amendment superseded by R010.** `body` = every byte strictly before the line beginning `Integrity:`, all trailing whitespace stripped, plus exactly one LF, UTF-8; SHA-256, lowercase hex; the blank separator line is **not** in the preimage. The FINAL amendment is delivery's parsing trap made normative — a memo quoting its own footer format defeats a first-match parser. Core owns the original ambiguity: the footer shipped **unverifiable by construction**, the third instance of the ambiguous-preimage class after E8 decimals and Q-11 uids. All existing digests remain valid. |
| Sidecar vs footnote | **Ratified; core's instruction was self-contradictory and delivery was right to refuse it.** The integrity footer makes archived memos immutable — a feature. Provenance and archive annotations live in a sidecar (`INTEGRITY.md`), never in the memo file. |
| Linter as a byte-rewriting tool | **Adopted for both sessions, normative.** Formatters, linters and auto-fixers MUST be excluded from every received-data path — vendored artifact, memo archive, and any verbatim evidence quotation. Core's framing: *the corruption vector is helpfulness*, which is why it is fenced structurally rather than by advice. |
| Memo archive in `.gitattributes` | **Cross-session finding from forensics, actioned.** `docs/from_core/` was under `* text=auto eol=lf` while `reference/` and `patches/` were fenced. Now `-text`. General rule: *the moment an artifact carries a digest, every layer between delivery and verification joins its trust path — version control included.* Core memos are **received data under E10**. |
| The push | **Authorised.** Gates verified from a cold clone with hostile settings; the 3.13 caveat accepted as an honestly-labelled expectation. Watch both matrix jobs; fix forward if 3.13 goes red. |

### Resolved by Response 010 (2026-08-21, Core→Forensics, forwarded)

**Received unverified — see `docs/from_core/unverified/`.** The ruling below was
implemented on the relay operator's independent instruction; the memo's bytes are not
certified and originals are requested.

| Was | Ruling |
|---|---|
| Two lines beginning `Integrity:` | **R009's final-line anchoring is SUPERSEDED.** Exactly one line may begin with `Integrity:` (producer obligation; quotations indented or mid-line). A verifier seeing more than one **MUST reject the file as malformed**. Core issued two incompatible rules within hours — delivery's anchor-on-final and forensics' raise-on-duplicate — which is the **E005 defect class reproduced inside the memo protocol**: a file "verified" by one checker and invalid to another. The stricter behaviour wins, grounded in ACJ's duplicate-key rule: `malformed`, never last-one-wins. |
| Three-outcome verifier rule | **Adopted programme-wide, from delivery's false-pass finding.** *Absent*, *unverifiable* and *failed* must never collapse; unverifiable and malformed are failures to **surface**, never skips. |
| Gate-verbatim rule | **Adopted programme-wide, from delivery's CI error.** A verification claim about a gate MUST be produced by that gate's **own commands, verbatim**. Binds both sessions' cold-clone claims and core's own artifact self-test claims equally. |
| "Hiding behind a redder failure" | **In the record (R010 §1).** A gate that has never fired is indistinguishable from a gate that passes, until the failures ahead of it clear. |
| Reconstruction is a candidate, not a recovery | **Delivery finding, 2026-08-21.** The one memo that could not be verified turned out to differ in a single character — `⇒` (U+21D2) read as `—`. The brute-force search missed it because the candidate set was **hand-picked** from characters previous memos happened to contain, while U+2000–U+21FF alone holds 512 that collapse identically; `⇒` was meanwhile in use five times in `CONFORMANCE.md` itself. Discipline 4 (generated inputs, not spot-checks) applies to recovery searches, not only to property tests. |
| Producer obligation on marker lines | **From Forward 002, actioned.** Quoting a protocol inside a document that speaks the protocol is how a file becomes malformed. Delivery quotes the footer convention in eight places, all mid-line — now held by a test rather than by luck. |

### Resolved by Responses 012 and 013 (2026-08-21)

| Was | Ruling |
|---|---|
| Digests in a ledger | **R012, adopted; delivery had the defect.** *A digest in a ledger is generated, never transcribed* — any recorded digest MUST be emitted into its cell by the verifier that computes it. **The two registers must never mix:** the `Integrity:` **body digest** is a memo's recorded identity; a **whole-file** hash is an ephemeral transfer aid, used to prove a copy and then discarded, never written into a ledger. `docs/from_core/INTEGRITY.md` now carries one generated register (`scripts/verify_memo.py --table`), guarded by two tests. |
| `ND-040` reason code | **R013: `malformed`, and no new vocabulary.** A URL parameter is *received* data; a string the canonicalizer cannot parse is malformed received data, and E10 already routes unparseable received structures there. **Canonicalize first; on canonicalization failure deny with `malformed`** — a parse differential is a denial, never a bypass. **Condition:** the evidence records the canonicalization failure *distinctly* (an evidence field, not a wire code), so audit can separate malformed-JSON from malformed-URL without expanding the vocabulary. `sender_mismatch` stays the only new code in `aadp/0.2`. `-02` change list item 23. **Verified against the code:** `CheckId.MALFORMED` already exists and is already emitted, so this costs onedoor no new code either. |
| §implstatus draft (a)–(c) | **Accuracy-checked against the source at `v0.3.6`, not against memory** — see `escalations/ACCURACY-CHECK-implstatus-2026-08-21.md`. All three blocks accurate as drafted. Two clarifications proposed, neither a correction: (c)'s "no behaviour change" is true *for policies* but the LiteLLM adapter's reporting moment does move by design; and (b)'s closing sentence generalises `not_attempted`'s **release** to all four outcomes, where R005 ruled settle for `success`/`failure`/`timeout`. |
| `ND-047` | **Parked (R012), constraint kept** — the pruned-prefix/chain interaction is item-22-adjacent on core's watch. |

### Resolved by Response 014 and Forward 003 (2026-08-21)

| Was | Ruling |
|---|---|
| Memo preimage: "trailing whitespace" | **Forward 003 §1: trailing ASCII whitespace, byte-level** (` 	

`). Text-semantics stripping never enters a preimage — a body ending in U+00A0 would digest differently across Unicode versions (the E14 reasoning). **Delivery conformed already**, because the preimage is computed over `bytes`; verified with a probe that first asserts `str.rstrip()` *would* have differed, so it cannot pass vacuously. |
| Memo preimage: end of file | **Forward 003 §2 + R014 §3: the file ends at the footer line with at most ONE terminating LF; a missing final LF is tolerated; any byte after that LF — whitespace included — is malformed.** **Delivery diverged twice, permissively** (an extra LF or a bare CR verified green) and once *strictly* (the first fix required the LF). Both corrected; 8 cases regression-tested. Archive unaffected throughout. See `escalations/ESCALATION-2026-08-21-006.md`. |
| Escalate-and-apply | **Ratified as the general test (R014 §2).** Fix-forward *with* a simultaneous escalation is correct when **(a)** core's text already rules the direction, **(b)** the rule is binding rather than advisory, and **(c)** no archived item changes verdict. If any of the three fails, **hold**. The prohibition was on silence, never on action. |
| §implstatus (a)–(c) | **Accepted and LOCKED**, with both of delivery's clarifications adopted — 2.1 (the adapter's reporting moment moves, by design) and 2.2 verbatim (release *only* on a positive assertion of non-occurrence). Enters the `-02` working copy. |
| Diagnosability | **"A property asserted per-branch dies at the next branch"** joins the record beside the outcome-not-proxy sentence — the same lesson from opposite sides. |

### Resolved by Response 015 (2026-08-21)

| Was | Ruling |
|---|---|
| `0.4.0` | **GO, in delivery's proposed order.** `ND-002` → `ND-003` → `ND-039` as one breaking increment, migration `0007`, **decomposition written before the code**, migration shape and ACJ renderer property tests leading — `ND-002`'s row format is the substrate the other two stand on. No core sign-off on the decomposition unless it surfaces a question. Decomposition: `TICKETS-0.4.0.md`. |
| Three constraints to cite | **E8 at the renderer** — shortest-exact, wire = storage = preimage, and the property tests assert the **tripartite equality**, not each leg separately. **R005 at the outcome** — settle on `success`/`failure`/`timeout`, release only on `not_attempted` as an audited event; settle-on-doubt is the invariant. **E11 at the envelope** — NULL receipt fields are *dark surface*, declared and governed from day one, and **a NULL meaning "not yet produced" must be distinguishable from one meaning "produced empty"**, now programme-wide in both directions. |
| The double-miss | **Recorded, credited to this channel:** *tightening is not automatically conforming; a fix that overshoots is still a divergence.* With the honest mechanics — the permissive direction was tested thoroughly and the strict one not at all — and core's note that finding it on the other channel is why the programme runs two implementations of what it cares about. |

### Resolved by Responses 016–023 (2026-08-21/22) — the `0.4.0` arc

| Was | Ruling |
|---|---|
| Genesis `prev_hash` | **R016: the 64-zero sentinel** — an affirmative in-band statement that no predecessor exists, leaving NULL exactly one meaning. A `chain_state` column was refused as a second answer to a question `prev_hash` already answers (X-14); an id in a hash-typed field was refused as a kind violation. `-02` item 24. |
| S2 (float bounds) | **R017: disclose against `≤0.3.6`, no `0.3.7`.** Magnitude supports a scheduled fix, the complete fix is W3, and a rushed backport is where a fix half-lands. Closed in `0.4.0`. |
| S3 (`str(Decimal)` storage) | **Closed as assessed** — confined to stored text; four independent lines, structural then empirical, ending on the real engine at the exact boundary. |
| `ND-040` reason code | **R013: `malformed`, no new vocabulary**, with the canonicalization failure recorded *distinctly in evidence*. `-02` item 23. Verified: `CheckId.MALFORMED` already existed and was already emitted. |
| Policy-hash attributability | **R019: record the canonicalisation beside the hash.** Migration `0008`'s `snapshot_schema` — "renderer changed, rules did not" must be readable from the record, not from memory of when the upgrade happened. |
| Suite runtime | **R020: ticket and diagnose before ship.** `ND-049`: measured, classified environmental-not-algorithmic, accepted with the AV hypothesis named as **unconfirmed**, revisit trigger = CI movement. |
| `0.4.0` | **Shipped 2026-08-22.** A4 and A4b move to met; `tests/guardrail/test_report_outcome.py` is §implstatus's citable evidence, one test per clause of the disclosure sentence. |

### Resolved by Responses 024–026 (2026-08-22) — the `ND-040` arc

| Was | Ruling |
|---|---|
| `ND-040` scope | **R024: decompose first**; the canonicalizer is **deterministic and dependency-pinned**, and the benchmark's three URL-shaped cases are the acceptance tests, `0/3 → 3/3`, with `ND-048`'s case **asserted still-failing**. Decomposition found the three evasive cases are three *different* problems: canonicalization alone closes one. |
| The opaque-host class | **R025: `ND-040` owns it, as U4** — the published scope binds the way the published schedule does. A **declared, versioned class**, starter list plus customer extension, matched **post-canonicalization by exact host**, **failing closed for members only** so the innocents column stays 3/3, the undeclared-shortener limitation **disclosed in the same breath as the fix**, and **no new wire vocabulary**. Delivered as: a member is treated as though it were the declared target, so the code is the existing `effect_floor` and the class rides in evidence (`opaque_class`, migration `0011`). |
| U2's acceptance | **R026: a corpus-style assertion** that every existing policy's matches and non-matches are unchanged with the feature present but unused. `tests/guardrail/test_param_effects_compat.py` uses the original expression as oracle and reads the engine's answer through `decide_and_reserve`, not a helper. |
| The disclosure's mechanism sentence | **Corrected in the same arc (R025).** `0.4.0` said canonicalization would close the three URL-shaped evasions; it closes one. CIDR matching closes the second **given a deployer who can declare the network**, and the shortener is not a canonicalization problem at all. The promise stands; the description now matches what was built. |

### Resolved by Response 027 (2026-08-22) — the three departures, and the ship

| Was | Ruling |
|---|---|
| U4's `effect_floor` reading | **R027 §1: CONFIRMED, and it improves on R025's own wording.** *Fail-closed means never silently execute, not always refuse.* An action whose consequences cannot be **verified** must not be auto-executed — which is not the same as saying it can never happen. Routing members onto the effect floor keeps the guarantee that matters and lets policy grant an approver the call, rather than over-blocking wearing a safety argument. Three conditions: the never-auto-execute **invariant asserted as a test**; evidence naming **both the class and the reason**; the semantics stated in **one plain sentence** in the docs. |
| U2+U3 landing together | **R027 §2: accepted as reported** — "not separable" honestly stated beats a green sequence that was briefly red in the middle. |
| The unaudited envelope-`malformed` denial | **R027 §2: `ND-050`**, recorded as pre-existing in `≤0.4.0` and backlogged with a severity note. Does not block `0.4.1`. |
| `0.4.1` | **R027 §3: ship**, standing release rule. **Published 2026-08-22**, tag `v0.4.1` @ `7e9fd07`. |
| `0.6.1` | **The first operator validation's findings** (F-A/C/D/E). **Published 2026-08-27**, tag `v0.6.1` @ `9f026cc`. Verified: four sources agree on both digests and sizes — the handover's **pre-upload** record, PyPI's index API, core's independent fetch, and `dist/`; the annotated tag dereferences to `9f026cc`; both GitHub assets byte-identical to `dist/`. Core additionally confirmed **F-A from public bytes** — `GET /` 200 across eight sequential requests over a real socket, against the store that returned 500 that morning. |
| `0.6.0` | **R054 §4: cut it before launch week.** **Published 2026-08-27**, tag `v0.6.0` @ `0df3afd`. Verified: four independent sources agree on both digests — the handover's **pre-upload** record, PyPI's index API, core's independent fetch, and `dist/` — and the equality is meaningful *because* the record predates the upload: **the build is not byte-reproducible** (measured). The GitHub assets and the PyPI-served wheel are byte-identical to `dist/`. |
| `0.5.0` | **R048 §3: cut it before S4** — the crypto epic is the launch's proof pillar and was sitting unreleased. Additive; Studio behind `[studio]` with S4–S6 named as not included. **Published 2026-08-24**, tag `v0.5.0` @ `fef596e`. Publication verified: PyPI's own recorded `sha256` equals the pre-upload digests for both artifacts, and the GitHub assets are byte-identical to `dist/`. |

**R027 §1's first condition found a defect rather than confirming a property.** U4
rested on the effect floor, and the effect floor is optional: a policy could declare
`opaque` and attach an effect with `min_tier: null`, and the declared redirector would
auto-execute silently. Constructed and observed before release, so it never shipped.
The invariant is now stated in the engine — an opaque-class member floors to the
human-approval tier whatever the action's tier and whatever the effect declares — and
asserted across eight policy shapes crossed with the kill switch. **The general
lesson: a protection that depends on a second, optional declaration is not a
protection, it is a default.**

### Resolved by Responses 028–029 (2026-08-22) — Phase B

| Was | Ruling |
|---|---|
| §4's question (does core's text need the correction?) | **R028 §2: yes.** `-02` change-list item 23 and the §implstatus prose both take the CHANGELOG's three-mechanism sentence. **Core owns both edits; nothing for delivery to touch.** Delivery's line is adopted as the rule for such texts: *the promise stands; the description of how it is kept must be true.* |
| The `ND-040`/U4 lesson | **R028 §1: adopted as a programme rule, in delivery's words** — *a protection that depends on a second, optional declaration is not a protection, it is a default.* The eight-shapes × kill-switch matrix, with the symmetric guard that an invariant blocking *approved* actions would be a refusal wearing a safety argument, is named the reference shape for invariant testing. |
| `ND-050` | **R028 §3: severity accepted as stated.** Backlogged unscheduled; when it runs, **the row-shape question comes to core before the migration, not after**. |
| The Phase-B viewer | **R028 §4: build it, viewer first**, then the crypto epic. `ND-051`; spec and mockup in `docs/oneview/`. |
| The Policy Studio | **R029: ticket as an epic**, `ND-052`, sequenced after the crypto epic, **no code before launch**. §2's constitution binds every sub-ticket; §5 makes principle violations **CI failures, not review notes**. |

### Resolved by Response 030 (2026-08-22)

| Was | Ruling |
|---|---|
| `ND-051` | **Accepted.** Non-ownership enforced by **AST** is named the **new reference for the single-verification rule** — stronger than import discipline because it is guarded structurally rather than by review. Four outcomes in the UI, with `unverifiable` as loud as `failed`, is the three-outcome rule rendered where a human meets it. |
| The unfootered artifact | **R030 §2: ABSENT — no integrity claim.** Never rejected (that punishes the archive for being honest about its history), never blended with `unverifiable` (that invents a claim nobody made). Three states, three meanings: absent is no claim, unverifiable is a claim that cannot be checked, damaged is a claim that checked false. |
| Which register holds a computed digest | **R030 §2: the register holds PRODUCER CLAIMS; the sidecar holds OBSERVATIONS.** A present-tense digest of an unsigned artifact is an observation — dated, in `INTEGRITY.md`, in the declared form `observed sha256 <hex>, <date>` — never in the protocol register, whose one meaning is *the producer sealed this*. |
| The chain block's label | **R030 §3: "not yet in operation", never "not yet produced"** — so absent-by-schedule is never readable as broken. |
| The crypto epic | **R030 §4: GO.** `ND-001` decomposition first, `ND-010` behind it, `ND-009` in parallel. |

### Resolved by Response 031 (2026-08-22) — the preimage

| Was | Ruling |
|---|---|
| C1's absent-versus-empty encoding | **R031 §1: length-prefixing, with the encoding fully determined.** Absent is a **type tag, never a zero-length string** — NULL and `""` must produce different preimage bytes. Field order declared once with golden vectors (shift collision, absent-vs-empty, delimiter bytes, one-byte perturbation). **E10 at the boundary:** the preimage seals what the row holds and performs no normalisation of its own. Delivery's reasoning — *`params_json` is received data and a caller may be actively trying to collide two rows* — is named as why this gets adversarial rigor. |
| C2–C5 | **R031 §2: GO**, and holding the writer until its bytes were defined is confirmed as the right read. `verify_chain()` holds a broken link, an absent chain and an unverifiable row apart as **three verdicts, not one**. |

**Delivery note on §1.2, reported rather than glossed:** the memo directs delivery to
follow *"the vendored artifact's uid-preimage convention"*. **`reference/rederivable-manifest/`
carries no length-prefix dialect** — no `struct`, no `to_bytes`, no packing anywhere in
it, checked rather than assumed; its six frozen rules cover decimals, datetimes,
strings, JSON, digests and RFC 6962. So the extension is the whole encoding, written
down in `docs/row-preimage.md` §1 under R031's own *"extend it explicitly and write the
extension down"*, and built on the one byte-level discipline the artifact does ratify —
rule 6's domain-separation tags. Saying so beats quietly implying a dialect was
followed.

### Resolved by Response 032 (2026-08-22)

| Was | Ruling |
|---|---|
| `ND-001` | **Accepted.** Opt-in and off by default is named the right rollout shape for a feature whose rows are permanent: nothing in production grows a chain until a deployer declares it, and the genesis sentinel meets its first real store on the deployer's terms. |
| The dialect | **R032 §2** names it as the vendored `rederivable-manifest` v3 uid-preimage convention, read from `onedoor/_vendor`. **Delivery escalated (008): that convention is not in the artifact** — evidence in the memo. The executable half is done: one dialect, documented in `docs/row-preimage.md`, adopted by citation. |
| `docs/row-preimage.md` | **Ratified as the SINGLE NORMATIVE SOURCE.** `ND-015` and `ND-017` **cite it and never re-derive** — X-14 at the preimage, guarded by an AST test rather than promised. |
| `ND-010` / `ND-009` | **R032 §3: GO.** The rebuild carries provenance to the rows it derives from and surfaces gaps rather than synthesising intents. |

### Resolved by Response 033 (2026-08-22)

| Was | Ruling |
|---|---|
| Escalation 008 | **SUSTAINED IN FULL.** R032 §2's *"read from the vendored files"* was **false** and core owns it: the dialect lives in the **Provenance Primitives Spec v1.1 §1 (Q-11)**, a forensics-repo document onedoor does not carry. *"Refusing to write a provenance you could not verify was exactly right"* — X-13 applied against core, sustained. |
| The dialect | **`len8`** — the byte length as an 8-byte big-endian integer — quoted **verbatim** in `docs/row-preimage.md` §1 so the citation carries its own checkable content and cannot rot into a pointer at nothing. **No bytes moved:** the draft written under the broken pointer already used 8-byte big-endian, verified by re-running the golden vectors before and after the edit. The ABSENT/PRESENT tags are declared as onedoor's **extension** — the spec's uid preimage has no absent case — and are adopted as programme vocabulary. |
| `ND-010` §7 | **R033 §3: a rebuilt row's `created_at` is its own write time, never backdated.** The ledger records when it *learned* a thing; lineage travels by reference; a rebuilt record never impersonates a live one. Same discipline as R030's register/sidecar split. |
| `ND-010` R1–R5, `ND-009` | **GO.** |

### Resolved by Response 034 (2026-08-22)

| Was | Ruling |
|---|---|
| `ND-010` | **Accepted as standing.** The rebuild forced no new question because its questions were asked at decomposition — *the decompose-first method working as intended, twice in one epic*. The rebuilt-record discipline (distinct type, own write time, lineage by reference) enters the record as the recovery-time shape. |
| `ND-009` | **GO**, against settled semantics: single-use; an invalid or replayed ref **evaluates as if absent**, never an error path that leaks whether a ref existed; the **kill switch wins**; refs are **principal-scoped**; binding is **action-equivalence**, not a byte-identical request; `approval_ref_status` writes the seven-value evidence field. Where resumption meets `ND-010`'s rebuilt state, the E10 label discipline applies unchanged. |

### Resolved by Responses 035–036 (2026-08-22)

| Was | Ruling |
|---|---|
| `ND-009` Q1 — preimage bump | **R035 §1: YES, `/2`, once, now** — `approval_ref_status` hashed. `sig`/`key_id`/`alg` and `anchor_ref` confirmed **excluded** for stated reasons; `ND-050` deliberately **not** pre-folded. `/2` also adds an **excluded, self-authenticating `preimage_version` hint** so `verify_chain` can walk version transitions **on live chains** — which makes today's bump **the last one that needed the everything-off window**. |
| `ND-009` Q2 — the principal | **R035 §2: delivery's proposal adopted whole.** `principal_mismatch` **reserved and never emitted**, `sender_mismatch` pattern, until `ND-004`/`ND-005` provide an authenticated identity. Delivery's sentence enters the record: *"a control in `CONFORMANCE.md` that does not control anything."* Core notes the draft's principal-scoped clause stays normative while onedoor's row reads **partial**. |
| `ND-009` Q3 — action-equivalence | **R035 §3: identity up to spelling** — same `action_type` **and** params equal under the canonical rendering, evaluated on the frozen received bytes' parse. Effect-set equality is asserted as **derived consistency, never the test**: it alone would let "approve €250 to X" be spent on €900. Goes to the `-02` change list as item 25. |
| `ND-052` sequencing | **R036: re-sequenced by Shamik's decision**, recorded as a principal's call. The Studio becomes a **pre-launch, demo-grade epic** opening the day `ND-017` closes, superseding the design note's *after the epic* line. Constitution unchanged. **Build order normative:** S1 backtest → S2 ratification → S3 canvas → S4 coverage map → S5 finance pack → **S6 the LLM proposer last**. **Two gates:** the Studio never gates the launch, and S6 demos only real, receipted, limit-stated output. |

**A6 note (partial → still partial, stated):** onedoor's row for the draft's
principal-scoped clause reads **partial** until an authenticated identity exists. The
value is in the vocabulary and held unemitted by a test; the check is disclosed as
awaiting `ND-004`/`ND-005` rather than implied to exist.

### Resolved by Response 037 (2026-08-22)

| Was | Ruling |
|---|---|
| `ND-009` | **Accepted**, both required tests in — the version-boundary chain walk alongside the DoD concurrency test. Delivery's reading confirmed: **the version hint mattered more than the column it shipped beside** — `/3` is now an ordinary migration, and the epic's remaining tickets inherit a settled, guarded preimage rather than a window. |
| `ND-015` custody | **Pre-settled by R037 §2**, so the decomposition relitigates none of it: private key **deployer-supplied**, never in repo/DB/receipt; **`key_id` derived** as a fingerprint of the public key, never assigned; an **unknown key is `unverifiable`** — never `failed`, never trusted; **rotation append-only** with a growing keyring, because public keys are evidence; signing **per-row over `row_hash`** under the standing AST guard. |

### Resolved by Response 038 (2026-08-22)

| Was | Ruling |
|---|---|
| Q1 — self-verification | **RULED: a store never says `verified` on its own.** Verification requires a trust anchor **from outside the store**; the in-store match gets its own honest name, **`self_consistent`** — *"signature matches this store's own keyring; supply a trusted key to verify"* — displayed as exactly that and never dressed as verified. Signature outcomes are therefore five: `verified` · `self_consistent` · `unverifiable` · `failed` · `absent`. Delivery's discomfort is named as the product's thesis in miniature: **a receipt system must not be its own witness.** |
| Q2 — X-6 | **RULED: a `[signed]` extra, with X-6 enforced at ENABLE time, not install time.** A hard install dependency guarantees nothing about config, and belief comes from config — so **signing configured + library missing = the process refuses to start**, asserted as a stated invariant. |
| Q3 — `alg` | **RULED: algorithm only.** Ed25519 is output-deterministic (RFC 8032), so a library version in per-row evidence would assert a dependence that does not exist. The pattern is resolved rather than suffered: **implementations are recorded where they can change outputs** — `canon_schema` and `unicode_version` exist because theirs do. The library and its pin are recorded once at the deployment layer. Semantics in the receipt, process provenance in the register. |
| `ND-017`'s anchor | **PRE-RULED (§4): an anchor is worth exactly the independence of where it lives.** A root stored beside its leaves proves internal consistency, nothing more — Q1's shape one level up. `ND-017` designs the export path; venue and cadence are its questions, X-8 unchanged underneath. Its decomposition cites this rather than re-deriving the discomfort. |

### Resolved by Response 039 (2026-08-22)

| Was | Ruling |
|---|---|
| `ND-015` | **Accepted.** The adversarial demonstration is named the acceptance done right — *"that gap is the product"* joins the record, demonstrated rather than asserted. So does the viewer reasoning: **a reader takes the tick and leaves the sentence** — UI truth-design in nine words, binding all three skins. The X-6 invariant catching its own subject's unguarded import is the enable-time ruling earning its keep inside its own ticket. |
| `ND-017` | **GO, with the frame set.** The four `E`/`I`/`T`/`v` preimages come to core **written to Q-11 rigor** (fields named, `len8` where concatenation appears, golden vectors) for sign-off **before bytes freeze**. The export path is designed to §4's independence metric, and the acceptance shape is the **third-party membership check**: a published root plus one receipt, nothing else of ours. |

### Resolved by Response 040 (2026-08-22) — the epic's last rulings

| Was | Ruling |
|---|---|
| `E` and `v` | **Signed off as proposed.** Params as a digest of the frozen bytes is E10 and privacy in one move. The no-`len8` statement accepted as the honest reading — a canonical object needs no framing, and saying so beats decorating with an unused dialect. |
| `T` | **AMENDED: drop `policy_source`.** The policy hash lives in `E` as an *input identity*; carrying it twice is **X-14 inside the seal itself**. `T` = `kind` + `keys` + `closure` — a statement of what must be **trusted**, never a second copy of facts `E` already seals. |
| `I` | **AMENDED: `anchor_cadence` comes OUT.** Delivery's flag was right and the consequence *was* the defect: cadence schedules anchoring, not deciding, and inside `I` an ops-schedule tweak would split `i_digest` cohorts for a reason no instrument comparison should care about. Cadence declares in the anchoring config and records on the anchor object. |
| A store-found root | **CONFIRMED `self_consistent`**, and the pattern gets its single plain statement: **"onedoor never vouches for itself: at the key layer and the anchor layer alike, `verified` requires something the store does not hold."** |

### Resolved by Responses 041–042 (2026-08-23)

| Was | Ruling |
|---|---|
| `ND-017` M4 | **R041: one late acceptance requirement**, landed as **F1**. The degenerate empty-path inclusion proof is accepted only at `tree_size == 1` and `index == 0`, refused **before any Merkle computation** otherwise, with two sabotage vectors and one positive size-1 vector. *A verifier must refuse the degenerate case before it computes, because the degenerate case is the one that computes to true.* Credit to `draft-schrock-ep-authorization-receipts-12` §7.3. **The epic stays closed.** |
| The epic | **R042 §1: accepted as reported.** Two documents with second implementations built from text rather than code is named the epic's real yield. The closing sentence is **ratified as a product line**: *onedoor never vouches for itself — at the key layer and the anchor layer alike, `verified` requires something the store does not hold.* |
| S1 Q1 — what a backtest writes | **R042 §3: nothing to the decision ledger. Ever.** Not a decision row, not a marker, not a breadcrumb. It **borrows the ledger's witness** — a backtest receipt that cites the sealed chain — so *a backtest proves it saw real data by citation, not by writing; the ledger vouches for the backtest, never the reverse.* |
| S1 Q2 — the empty store | **R042 §4: a hashed `ledger_provenance: live \| fixture`**, with a shipped fixture ledger that is mechanically real and declares itself synthetic. The label must survive into every rendering — a fixture-backed number without it is the overclaim this programme exists to make impossible. |

### Resolved by Response 043 (2026-08-23) — S1's three

| Was | Ruling |
|---|---|
| Q1 `cost_eur` | **Sustained**, with a law attached: **measured zero and declared zero never share a representation.** A `0.00` resolved through the candidate's `cost_param` is a *measurement*; an action whose candidate declares no `cost_param` is a *non-measurement*, counted under its own reason. The candidate's `cost_param` applies even where it differs from the policy in force when the row was sealed — the backtest's question is what the **candidate** would have done. |
| Q2 provenance | **Sustained: two labels, no third.** `ledger_provenance` describes the **cited range**, not the store; an unchained prefix is a counted skip. **Plus one ruling not asked for:** a store with **no chain at all** gets a **refusal, not a receipt** — `row_hash_at_last_seq` is REQUIRED, and a null citation would be the store vouching for itself. The refusal names the remedy. |
| Q3 the fixture | **In the wheel**, deterministic, byte-pinned with a regeneration test, low hundreds of rows, back to the board over ~256 KB. The pinning buys **anti-masquerade**: the fixture's chain head is a published constant, so a receipt citing it while claiming `live` is detectable by anyone. |
| The S2 flag | **Endorsed as stated.** Ratification cites `record_snapshot`'s machinery and never re-derives it; S2's decomposition opens by quoting that as settled. |

### Programme law — a blank is a promise that someone will remember

Ratified by R051 §2 out of S5's decomposition, and it generalises well past templates.

> **A blank is a promise that someone will remember.** A protection whose value arrives
> later is a default with a hole in it, and the hole is the part that ships.

**The second half is the sharper one, and it is why `ND-052`/S5 is shaped as it is:**

> **A template with blanks cannot be checked, because it is not yet the thing the check
> checks.**

`{{daily_cap}}` is not a `Policy`. `validate_policy` cannot refuse it, `coverage.build`
cannot map it, and a pack's own law tests would pass **against an artifact that does not
exist yet** — a green check with nothing behind it, which is *worse than an unchecked
artifact because it carries an assurance.*

Consequence, held by `tests/templates/`: shipped packs are **concrete policies with
fail-closed defaults**, and *adjustable* means editing a real value that was already
safe. Principle 3 read strictly — **the review surface is a number you can see and
change, never a hole you must remember to fill.**

### Programme law — naming honesty, in both directions

Settled across four memos and recorded here once, because it kept arriving as a fresh
discovery: **every name in this system is an assertion, and an assertion that outruns
what is checked is a defect whether or not anything fails.**

| Layer | Ruling |
|---|---|
| **A field's name** | R045 — `ratified_by_session`, not `ratified_by`: the short name reads as an identity claim to every future reader of an export. |
| **A reserved field** | R046 — a reserved *word* is a promise about vocabulary; a reserved *field* is a claim about mechanism. `removed` would have claimed a retirement path the engine lacks. |
| **A test's name** | R048 — *a name that outruns its check is false comfort.* |
| **A check's name** | R050 — *a check that outruns its name is a false alarm.* Both are defects; they differ only in which direction the lie runs. |
| **A computed value's name** | R050 — `exercised_effects` claimed history for a projection. Renamed `would_exercise`; **a rename, not a migration.** |

**The deciding principle, which generalises past all of them:** *when a check and the
artifact it guards conflict, narrow the check to what it always claimed — never degrade
the artifact to satisfy the check.* Rewording documentation to appease a linter lets a
guard erode the thing it guards, which is how a control quietly becomes what it was built
to prevent. A narrowing is done honestly by testing the boundary **from both sides**.

### Programme law — deferred annotations resolve where the module lives, not where the code runs

Registered with its shape (R056 §3), because it is a trap and not a one-off.

`from __future__ import annotations` makes every annotation a **string**. A framework that
resolves those strings — FastAPI does, to build its request model — resolves them against
the **module's** globals. A name imported inside the function that builds the routes is
invisible at resolution time, however plainly it sits in the source.

**Symptom:** `request: Request` read as an unresolvable **query parameter**; every browser
form POST returned `422` *before reaching the handler*, with a message about a missing
query field that names nothing wrong with the request.

**Found:** building `ND-055` P0's create-draft form. **Fix:** the name lives at module
scope behind an import guard, so the annotation resolves where the framework looks. The
X-6 property survives — importing the module still works without the extra, and
`create_app` still refuses with a remedy, because if it did not refuse then the guarded
import already succeeded.

*The next closure-built app should hit this register before it hits the 422.*

### Seal-boundary doctrine — configuration advice is not a verdict

R056 §2, recorded because the line is easy to over-draw in either direction.

- **The semantic pair is reserved for verdicts and states.** Allow/refuse and their kin
  never decorate anything that is not one.
- **Seal gold as a brand frame on an advisory panel is brand usage**, not state signalling.
  §4 forbids gold **carrying** state; it does not forbid gold standing near information.
- **So V8(a)'s strengthened check is scoped accordingly**: it hunts state and verdict
  vocabulary and semantic-class routes *inside the seal region*. It must **not** fire on a
  conditionally-rendered advisory panel — a check that did would outlaw gold anywhere
  dynamic, and **teach people to route around it**, which is worse than the violation.

### Programme law — a summary is a claim about a source

**Check the source before you reason from the claim.**

A summary, a register, a `CONFORMANCE.md` row — each is an *assertion about* a document,
made at a moment, by someone with a purpose. Reasoning from one without opening what it
summarises is trusting a claim you could have checked, and the cost lands where the
summary happened to compress.

| # | Who | What happened |
|---|---|---|
| 1 | **core** | answered a correspondent's §9/§10 questions from principle **without the draft open**, and was called on it. The draft was on the same internet. |
| 2 | **delivery** | argued in `ESCALATION-20260827-006` that AADP was silent on `params` typing, reasoning from **this file's** budget-object line instead of the draft. `-01`'s rule was already unqualified — *monetary values*, full stop. The draft was on the same disk, and delivery opened it an hour later for the Appendix B review. |

Same defect, both parties, **both self-reported after external contact** — which is the
uncomfortable half: neither was caught by reading more carefully, and both needed someone
outside to run into it.

The related failure delivery's instance also shows: **a scope restriction inferred from
where you first met an example of a rule, rather than from the rule's own words.** The
budget object was simply where the decimal-string rule was first seen; nothing in the rule
said it lived there.

**And the escalation channel is what survived it.** A verdict-changing behaviour was
flagged rather than taken, and the proposal reached was the one core ruled for.
*The escalation channel exists to survive bad reads, not to require good ones.*

**The consequence, ratified as a finding rather than a confession.** Two instances, both
parties, **both self-reported only after external contact** is a *measurement of
self-review's limit* — and no amount of additional discipline would have changed either,
because **the defect class is precisely a confident belief about a source that makes
opening the source feel unnecessary.** Care cannot catch it; care is what produced it.

So the response is structural, and it is already built: **the operator on a clean machine,
the correspondents asking cold questions, and the cross-channel relay are not courtesies
around the quality system — they are the part of it that catches what self-review cannot.**
`0.6.1` exists because someone installed `0.6.0` from PyPI and clicked; `-02` §5 says what
it now says because a conforming-looking implementation got it wrong in public. **The
programme buys external contact on purpose**, and should keep doing so — a cold reader is
a perishable asset, and the one thing an internal review can never simulate.

### Programme law — a register that silently loses a row invites the question of what else it lost

Core's Appendix B ruling (2026-08-27), against delivery's own recommendation and recorded because delivery was wrong.

Reviewing `-02`'s Appendix B, delivery proposed **dropping** the idempotency-propagation
row: `-02` had drawn a boundary making it a non-gap, so listing it beside real gaps looked
like inviting a reader to see an unfinished feature. Core ruled it **restated as a
boundary instead**:

> A row that says *"this stopped being a gap because `-02` drew the boundary"* preserves
> the register's history and teaches the reader the boundary in one move.

**This binds every register in this repository**, and there are several: the
migration-number register, the proxy-for-contract table, the substitution class above,
`INTEGRITY.md`'s digest register. A closed entry is **marked closed with its reason**,
never deleted. Deleting is the edit that makes a reader wonder what else went quietly —
and a register's whole value is that a reader does not have to wonder.

### Programme law — an unasserted substitution fails silently in both directions

**The proxy table's sibling** (R052 §2), and the pairing is the point: *the proxy class
trusts a check's stand-in; this class trusts an edit's return.*

> **An unasserted substitution fails silently in both directions — no-op or overreach —
> and in neither direction does the caller find out from the call.**

Delivery's law, ratified in its own words: **a substitution that cannot fail is not an
edit, it is a wish.**

| # | Where | Direction | What it cost |
|---|---|---|---|
| 1 | **core's memo-sealing tooling**, sealing R051 | **overreach** — a bare `DIGEST` placeholder matched *inside* `PACK_DIGEST` and `SPEC_DIGEST` | the memo's own body was corrupted while being sealed; caught by integrity verification, repaired, re-sealed |
| 2 | **delivery's ledger script**, after R050 | **no-op** — two `.replace()` calls whose anchors were absent | `CONFORMANCE.md` went on claiming *"as of Response 048"* long after 050 landed; surfaced only when a later script crashed looking for text it believed it had written |

Same root, opposite failure directions, and neither caller was told. One matched too
much; one matched nothing. Both returned successfully.

**The standing rule: every mechanical edit asserts its own effect** — exactly-one-match
before, changed-content after, or the script fails. A substitution whose return value
carries no information about whether it did anything is not a tool, it is a coin flip
that always reports heads.

### Programme law — proxy-for-contract, and the sixth instance

**A proxy matches whatever else happens to say it.** A check that looks for a stand-in
token rather than the contract itself will be satisfied by anything that stumbles into
the token.

| # | Where | The proxy |
|---|---|---|
| 5 | a monitor filter watching for a `pytest` summary | `passed` — matched ruff's *"All checks passed!"* |
| 6 | **`scripts/gate.py`'s own contract table** | `" passed"` declared as the tests gate's contract — **a substring of the lint gate's output**, so a lint run would have satisfied the test gate |
| 7 | **core's own memo-sealing tooling**, in R051 | a bare `DIGEST` placeholder, replaced by a tool that then matched it **inside `PACK_DIGEST` and `SPEC_DIGEST`** in the body and corrupted both. Caught by integrity verification, repaired, re-sealed |

Instance six is logged as **the most instructive of the six**: it was committed *while
building the tool that exists to prevent the class*, by an author who could name the
class. R050's line for the file: **a class you can name is not a class you have escaped.**
It was caught by that tool's own test on first execution, which is the argument for
putting laws into construction rather than into memory. The fix: contracts are **patterns
requiring a count**, cross-checked against every other gate's real output.

**Instance seven is core's, and it sits in the same table as the rest on purpose.**
The enforcer's own lapses belong in the same rows as everyone else's, or the table
records who gets audited rather than what goes wrong. R051 §1's line covers it —
*nothing here is authoritative because of who wrote it* — and a class table that
exempted its own author would be the clearest counter-example to that.

### Resolved by core's Appendix B ruling (2026-08-27, unnumbered acknowledgment)

| Was | Ruling |
|---|---|
| Gap 1 — structured budget object | **Closed**; replacement text folded into `-02` as supplied. |
| Gap 2 — `approval_ref` | **Split accepted**, for the reason delivery gave: this repo shipped a release where every library test passed while every served page returned 500, so a register blurring engine capability with served-surface exposure would invite the same misreading. `-02` now reads *"the engine exercises it; the remaining gap belongs to the served surface, stated as such."* |
| Gap 3 — sender-constrained permits | **Still open**, delivery's sentence intact: *the vocabulary complete, the mechanism absent, the absence declared.* |
| Gap 4 — idempotency propagation | **Restated as a boundary, not dropped** — delivery's recommendation overruled. See the register law above. |
| The version sentence | **Flips to `0.6.1` on submission day, after publication is verified — not before.** |

### Resolved by Response 062 (2026-08-28) — V6, and the Q8 ruling

| Was | Ruling |
|---|---|
| V6 | **Accepted.** 1104 passed, four gates green, CI green on both jobs. *"Built the way it was argued: on a premise verified where it can fail, not asserted where it can't."* |
| The replay calling the engine | **Law** — see below. The structural assertion *"is the fence that keeps the second implementation from growing back"*, and the control case *"is the calibration every counterfactual borrows its credibility from."* |
| The unretrievable middle row | **The feature's conscience.** *A comparison that could not be made must be unrenderable as a comparison that found nothing.* **Guard its tests jealously.** |
| R061 §5's addition | **Discharged in full.** |
| `assert_reader_sees` | **House practice: a mistake made once is a fix, twice is a pattern, three times is a tool.** *A named tool is also a named thing a reviewer can ask for by name.* |
| **Q8 — the `pytest_terminal_summary` move** | **APPROVED on its own merits, explicitly NOT as a fix.** The matrices are disclosure, not assertion; reporting belongs in the reporting phase, and `capsys.disabled()` mid-test *"was always borrowing the capture machinery against its grain."* Recorded with that as the reason. |
| **Q8 — the flake itself** | **STAYS OPEN.** *Nothing diagnosed can be fixed, and nothing undiagnosed should be recorded as fixed.* **Two closing paths, either honest:** it recurs after the move — which refutes the capsys suspicion and earns a real investigation with the full stash trace captured; **or** some healthy number of consecutive runs pass — closing as *"not observed since the reporting move; cause never established."* **Never a third path where the move gets the credit.** |
| V7 | Proceed. The ND-054 note *"describes what the engine does today — honestly, without hedging toward the future fix and without implementing a character of it."* |

### Programme law — the replay must call the judge, never imitate it

R062 §1. **A hand-written comparison of rules is a second implementation of the verdict,
and two implementations of a verdict disagree the first time anything subtle changes.**

The fence is structural: the module must contain the engine's entry point and must not
contain a tier check, a counter read, or a verdict function of its own — *the fence that
keeps the second implementation from growing back.* The calibration is the control case:
replayed under the deciding version, the engine reproduces the recorded verdict, and
**every counterfactual borrows its credibility from that.**

### Programme law — a suspicion is not a diagnosis

R062 §4. *A mechanism changed on an unreproduced flake treats a suspicion as a diagnosis,
and if the flake then vanishes, you have learned nothing and believe you learned
something.*

So the two questions separate: the change can be right **on its own merits** and still not
be a fix. Record the reason that is actually true, and leave the fault open with its
honest closing paths — **never a path where the change gets credit it did not earn.**

### Programme law — a mistake made once is a fix, twice is a pattern, three times is a tool

R062 §3. The third repetition earns a named assertion, and the naming is half the value:
**a named tool is a named thing a reviewer can ask for by name.**

### Programme law — a gate's worth must be stated honestly, like everything else

R062 §4, adopting delivery's sentence: **a suite that fails once in three runs is a green
gate worth less than it looks.**

### Resolved by Response 061 (2026-08-28) — V5, and core's wrong word

| Was | Ruling |
|---|---|
| V5 | **Accepted.** 1081 passed, four gates green, CI green on both jobs. **Q5 discharged** — *"with the layout ruled in R058 §6, and better than ruled."* |
| The ceremony's spine | **Canon as written: ratification is a GET before it is a POST.** A served test proving that reading the page ratifies nothing *is the whole justification for a ceremony page over a button, stated as an assertion instead of an intention.* |
| **R060 §5's word "irreversibility"** | **Core's defect, registered.** Had the page followed core's word it would have carried *a falsely frightening claim in its most solemn sentence*. Filed on the same shelf as the deny tier and the mockup contrast: **core's language, agent's correction.** |
| The malformed fourth case | Closes a hole the three-outcome doctrine left implicit — **malformed is its own outcome.** *The right-typed lie found in a dataclass, caught by mypy doing its job.* |
| The backtest panel | Ratified. Per-direction flip sentences are correct *because a single count buries the only direction that pages an operator.* |
| Q5's three states | **The finish the ruling lacked.** The page stating that neither voice is derived from or checked against the other is *the two-voice boundary made legible to the reader instead of merely held in the code.* |
| V6 | Proceed. One addition: **the re-evaluation screen names BOTH versions in the same breath and wears the would-have limit sentence.** *A counterfactual that does not name its counterfactual-ness on the screen where it renders is the backtest panel's lie one click deeper.* |

### Programme law — finality is not irreversibility

R061 §2, correcting R060 §5. **The record is permanent, the way back is forward, and a
ceremony that overstates finality is lying in the direction that LOOKS like caution.**

The forbidden-word list held as a test is the right fence, and the reason it matters is
the sting in the ruling: **caution-flavoured lies are the ones nobody audits.** A page
saying "this cannot be undone" would never be challenged for being too careful — which
is exactly why it has to be challenged for being false.

### Programme law — malformed is its own outcome

R061 §3. A state that says the work ran, carrying no result, is neither success nor
refusal. **Zeroes in a malformed result would report a clean run that never happened.**
Found in a dataclass by a type checker, which is a perfectly good place to find one.

### Programme law — prove verbatim in the form the reader receives

R061 §3. A constant containing an apostrophe reaches the page escaped, which is the page
being *correct*. **Asserting only the raw constant makes a correctly-escaped page look
like a paraphrase.** Check both: the escaped form in the markup, and the unescaped
rendering back to the constant character for character.

`tests/viewer/assertions.assert_reader_sees` is that check, written after the mistake
recurred three times — *a recurring mistake earns a named tool.*

### Resolved by Response 060 (2026-08-28) — V4, and the third case

| Was | Ruling |
|---|---|
| V4 | **Accepted.** 1048 passed, four gates green, CI green on both jobs. Q7 closed until the freeze lifts. |
| **The third case** | **Ratified, and it supplies the clause R059 §5's binary did not draw.** The API exists *and the Studio may not use it*. The deeper reason is the first: `set_engaged` through the enforcer connection would falsify R047 §2's sentence, **and that sentence is the two-process design.** |
| Saying what the switch does not stop | **Ratified as a shape**, and generalised — see the law below. Rank read from `decision.py`, **R058 §4 holding its second door.** |
| The budget arithmetic | **Accepted as specced.** *A counter means what the code that increments it means, not what its name suggests* — the same law as R058 §4, now proven on arithmetic. The pinned-snapshot limits, sabotaged by writing a different cap into live `policies`, are *the V6 spine tested the only way that counts.* |
| The no-bar rule | Its own small law — see below. |
| Q7 | **Closed properly.** The one-step-short instinct kept in the record rather than smoothed away *is how the register is supposed to read.* |
| V5 | Proceed, with Q5's two-voice layout. Two reminders carried into the ticket: the mockup's ratify screen is authority for **direction and anatomy, never engine facts** (R058 §4 binds hardest where the rendering is most theatrical), and **the ceremony's gravity must come from what is true.** |

### Programme law — capability is not authority

R060 §1. **An API that exists but would break a load-bearing separation is, for this
caller, an API that does not exist.** The correct rendering of that law is: state shown,
no control drawn, reason stated on the page — asserted on both the rendered body and the
received bytes, which closes the door both ways.

### Programme law — where a control's name invites a wrong model, the page says what the control does not do

R060 §2. The live page states that policy-making continues under ENGAGED, because
nothing ratified can move while the switch holds. **The incident screen corrects the
operator's model at exactly the moment the wrong model is most expensive.**

### Programme law — a counter means what the code that increments it means

R060 §3. `cap_counters` is bumped at *reserve* time, so it is consumed **plus** reserved;
the name says neither. Read the incrementer, not the column name. R058 §4's law, proven
on arithmetic rather than on an enumeration.

### Programme law — an undeclared limit permits two lies, so draw neither

R060 §3. **A bar chart has two lies available — full and empty — and an undeclared limit
permits both.** Draw nothing and say why. *A proportion needs a declared denominator.*

### Programme law — a ceremony that overstates is a design-study banner away from a lie

R060 §5. Where a rendering is most theatrical, R058 §4 binds hardest: the design study is
authority for **direction and anatomy, never engine facts**. The weight of a ceremony
comes from the digest, the diff and the irreversibility **stated as the engine can back
it** — never from an element that dramatizes beyond what the engine does.

### Resolved by Response 059 (2026-08-28) — V3, and the Q7 actor ruling

| Was | Ruling |
|---|---|
| V3 | **Accepted.** 1024 passed, four gates green, CI green on both jobs. |
| Chain-numbered entries | **Adopted verbatim as the rule for every numbered thing we render:** *a citation must survive the view that produced it.* `unchained` is the honest absence — *a number nobody assigned is a number the ledger would have to defend without a record.* |
| Read-only asserted against the source | **The structural-fence law completing itself.** A behavioural test proves the paths it happened to take; the absence of a write path is a property of the code, checkable in the code. **Keep both — the structural assertion as the fence, behaviour as the smoke.** |
| Digest labels read from `digests.py` | **R058 §4's law held its first door.** Captioning `t_digest` "target" from the canary pillar's habit would have been confidently wrong in a compliance product. |
| **Q7 — the actor gap** | **Stopping at the freeze was the only correct move**; the interim rendering is approved as built. *A ledger that says "who asked is not recorded here" is honest; one that quietly answers identity questions with provenance facts would be F-H's lie wearing a filter's clothes.* |
| **Q7's shape — `actor_hash` REJECTED** | **Never digest secrets.** *"A hash of a credential is an oracle — anyone holding the key list, or guessing at weak keys, can test candidates against exported audit rows; you would have shipped a credential-checking service inside every export."* Delivery's instinct (*a raw key in a receipt is a credential in a receipt*) was right and **did not go far enough: a DIGEST of a credential in a receipt is still a function of the credential.** |
| **The ruled shape** | **A non-secret `key_id` assigned at key creation** — assigned, stable, meaningless. The ledger records the key_id. **Nothing derived from the secret ever touches a row**; revealing the ledger reveals which key acted, never anything about the key itself. |
| Q4's declined exemption | Approved, with the reason recorded — *which is exactly what keeps it from becoming an unwritten rule*. The known-gap-test shape is now **house practice for every temporary exemption: the exception carries the test that will delete it.** |
| Q6's near-miss | Earns the law below. |
| Q5 | **Unlanded by design is correct** — V3 changed the route, not the body. Verifying the plumbing without building on it is *the right amount of early.* |
| V4 | Check for the admin API first, as planned. **If the API half-exists (read but not write), that is still the read-only case, not a reason to invent a write path during the freeze.** |

### Programme law — a citation must survive the view that produced it

R059 §1. An ordinal that changes with the filter means an auditor quoting "entry 14" is
quoting the page rather than the ledger. Every numbered thing this programme renders
carries the number its source assigned, or says it has none.

### Programme law — a response is honest as a whole, or not at all

R059 §2, from the Q6 near-miss. `HTTPException` answering 404 with
`content-type: application/json` around an HTML body fixed the status and broke the
media type. **Status, media type and body are one statement; a fix that relocates a lie
to another header is not a fix.**

### Programme law — never digest a secret

R059 §3, binding with full force (stage-records recipe R9). **A hash of a credential is
an oracle**: anyone holding the key list, or guessing at weak keys, can test candidates
against exported rows — a credential-checking service shipped inside every export.

Identity in a ledger is carried by a **non-secret identifier assigned at creation**,
never by anything derived from the secret. *A digest of a credential in a receipt is
still a function of the credential.*

### Resolved by Response 058 (2026-08-28) — V1+V2, the ΔE floor, Q4–Q6

| Was | Ruling |
|---|---|
| `0.6.2` | **Published and independently verified.** Shamik ran the handover; core downloaded both files from PyPI, recomputed digests against the pre-upload record (wheel `6093133a…`, 250,759 bytes; sdist `5651731f…`, 292,226 bytes — both MATCH), and smoke-tested the published wheel in a fresh venv. Release stands at `v0.6.2` → `95a6150`. **Handover discharged.** |
| V1 + V2 | **Accepted.** |
| The snapshot reading | **Law, not implementation choice.** Delivery's sentence adopted verbatim: *"Those agree through the normal write path and can disagree through any other — and then they answer different questions."* Generalised: **the digest in the header names the snapshot, so the snapshot is the only honest source for the page under it.** This is V6's premise arriving early. |
| Correction beside, not into | **The house shape.** *"E10 wearing CSS clothes… corrections annotate evidence; they do not rewrite it."* |
| The five refusals | **Ratified.** The unreadable-snapshot one matters most: it is **the failing-open guard generalised to rendering** — *a page that cannot read its source must say so; it must never say "nothing".* The third assertion on the disagreement test is **the sabotage discipline applied to a test's own premise.** |
| **The ΔE floor replacement** | **Approved**, with the reasoning made canon (see the law below) and **two binding conditions**: the full ΔE matrix keeps printing in CI beside the mockup's numbers, and R057 §6's baseline is marked **superseded-by-disclosure** citing R058 §5 — *not overwritten*. |
| **Q4 — `--faint`** | Withholding it was right; Q1's scope was three tokens, not a licence to sweep. **Scope now granted, shaped by use:** where `--faint` styles text that must be READ, the token law applies; where it is decorative or marks a disabled affordance, WCAG's own exemption applies and is recorded with its reason. **Not permitted: `--faint` as a compromise for text that matters slightly less — "slightly less" is not a WCAG category.** |
| **Q5 — frozen descriptions** | **Yes — show BOTH voices, never merged.** The operator's frozen description is received data: quoted, attributed, visually distinct. `library.sentences()` is the derived voice: the page's own prose. *The screen's value is exactly the gap between them.* **Merging them would manufacture agreement; the layout must make disagreement visible, not smooth.** |
| **Q6 — the 200 for an unknown rule** | **Defect.** A detail page for a rule that does not exist answers **404** with an honest body. *The status code is the machine-readable verdict, and a 200 whose body says "not found" is the right-typed lie for machines* — every crawler, cache, monitor and script reads the type and believes the page exists. |
| Suite | The public site is **oneproof.dev** (live before Sept 8). onedoor's public door links to the repo as-is; future public docs may cite it. |

### Programme law — a floor on a proxy is a promise about the requirement

R058 §5, canon. **When the proxy and the requirement part ways, keep the requirement,
keep printing the proxy, and never let the proxy quietly become the requirement again.**

WCAG 1.4.1 asks that state never travel by colour alone. The ΔE floor was a way of
approximating that promise; word-plus-colour keeps it outright — **for every axis of
colour vision at once, including ones no ΔE pair was ever checked against.**

R057 §6's recorded baseline (ΔE 15.6 brand-vs-state under deuteranopia) is
**superseded by disclosure**, citing R058 §5. It is not overwritten: the mockup's
numbers keep printing beside the current ones, because *a shrunk baseline nobody sees
cannot be audited.*

### Programme law — check every phrase against the code that decides, not the names that suggest

R058 §4. `R055` §V2 described a **deny tier that does not exist** — core-authored text,
registered as a defect against the design note the same way R057 §5 registered the
mockup's contrast. **The design note is authority for direction and anatomy, never for
engine facts, which have exactly one source.**

Delivery's method is the law: the tier phrases were checked against `decision.py`, which
is how `OBSERVE` was found to return `Decision.EXECUTED` and perform nothing, **returning
before bounds are even evaluated — which no name would have told anyone.**

### Programme law — the status code is the machine-readable verdict

R058 §6. A page whose prose is honest and whose status code is not has moved the lie to
the channel that machines read. **A 200 whose body says "not found" is the right-typed
lie**, and its prose being correct is exactly what makes it dangerous rather than
harmless: every crawler, cache, monitor and script believes the page exists.

Delivery's first fix for this traded the status code for the media type — `HTTPException`
answers 404 with `content-type: application/json` wrapping HTML. **Fixing one channel
while breaking another is not a fix**; every machine-readable channel must say what the
prose says.

### Resolved by Response 057 (2026-08-28) — the contrast escalation, and the cursor

| Was | Ruling |
|---|---|
| **Q1: the state chips fail WCAG AA** | **Approved as proposed, and the defect is core's.** The failing ratios are defects in the **approved mockup** — a core-authored artifact. *"The mockup is design authority for direction and anatomy, never for a failing measurement. Accessibility is not a deviation from the design; inaccessibility is."* Lighten the three state foregrounds until each clears 4.5:1 on its muted background, hue preserved, brand untouched; backgrounds may darken slightly at delivery's judgment, measurements reported. |
| **Token law** | **State text at chip size clears WCAG AA 4.5:1, measured in CI, or the token does not ship.** *The verdict a user most needs to read must never be the faintest.* |
| **The digest cursor** | **Amended.** Delivery resolved a real spec conflict *in the more austere direction than R055 requires*: §3 mandates copy-on-click **and** permits "minimal inline JS", and delivery dropped the feature to keep zero JS. Copy-on-click **returns as progressive enhancement** — the same inline script attaches the handler and adds the class that enables `cursor:copy`, so **the affordance and the capability arrive in the same instant or not at all** and V8(f) is satisfied structurally. |
| No design-study banner; tabs as links | **Both correct.** *The banner marks studies; its absence marks the product.* Server-rendered navigation is the architecture, not a fallback. |
| The seal migration | **Closed.** Seven caught and cleared, *"one more than Forward 005's census predicted, which is the positive check out-reading its own advertisement."* The R049 supersession is fully discharged. |
| Colourblind numbers; `asserted`/`measured` | **Both approved.** *A passing check whose numbers nobody sees cannot be audited* — ΔE 15.6 brand-vs-state under deuteranopia is a recorded baseline, and a change that shrinks it must say so. Type the classification words once, import them everywhere, including in the seal check. |
| **Core's own producer obligation** | **Effective immediately:** every core→delivery communication carries either a response number or the explicit marker `(unnumbered acknowledgment — cite by date)`. *A source that is easy to cite wrongly shares the fault with the citer.* The citation defect had two parents. |

### Programme law — a route's first honest test is a request, not an import

R057 §4, generalising F-A. `banner_for` read an enforcer table from the draft store and
every shell route raised `no such table` on a fresh install; **no library-level test saw
it**, because a library call happens on the calling thread and a route happens on a
threadpool thread, against whatever connection the app actually holds.

The served-app smoke test over *every* route exists for this shape. Keep it merciless.

### Programme law — a checker must parse the language it checks, not the prose around it

R057 §4, from delivery's own second defect. The strengthened seal check condemned
`.store-warning` — the advisory panel R056 §2 names as the thing that must **not** fire —
because it read the explanatory comment above the rule as part of the selector.

**A check that reads comments condemns the code that documents itself best.** Fix
pattern: strip comments or use a real tokenizer; never regex over raw text.

### Programme law — a correction to received data is a new artifact that cites it

E10's two-discipline, arriving at a design system. Core's mockup carried a measured
defect, and the fix is recorded in `studio/tokens.CORRECTIONS` **beside** the vendored
block rather than edited **into** it. The block keeps its bytes and its digest; each
correction carries the measurement that forced it and the ruling that approved it.

Editing the block would have been quicker and would have destroyed the one property that
makes the palette auditable — that it can still be compared with what core approved.

### Resolved by Response 056 (2026-08-28) — the R049 §3 conflict

| Was | Ruling |
|---|---|
| `ND-055` P0 | **Accepted** at `a889300`. *Eight of eleven tests failing against the shipped code before the fix is the sentence that makes the other numbers credible — tests that have never failed have never been shown to look.* |
| F-G's generalisation | **Adopted as the pattern for every empty-state fix in this build**: an affordance that exists only in the empty state is *an affordance discoverable only by the lost.* |
| The `parse_qs` choice | **Approved with approval underlined** — content-type dispatch, JSON API byte-identical, no new dependency: *the no-framework ethos holding under pressure to bend it.* |
| **R049 §3's `--seal` clause** | **SUPERSEDED.** The strengthened rule binds **everywhere** — no grandfathered screens, no channel where gold may carry state. R049 was ruled before the seal/state contradiction surfaced; **its premises moved, so the ruling comes back — it does not stretch.** R049 §3 stands *except its fourth mechanism*: size, position and weight remain, and three are enough. If prominence genuinely fails with three, that is a **design escalation, not a reason to readmit gold.** |
| Sequencing of the migration | **Delivery's second option.** S4/S6 migrate off seal-in-state **as part of V1's shell work**, so the token change lands exactly once, in the `0.7.0` line after Sept 12. **`test_coverage_map.py:82` and `test_proposal.py:156` invert in the SAME COMMIT as the migration** — *a test that requires a violation becomes a defect the moment the law strengthens, and it must not survive one commit longer than the violation it protects.* Afterwards, run Forward 005's sabotage pair against S4/S6 and report the four violations as **caught-then-cleared, by name**. |
| V6's premise | **Accepted as verified.** No new table, no escalation. Screen copy: the version dropdown lists what `snapshot_for()` can honestly serve; anything it cannot serve renders **"not retrievable", never as absent.** |

### Resolved by core's F-B ruling (2026-08-27, unnumbered acknowledgment)

| Was | Ruling |
|---|---|
| **Q2** — does AADP-01 type `params`? | **Yes.** §5's rule — *monetary values are decimal strings, never floating-point numbers* — **governs the whole message**, and §5.1's worked decide request carries `"params": {"payee": "acme-gmbh", "amount_eur": "40.00"}`. A decimal string in `params` is **the draft's own example**, not merely permitted. |
| **Q1** — which way do the paths agree? | **The spec's direction.** Numeric bounds over a declared cost parameter accept the decimal-string form (parsed as `Decimal`, never through `float`) and JSON numbers besides. The current refusal is a **conformance defect**, and an ironic one: it forces integrators toward exactly the binary floats the Security Considerations names as an attack surface on budget arithmetic. |
| **Q3** — before or after the freeze? | **Delivery's lean ratified: it waits.** *`denied` → `permitted` is the one direction that never rides a hotfix into launch week.* Lands as the first post-freeze change (`ND-054`) with tests in both directions: `"40.00"` accepted and evaluated exactly, a float-precision edge case handled deliberately, and a garbage string still refused with the bounds message naming the parameter. |

**Delivery's read was wrong, and the mechanism is recorded because the mechanism repeats.**
The escalation argued the decimal-string rule belonged to *generated* structures and that
the spec was silent on `params`. **`-01`'s rule was already unqualified** — *monetary
values*, full stop. The scope restriction was delivery's inference, drawn from **where it
first met an example of the rule** (this file's budget-object line) rather than from the
rule's own words. And beneath that, the plainer failure: **delivery reasoned from this
document's summary of the spec instead of opening the draft**, which sat on the same disk
and which delivery opened an hour later for the Appendix B review.

> **A summary is a claim about a source. Check the source before you reason from the
> claim.**

The escalating was right — a verdict-changing behaviour was flagged rather than taken, and
the proposal it reached is the one core ruled for. **What was wrong was the read, not the
escalation.**

### Resolved by Response 054 (2026-08-27)

| Was | Ruling |
|---|---|
| `ND-052` | **Complete.** Six tickets, normative order, no ticket built before its ruling; 857 tests at close against 592 at S1's baseline. The proposer arriving last into a world where the ceremony, validator, law tests and coverage map were already waiting is the epic proving its own sentence about why it was built last. |
| The constitution decision | **Ratified and elevated to standing law**, not overruled: **the archive is immutable; the constitution is alive; the origin and the in-force text are different documents, and each says so on its face.** *A constitution that could only be amended by editing history would make every amendment a small forgery.* One instruction attached: **pin the origin by digest**, so descent is checkable rather than narrated. |
| The benchmark handling | **The disclosure gate working as designed.** Recorded in the corpus's own docs: the fixture never interprets instructions, **so it cannot be persuaded, so its injection score is a claim about nothing** — 9/11 must not be read as a model's injection resistance; that measurement belongs to a future budgeted live run. The no-miss-refusing test is **the anti-perfection rule made structural, first of its kind in the repo.** |
| `0.6.0` | **Cut it before launch week** — the launch narrative points at a released Studio, not at a main branch. |
| `ND-053` | **GO to decompose, build held.** The **freeze rule stands from now to the firing sequence: no breaking change lands between here and launch.** The build ruling comes after Sept 12. |

### Resolved by Response 053 (2026-08-27)

| Was | Ruling |
|---|---|
| **Q1** — what a proposal record is called | **A derivation record, and the constitution was amended rather than stretched.** Principle 5 now reads: *every derivation gets a record; a record that promises re-derivation is a receipt; a record that cannot promise it says so on its face.* The word *receipt* was coined when everything was recomputable, and **a constitution whose own noun outruns the computation is R050 §4's defect installed at the top of the document.** One more face sentence required: **the candidate's authority comes from the checks it passes, never from this record** — provenance, not trust. |
| **Q2** — how the model is supplied | Mechanism approved; the field is **`proposer_provenance: live \| fixture`** — the *same value pair* as `ledger_provenance`, because it is the same decision and **a renderer must not learn a second dialect for one distinction.** The instrument block is **never empty in either case**, and the label survives to every rendering with B5's sabotage shape. |
| **Q3** — where mentioned rows live | **Adjacent, not merged: one surface, two sections, never one table.** Merging would not make one honest list, it would make one dishonest one, because **a list is honest only if every row carries the same kind of warrant.** The second section states its warrant on its face and each row cites the coverage state it was checked against. |
| **Q4** — the demo gate | **No score threshold — and that is harder, not softer.** *A threshold we pick for our own generator is the instrument fitted to the finding.* The demo may run when the benchmark's results, **misses included**, are published beside it and the demo states its number. The corpus includes adversarial descriptions; the published misses include the **security-shaped** ones. CI benchmarks the fixture path only. |

### Resolved by Response 052 (2026-08-27)

| Was | Ruling |
|---|---|
| S5 | **Accepted.** Every row of R051 §7's list green, both fold-ins in the commit, register regenerated immediately before it. Five tickets delivered in sequence with **no ticket built before its ruling and no ruling stretched past its premises** — the record the launch stands on. |
| The wheel-presence assertion firing on day one | **Not a blemish — the entire argument for the assertion.** *A check earns its place the day it fires.* |
| The inverted webhook control | **Recorded as the standing example of why asserted verdicts are required.** A rule that loads cleanly and tests cleanly as "no error" is precisely the artifact that ships inverted controls into payments packs. |
| The `t.co` case | **The canonical U4 exhibit**, and *"you cannot dodge the control with a shortener"* is to be kept verbatim as a launch-demo sentence. |
| The gate-test message | Naming honesty **in a test message**: *an error message is an assertion too, and one that indicts the wrong party is a false accusation with a stack trace.* |
| The unasserted `.replace()` | **Ratified in delivery's words** and paired with core's own overreach instance as one named class, recorded above beside the proxy table. |
| S6 | **GO to decompose, explicitly not GO to build.** *The protocol does not change at the finish line* — decomposition, then rulings, then the build. |

### Resolved by Response 050 (2026-08-24)

| Was | Ruling |
|---|---|
| S4 | **Stands.** The unprompted addition called out as the standard: `range.state` carrying `uncitable` as its own value, so an unchained store's numbers read as *real and uncheckable* rather than as a bare count. **The three-outcome rule is a habit, not a list of places it has been applied.** |
| The runner | **Ratified.** Two green-looking failures on day one — contract present beside a non-zero exit — is the argument made in measurements rather than prose. |
| The `" passed"` contract | **Proxy-for-contract, sixth instance**, recorded above. |
| The false alarm | **Law**, paired with R048's, recorded above with its deciding principle. |
| **§6's finding** | **Ruled: a rename, not a migration.** `exercised_effects` claimed history; the computation is a projection, and for a *candidate* that projection is the correct question. Renamed `would_exercise`. **The historical question is not the map's** — resolving what actually happened needs each row's own `policy_version` and its frozen params, because `param_effects` makes effects param-dependent. That is the engine over history against sealed inputs: **that is a backtest.** No hashed column, no `/3`, no migration — *the map projects and cites; the backtest measures and receipts.* |
| `ND-053`'s sequencing | **Closed.** Detector first, refusal after, is *the courtesy a breaking change owes the people it will break.* |

### Programme law — a protection that depends on a second, optional declaration is not a protection

**Binding on all policy** (R049 §6), not only on generated policy. Recorded here rather
than in a ticket because this is its **third instance**, which is the threshold at which
a rule stops being a finding and becomes the programme's.

> **A protection that depends on a second, optional declaration is not a protection — it
> is a default.**

The law is about the **shape of the rule, not the identity of its author.** R027 applied
it to the Studio's generator because the generator was the surface in front of us;
nothing in it was ever about who typed the rule. The generator rule is therefore a
**case** of this law, cited as one, never its source.

Instances, in order:

| # | Where | Shape |
|---|---|---|
| 1 | `ND-040`/U4 | a policy with an `opaque` block and a `min_tier: null` effect let an opaque host auto-execute — the protection depended on the effect floor also being declared |
| 2 | `R027` / the Studio generator | it may never emit a rule whose safety depends on an optional second declaration |
| 3 | `ND-053` (below) | `effects: [money.egress]` with no `effect_policies` row: the label is **silently dropped**, so the protection depended on a second declaration the author may believe they wrote |

**Measured on `0.5.0`, not reasoned about:** the same request returns
`PERMITTED, effective_tier 1` with the label alone and `proposed, effective_tier 3` once
the effect policy exists.

**`ND-053` makes `validate_policy` refuse it**, under three constraints core attached
because this changes what a deployment boots with: a **declared breaking change in its
own release**, never folded into a patch; **no opt-out flag** — a switch permitting inert
effects would itself be a protection depending on a second optional declaration, the law
applied to its own escape hatch; and the refusal **names the effect, the rule that labels
it, and the remedy**, because a fail-closed check whose error does not say how to pass it
converts a defect into an outage.

### Resolved by Response 049 (2026-08-24)

| Was | Ruling |
|---|---|
| The `0.5.0` verification | **Accepted**, and the deciding move named: taking the `sha256` from **PyPI's index API rather than the upload transcript** — the receiver's record of what it holds, not the sender's account of what it sent. |
| The annotated-tag near-miss | **The report's finding, not a footnote.** New law: **an identifier is answered at a layer; name the layer or you do not know what you compared.** Joins *a green answer about the wrong artifact*. |
| The tooling proposal | **Both layers approved and built.** Two requirements: the runner is the **documented** way gates are run (so a raw-command transcript is itself the smell), and it **prints what it ran and where** — *a control indistinguishable from its own absence is not yet a control*. Delivery's honest limit ratified as the right standard: **an irreducible remainder is not a failure of the tool; it is the thing the tool exists to make small and conspicuous.** |
| The two extra instances | Named as old classes: the monitor filter is **proxy-for-contract, fifth instance**; the backslash-U heredoc is **a path is data, and data pasted into a language is code until you make it not be.** Both are tests in `tests/test_gate_discipline.py`. |
| **Q1** — the semantic pair | **Sustained, no pair.** Red on a receipt means *this was denied* (a past fact); red on a coverage cell would mean *this would be denied* (a prediction about a class) — **a colour that means two things means neither.** Ranking ratified with its law: **rank by what a state does at decision time, not by how alarming its name sounds.** |
| **§4's fourth state** | **Core's finding back to delivery:** `unobserved` has no enumeration source, so it is a row **only within a bounded vocabulary** (a declared effect nothing exercised, rendered *absent*) and otherwise the map's **footer**. Principle 4 turned on the coverage map. |
| **Q2** — evidence or view | **A view that cites.** The distinction from S1 is **instrument, not convenience**: a backtest cannot be re-derived without running the engine; this can. **The citation pair is the receipt.** With a requirement: the citation must be exportable and the derivation documented well enough for a second implementation. |
| **Q3** — the inert refusal | **Yes, it refuses**, and the rule binds **all policy**. See the programme law above and `ND-053`. |

### Resolved by Response 048 (2026-08-24)

| Was | Ruling |
|---|---|
| S3 | **Stands**, T1–T6. The both-directions colour test called out specifically: *a rule tested one way forbids the wrong thing without requiring the right one.* |
| The gate-fidelity defect | **Ratified as law: a gate is a command and the world it runs in.** General form for the file: **a green gate is a claim about an environment; state the environment or the claim is unbound.** Declaring the dependency rather than silencing the checker, then closing the *class* rather than the instance, is right twice over. |
| The renamed test | **Ratified as law: a test's name is a claim, and a name that outruns its check is false comfort.** Third instance of one rule at three layers — R045 (fields), R046 (reserved fields), R048 (test names). **Naming-honesty is now a settled programme law: every name in this system is an assertion, and an assertion that outruns what is checked is a defect whether or not anything fails.** |
| Release vs. S4 | **Cut the release first.** *A claim demonstrated from an unreleased branch is a claim; from a published wheel it is evidence.* `0.5.0`, additive, Studio behind `[studio]` with its boundary named exactly. |

### Resolved by Response 047 (2026-08-23)

| Was | Ruling |
|---|---|
| S3's four findings | **All endorsed**, two with emphasis: the scope-fence resolution **checked against the vendored bytes rather than remembered** (which is why it dissolved instead of becoming an escalation), and the wrapper's honesty clause — *problems found*, never *all problems* — as the overclaim discipline applied to an error list. |
| **Q1** — the canvas's surface | **(b) sustained**, and the security reason ratified as the deciding one: one leaked credential must not both answer decisions and rewrite the rules those decisions are made under. **One hard edge added:** the Studio **refuses to bind anything but loopback**, as a test rather than a default — possession-of-the-box is honest only while the binding makes it true, and a drift to `0.0.0.0` silently converts it into possession-of-the-network. X-6's shape. |
| **Q2** — where a candidate lives | **The Studio's own `studio.db`.** The line that decides it: **the enforcer's database contains no row the Studio can edit.** Mutability already lives in the main store *where the enforcer owns the mutation*; what it has never held is a row a second process edits. Migration `0019` **released** — the main sequence is the enforcer's history. |
| **Q3** — re-basing | **Pin and surface, sustained**, with two sharpenings: the state **names both hashes** (*a warning naming no versions is a mood, not a fact*), and re-pinning **invalidates every preview with it** — no panel survives showing a number from a base the diff no longer uses. |

### Resolved by Response 045 (2026-08-23)

| Was | Ruling |
|---|---|
| The `MAGIC`-not-`CURRENT_VERSION` witness | Captured as law: **a regression must compare against the fact itself, never against a second name for the fact** — two names drift together, and a test asserting their equality certifies the drift. |
| The structural sibling audit | Accepted as the **AST-guard pattern** doing what it was adopted for. The corrupt-cache header check is accepted with it. |
| The SHA-filtered CI check | Accepted, and **now standing procedure wherever CI is quoted**. *A green answer about the wrong artifact* joins the Forward 004 family. |
| S2 finding one (the preview) | **Sustained with emphasis.** The preview comes from the scratch-store ratification, over the candidate **merged over the active set**. A sabotage that seeds the scratch store with only the changed rules and watches the equality test fail is **required**. |
| S2 finding two (the CAS) | **Sustained as written.** CAS on the `version_hash` the diff was read from, and the lost-race path **refuses loudly — it never retries on the operator's behalf**. |
| **Q1** — `ratified_by` | **Sustained, with a rename**: the field is `ratified_by_session`. *A field's name is part of its honesty* — the shorter name reads as an identity claim to every future reader of an export. Authenticated identity later is `onedoor/ratification/2`. |
| **Q2** — backtest required? | **Allowed and visible**, with two requirements: a cited digest is **verified at the ceremony** (resolves here, and its `policy_digest` equals `candidate_digest`, else refusal with its own named reason); and **absence is rendered, not merely null**, in every view — with a cited backtest's `ledger_provenance` surfaced by dereferencing. |
| **Q3** — kill switch blocks? | **No.** The switch's dominance over every action is exactly why it need not win over policy-making: nothing ratified can move while it holds, so **the moment of risk is the lift**. Two requirements: the switch's state is a **hashed field** on the receipt, and the active `version_hash` is recorded at engagement so the release path reports any change since. The law: **the switch that stops everything need not stop the pen — it already stops the consequences, and the lift is where the pen's work must be shown.** |

### Resolved by Response 044 (2026-08-23)

| Was | Ruling |
|---|---|
| S1 | **Stands.** All four requirements accepted. Two design vindications named: the stripped-label sabotage fails because `ledger_provenance` sits **inside** the digest, and Q1's law lives in `caps.resolve_cost`. The principle: **laws pushed into construction outrank laws kept in tests, which outrank laws kept in memos.** |
| The `append_expiry` defect | **Accepted**, with a programme law recorded: **time is an input, and a suite that never lets it pass has not tested what it triggers.** Instruction: pin it with a fixture-independent regression living with the chain tests, and audit sibling write paths while the pattern is fresh. Fold into the release notes with the defect stated plainly. |
| The Q3 amendment | **Accepted** — identity instead of bytes. *A digest answers exactly one question*, and the question was row identity, not file identity. **Acceptance condition made explicit:** first use generates automatically, verifies against the pinned HEAD, and refuses on mismatch. |
| S2 | **GO** — opens by citing `record_snapshot` as settled. |

### Open

**None blocking.** `0.6.1` is staged with the operator-validation fixes; F-B is ruled and
ticketed as `ND-054`, held behind the freeze.

**`0.6.1` carries the first operator validation's findings.** F-A — the Studio server
returned Internal Server Error on every page, because its stores were opened once at
startup while every route is a sync `def` that FastAPI runs in a threadpool. **Every
library-level test passed while the served surface was broken.** The regression test was
written first, reproduced the operator's error verbatim, and reaches the app through the
server rather than through the function a route calls. Verified after the fix **over a real
socket, not a test client** — *verify on the terrain that failed.* F-C (`__version__`), F-D
(the Studio app self-describing as `0.4.x`) and F-E (a PyPI-reader's quickstart, every
command run before being written) ride with it.

**`ND-054` is F-B, ruled: a conformance defect against AADP §5 and the draft's own worked
example.** Held behind the freeze because it widens a verdict from `denied` to `permitted`.

**Core → delivery:** none, as of Response 062 (2026-08-28). **`ND-052` is complete** and
`0.6.0` is staged; `ND-053` is decomposed with its build **held by the pre-launch freeze**. `ND-001` is built (C1–C5),
chaining opt-in and off by default; next is `ND-010`, with `ND-009` able to run in
parallel, then `ND-015`/`ND-017`; `ND-052`, the Policy Studio, is ticketed and sequenced
after the epic with no code before launch.

~~**Delivery → core — ONE, surfaced by the `0.4.0` decomposition (`TICKETS-0.4.0.md` §7).**
**Genesis `prev_hash` is ambiguous under R015's null-versus-empty rule.** `ND-001`
starts the chain at a genesis row because existing rows cannot be retro-chained; that
row has no predecessor to name, so `prev_hash` NULL would mean *both* "no predecessor
exists" **and** "not yet produced" — the exact collapse R015 makes programme-wide. A
verifier walking a mixed archive could not tell the first chained row from an
unchained one. Options delivery can see: a reserved 64-zero sentinel; a distinct
`chain_state` column; or genesis carrying the id of the last unchained row in its own
field, which `ND-001` already requires it to record. **Receipt content, so core's
call.** **Does not block `0.4.0`** — that release only creates the column NULL — but
it must be settled before `ND-001` writes the first chain.

**Delivery → core (closed):** `0.3.6` is published and its §implstatus revision is locked.
The earlier item — Core→Forensics Response 010's bytes — closed
2026-08-21 by disk copy; every digest-bearing memo verifies and the quarantine is empty.
Digests are not repeated here: `docs/from_core/INTEGRITY.md` carries the one generated
register, per R012 — *a digest in a ledger is generated, never transcribed.* Recorded for the record: delivery's reconstruction
of that memo was wrong in one character (`⇒` read as `—`, indistinguishable under the
relay corruption), so the quarantine prevented a false record entering the archive.

**Core → delivery:** none, as of Response 010 (2026-08-21). Escalations 001–005 are
fully ruled; 006 and 007 raised nothing requiring a delivery answer. The next expected
contact is delivery's `0.3.6` release ping, which triggers core's §implstatus revision
covering the LiteLLM conformance fix, the obligation-machinery gap (N6/`ND-038`), and
the `not_attempted` defect (A4b/`ND-039`) — and which now also confirms `main` is green
on `origin` again.

---

## 6. Target vocabulary (`aadp/0.2`, from `0.4.0`)

The settled spec surface for `ND-002`, `ND-003`, `ND-005`, `ND-009`. Reproduced
here so implementers have one reference; core's Response 001 is authoritative.

**Reason codes.** `cap_daily_rate` → **`cap_rate`**; `cap_eur_day` **and**
`cap_eur_month` → **`cap_value`** (the window moves into the budget object); plus
one genuinely new code, **`sender_mismatch`** (E5). Old codes are DEPRECATED, never
removed, and MUST NOT be emitted by a PDP advertising `aadp/0.2+`.

**Why a clean break is safe here:** reason codes are *audit vocabulary*. A PEP's
behaviour is fixed by the **verdict**, never by the reason string — so a `-00` PEP
that has never heard of `cap_value` still denies correctly. The break is
**audit-only; there is no enforcement-path regression.**

**`budget` object** — on the Decide Response, present **iff** verdict is `deny` and
reason ∈ {`cap_value`, `cap_rate`}:

```json
"budget": {
  "dimension": "value",                        // REQUIRED  "value" | "rate"
  "unit": "EUR",                               // REQUIRED  ISO 4217 for value; a token ("calls") for rate
  "window": "month",                           // REQUIRED  "day" | "month" | ISO-8601 duration
  "limit": "250.00",                           // REQUIRED  decimal string, never float
  "consumed": "250.00",                        // REQUIRED
  "remaining": "0.00",                         // REQUIRED
  "window_resets_at": "2026-09-01T00:00:00Z"   // REQUIRED  RFC3339 UTC
}
```

**`approval_ref_status`** — evidence field, ∈ {`absent`, `honored`, `expired`,
`consumed`, `unknown`, `action_mismatch`, `principal_mismatch`}. Keeps expired /
consumed / forged forensically distinguishable **without** polluting the verdict
vocabulary. Approvals are principal-scoped; a ref presented under a different
principal is `unknown` for the verdict, `principal_mismatch` in evidence.

**Receipt envelope** — frozen; all columns land in the `0.4.0` migration, later
ones NULL until their increment:

| Increment | Columns |
|---|---|
| `ND-001` (P1) | `prev_hash`, `seq`, `row_hash` |
| `ND-015` (P2) | `sig`, `key_id`, `alg` |
| `ND-017` (P3) | `e_digest`, `i_digest`, `t_digest`, `v_digest`, `anchor_ref` |

All digests SHA-256, lowercase hex, over canonical bytes. Anchoring is periodic,
not per-row. The *preimage definitions* (which fields constitute `E` for an onedoor
decision, etc.) are `ND-017` design work with core sign-off at decomposition.

**Canonical form** (normative from `0.4.0`; one form for wire, storage and preimage):

- **Decimals** — fixed-point only, never exponent form. Shortest exact form: strip
  trailing fractional zeros, omit the point when the fraction is empty
  (`250.00`→`"250"`, `0.50`→`"0.5"`). Single leading `0` for |x|<1. No `+`; `-` only
  on negative nonzero; negative zero renders `"0"`. Same rule for `"value"` and
  `"rate"` — no per-currency minor-units logic.
- **Datetimes** — RFC3339, UTC, `T` separator, uppercase `Z`, seconds always
  present, fractional seconds shortest-exact and omitted entirely when zero.
- **JSON** — keys sorted, NFC.
- **Implementation trap:** `str(Decimal("2.5E+2"))` → `"2.5E+2"`. `str()` is not a
  canonical renderer. Render through an explicit fixed-point function and hold it
  with a property test: equal-value/different-scale `Decimal` pairs produce
  identical bytes, and canonical output re-canonicalises to itself.
- **`params_json` / `payload_json` — ruled (E10, R003/R004); not canonicalised by
  the above, by design.** They are *received* data: frozen **verbatim at ingress**,
  never re-serialised, so the stored bytes are the received bytes. The canonical form
  above governs *generated* structures (`budget_json`, the receipt fields). Parsing is
  `parse_float=Decimal`, including policy YAML; duplicate keys / NaN / Infinity /
  non-UTF-8 ⇒ deny `malformed`. The in-process binding receives no bytes, so its frozen
  form is one ACJ serialisation at ingress and the row must make that provenance
  distinguishable. Lands in `ND-002`'s row format; closes N7.

---

*Update protocol: every ticket that closes moves its row here in the same PR,
with the evidence column filled in. After any release that changes this file,
ping core so the draft's Implementation Status section and the papers'
"reference implementation, version X" claims are refreshed.*
