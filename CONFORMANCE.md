# CONFORMANCE.md — onedoor ↔ AADP

**Implementation:** onedoor `0.3.6` (tag `v0.3.6`)
**Standard:** AADP Internet-Draft `draft-saha-aadp-01`
**Test suite:** 135 passed at the `0.3.5` baseline; **175 passed / 8 skipped** on `main`
at 2026-08-21 (Python 3.12, `pytest -q`, all four gates green)
**Last verified:** 2026-08-20, by direct source inspection at `3dfe3cd`
**Spec rulings in force:** Core→Delivery Responses **001–013** (001–006 on 2026-08-20; 007–013 on
2026-08-21), plus Core→Forensics 009 §3, 010 §2 and 012 §1 by cross-session forward.
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
| A4 | Unit-neutral reason codes + structured `budget` object (§decideresp) | ❌ | `CheckId` still emits `cap_daily_rate` / `cap_eur_day` / `cap_eur_month` (`models.py`), and `caps.py:139–149` formats budget state into a free-text `detail` string. `PolicyDecision` has no `budget` field, and **no AADP protocol version is stamped anywhere in the package or the evidence store**. **Settled (E1): `cap_rate` + `cap_value` replace all three; window and unit move into the `budget` object; clean break at `0.4.0`, no dual-emission; protocol bumps to `aadp/0.2`.** Shape in §6. | `ND-002`, `ND-003` |
| A4b | Report outcome vocabulary: `success \| failure \| timeout \| not_attempted` (§reportreq) | ❌ | **Live conformance defect, found 2026-08-20 (Escalation 005).** `report_result(..., ok: bool, ...)` has **no outcome parameter at all** — onedoor can express two of the four outcomes; its own docstring names three. `not_attempted` and `timeout` both collapse to `ok=False` → `Decision.FAILED` + `action.failed`. Three consequences: (a) the audit asserts an attempt that never happened; (b) `cap_reservations` is settled **unconditionally before the outcome is examined** (`decision.py`), so a conformant `not_attempted` **permanently charges budget for an action that never occurred**; (c) the fix is an API change, not an enum edit. Not reachable until obligations ship — reachable the moment `ND-038` does. | `ND-039` |
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

### Open

**Delivery → core:** none. The last item — Core→Forensics Response 010's bytes — closed
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
