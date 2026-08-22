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

### Open

**Delivery → core — THREE, from `ND-017`'s decomposition (`TICKETS-ND-017.md` §5), and
the first two block M1 because a preimage freezes on first write.**

**1. Are the four preimages right?** Proposed in §1, built to the vendored manifest's own
scheme rather than invented — read from `manifest.schema.json`, and confirmed by
computing that the shipped `t_digest` `4f53cda1…b945` is SHA-256 of canonical `[]`, so
`T` really is a declared closure. Every digest is over `canonical_bytes`, so **no
concatenation appears and `len8` is not reached** — stated because R039 asked for it
*where concatenation appears*, and the honest answer is nowhere. `T` is the one delivery
is least sure of: an archive's declared closure translates only by judgment into "what
must a verifier trust to accept this verdict".

**2. Is `anchor_cadence` inside `I` intended?** It follows from R039's *cadence is
declared config inside the instrument*, and the consequence is that **changing the
cadence changes `i_digest` for every row sealed afterwards**. Delivery reads that as the
point — X-7's shape, a declaration change being visible — but a consequence that
permanent is better confirmed than discovered.

**3. Does a root found in the store report `self_consistent`?** R038 §1 one level up, and
delivery believes it follows directly. Raised because it means **a store on its own can
never say an anchor is verified** — the same slightly uncomfortable place, and now the
second time this product declines to vouch for itself.

M2 through M5 are unblocked; migration `0015` is claimed.

**Core → delivery:** none, as of Response 039 (2026-08-22). `ND-017` is decomposed —
the epic's last ticket — and its close opens the `ND-052` Studio epic. `ND-001` is built (C1–C5),
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
