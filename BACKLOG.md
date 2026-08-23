# BACKLOG.md — onedoor delivery

**Baseline:** `0.3.5` @ `3dfe3cd`, 135 tests passing.
**Source:** `onedoor_Roadmap_20260820.md` §2–§6, corrected by the code survey
recorded in `CONFORMANCE.md` §3–§4.
**Owner:** delivery. Standard-coupled decisions marked 🔺 go to core first.
**Rulings in force:** Core→Delivery Responses 001–005 (2026-08-20). **No open questions
on either side.** The settled spec
surface is `CONFORMANCE.md` §6. **Nothing is gated. `ND-001` and `ND-039` are both unblocked.**
**`0.4.0` remains one breaking increment** — the obligation surface turned out to be
normative in `-00` already, so landing it is conformance catch-up, not a wire change.
**`0.3.6` RELEASED and published** 2026-08-21 — tag `v0.3.6` @ `6a95a69`, on PyPI,
GitHub release live, artifact digests verified byte-identical to the build. `ND-021`,
`ND-024`, `ND-025` and `ND-036` all closed on origin. Core's §implstatus revision is
locked with both of delivery's accuracy-check clarifications adopted (R014).

**`0.4.0` in progress — GO from R015, in delivery's proposed order.** `ND-002` +
`ND-003` + `ND-039`, one breaking increment, migration `0007`, `ND-040` immediately
behind it per R011. **Decomposition written before the code: `TICKETS-0.4.0.md`** —
it carries the work order, the `0007` column shape, the test plan, and seven findings
from the code survey that the backlog did not name (four of them live defects). **`0.4.0` RELEASED and published** 2026-08-22 — tag `v0.4.0` @ `5c50466`, on PyPI,
GitHub release live, artifact digests verified byte-identical to the build. W1–W7: the canonical renderer is vendored and pinned by property tests
over generated inputs; migration `0007` lands the row format including the whole
receipt envelope dark; and Decimal now survives ingress → bounds → cost → reservation
→ settlement, which closes S2 (a live enforcement mis-decision) and S3; and W4 lands
the `aadp/0.2` vocabulary (`cap_rate`/`cap_value`, `sender_mismatch` reserved), the
protocol stamp on every row, and R019's `snapshot_schema`. W5 lands the seven-field `budget` object, closing the day-vs-month granularity gap
W4 deliberately opened; W6 lands the four-value outcome with outcome-dependent
settlement, closing A4b; W7 lands the verbatim freeze with row-level provenance.
**`ND-040` in progress — GO from R024, decomposition first.** URL canonicalization
before effect matching, with the reason code already ruled (`malformed`, no new
vocabulary, failure recorded distinctly in evidence). **Decomposition written before
the code: `TICKETS-ND-040.md`** — work order U1–U5, the canonicalization surface, the
acceptance tests, and one surfaced question. **Key finding: the benchmark's three
URL-shaped evasive cases are three different problems**, and canonicalization alone
closes one of them — **ruled by R025: `ND-040` owns all three**, with the opaque-host
class as U4 inside the ticket and the disclosure's mechanism sentence corrected in the
same arc. **U1 is done:** `onedoor/guardrail/urlcanon.py`, deterministic, **no new
runtime dependency**, 36 tests covering nine canonicalization concerns in both
directions plus idempotence and non-collision over generated inputs.

A Phase-B read-only receipt viewer is announced for after `ND-040` lands.

> **Sequencing correction from the decomposition.** This backlog assigns vendoring
> `canonical.py` to `ND-001` (`0.4.1`). That is the wrong order: `ND-002`'s row format
> and `ND-003`'s budget object both need the renderer, so **vendoring moved into
> `0.4.0` as W1** — `onedoor/_vendor/canonical.py`, byte-identical to the pinned v3
> artifact and held there by a test. `ND-001` inherits it rather than introducing it.

> **Verification note.** The device's `.venv` is a Windows venv on Python 3.12.10 —
> the same minor CI uses — and all four gates run natively. Baseline independently
> confirmed at `227a682`: **135 passed** (the venv had been missing `langchain`, which
> module-skips 7 tests and shows a misleading 128+1skip until `pip install -e ".[dev]"`).
> **Now 156 passed, 6 skipped, and all four gates green locally** — `ruff check`,
> `ruff format --check`, `mypy --strict onedoor`, `pytest`. The `+21` over baseline:
> `ND-024` `+3`, the `.gitattributes` byte-fidelity guard `+15`, memo-integrity `+3`
> (6 skips are memos 001–006, which predate the integrity-footer protocol).
> **`origin/main` is still red until this is pushed.**

## How to read this

- **Size** is relative, not calendar time. **S** = one sitting, one module, few
  tests. **M** = several modules or a migration, a day's focused work. **L** =
  multi-module with a design decision inside it. **XL** = an epic; decompose
  before starting.
- 🔺 **core-gated**: has a wire-observable or research-coupled decision inside it.
  Do not start implementation until core answers. The question is stated on the
  ticket.
- Every ticket's Definition of Done is the same and is not repeated per row:
  *implementation + tests + suite green + `CONFORMANCE.md` row updated + docs
  touched where the behaviour is user-visible.*

## Ticket index

| Phase | Tickets |
|---|---|
| P0 — hygiene, unblocks everything | ND-025, ND-021, ND-024, ND-036 |
| P1 — conformance + trust (roadmap §6 near term) | ND-001 … ND-010 |
| P2 — product surface (roadmap §6 mid term) | ND-015 … ND-019 |
| P3 — reach + enterprise (roadmap §6 long term) | ND-020 … ND-037 |

---

## Phase 0 — hygiene (do first, small, unblocks the rest)

### ND-025 — CI: run the suite, mypy strict, and ruff on every push · **S**
`pyproject.toml` already configures `mypy strict` and `ruff`; nothing runs them.
Add a GitHub Actions workflow: Python 3.12 + 3.13 matrix, `pytest`, `mypy`,
`ruff check`. Branch protection on `main`.
**Why first:** the brief's discipline #2 ("the suite stays green, 135 and rising")
is currently enforced by hand. Every ticket below adds tests; none of them are
protected until this exists.
**DoD extra:** add a CI status badge to `README.md` (there is none today).

### ND-021 — LiteLLM example: make it conformant or retire it · **S**
`examples/litellm_guardrail.py:92` calls `report_result` immediately after
`decide_and_reserve`, before the gateway acts. That is a published, documented
demonstration of a two-phase-contract violation by the standard's own reference
implementation.
Options: (a) move reporting to `async_post_call_success_hook` as the file's own
docstring says production should; (b) retire the example and the doc page.
**Recommend (a)**, with a test that asserts no report is written before the
post-call hook fires.
**Answered (D1): the draft *does* cite it, and cites it honestly** — §implstatus
already calls it "not conformant as written… included as evidence that the gateway
hook point is viable, not as a conformant PEP." So the citation is accurate today
and becomes **false** the moment this ticket lands. **Take option (a), and ping core
on `0.3.6`** so §implstatus is revised in the same beat.
**Blocks:** nothing, but it is the cheapest credibility fix on the list.

### ND-024 — Remove or document vestigial schema · **S**
`0001_init.sql` still identifies as "Sutradhar M0 schema" and creates
`intake_policy`, `preferences`, `sessions` — no module in `onedoor/` reads any of
them. `push_subscriptions` is genuinely planned (ND-026), keep it.
Forward-only migrations mean these cannot simply be dropped without a `0006`;
decide between dropping them and commenting them as reserved. Rename the header
comment either way.
**Depends on:** ND-001 if both add migrations — sequence the numbers.

---

## Phase 1 — conformance + trust

*Roadmap §6 order, amended: ND-002/003 (A4) now precede ND-001 (P1), because the
reason-code rename changes what a chained audit row contains. Chaining first
means hashing a format that is about to change.* **Core assent granted (C1),
2026-08-20 — the reorder is confirmed, not proposed.**

*Second change since the survey: **E2 decoupled `ND-009` from `ND-002`.**
`approval_ref` handling introduces no new reason codes, so resumption no longer
waits on the vocabulary release and can run in parallel with it.*

### ND-002 — Unit-neutral reason codes + `aadp/0.2` protocol stamp · **M** · AADP A4
**Unblocked — E1 settled every question.**
- `CheckId.CAP_DAILY_RATE` → **`cap_rate`**; `CAP_EUR_DAY` **and** `CAP_EUR_MONTH`
  → **`cap_value`** (one code; the window moves into `ND-003`'s budget object).
- Add **`sender_mismatch`** to the enum now, so the vocabulary change is complete in
  one breaking increment. It cannot fire until `ND-005` wires the check — reserve
  the code, ship the check later.
- Extend the **report response** with an optional `reason` field (E5) — also part of
  this one wire increment.
- **Bump the protocol string to `aadp/0.2`** so the wire self-identifies its
  vocabulary.
- **From E6 (ruled):** add a **`protocol` column to `actions_audit`** and stamp it on
  every row. Document the fallback in onedoor's own docs now, ahead of `-02`: *an
  evidence row with no `protocol` value MUST be read under `aadp/0.1`.*
- **From E8 (ruled):** route every decimal and datetime through a canonical renderer —
  shortest exact form, one form for wire, storage and preimage. `str(Decimal)` is not
  it. Property test per `CONFORMANCE.md` §6.
- **From [reconcile-01]:** land the **whole receipt envelope** in this migration —
  `prev_hash`/`seq`/`row_hash`, `sig`/`key_id`/`alg`, `e_digest`/`i_digest`/`t_digest`/
  `v_digest`/`anchor_ref` — later fields NULL, so `0.4.1` and `ND-017` never re-migrate.
- **From E10 (ruled, final):** freeze `params_json` / `payload_json` **verbatim at
  ingress** — abolish the `parse → json.dumps(default=str)` round trip; the stored bytes
  are the received bytes. Generated columns (`budget_json`, receipt fields) are ACJ.
  The in-process binding receives no bytes, so its frozen form is **one** ACJ
  serialization at ingress and the row must make that provenance distinguishable.
  No `received_digest` column — the frozen bytes are stored, so the digest is derivable.
- **From E10 (ruled):** parse with **`parse_float=Decimal`**, including **policy YAML
  loading** — otherwise numeric bounds compare a Decimal against a float and the
  money-through-a-float defect reopens. Duplicate keys / NaN / Infinity / non-UTF-8 ⇒
  deny `malformed` (no new vocabulary; §decidereq already covers it).
  **Property test:** `250` / `250.00` / key-order permutations ⇒ identical canonical
  bytes and identical `row_hash`.
- **From E11 (ruled):** land the obligation surface — `obligations` on the decide
  response, `not_attempted` in the outcome vocabulary, discharge evidence **in the
  payload** (no new field; `-02` adds a RECOMMENDED `payload.obligations` convention).
  **This is conformance catch-up, not a wire break** — all three are normative in `-00`.
  Ships **dark**: see `ND-038`'s enforcement-before-emission rule.
- **Also in `0.4.0`:** `ND-039` (report outcome rework) — the enum edit alone is not
  the fix; it would record lies more precisely.
- **Test discipline (from the v3 intake):** the ACJ property test uses **generated**
  inputs — equal-value/different-spelling numbers, key-order permutations, string normal
  forms — not three hand-picked examples. Spot-checks find only the violations you
  thought of; that is exactly how the nested-`additionalProperties` defect survived two
  independent probes of the manifest artifact.
- Clean break: **no dual-emission.** Safe because reason codes are audit vocabulary;
  a PEP's behaviour is fixed by the verdict, so a `-00` PEP still denies correctly.
  The break is audit-only.
Touches `models.py`, `caps.py:139–149`, every test asserting a reason string, and
`docs/policy-reference.md`.
**DoD extra:** a test that reads a fixture DB containing old-form rows with no
`protocol` stamp and still renders them correctly under the `aadp/0.1` reading.

### ND-003 — Structured `budget` object on `PolicyDecision` · **M** · AADP A4
**Unblocked — shape pinned by E1.2, reproduced in `CONFORMANCE.md` §6.** Seven
REQUIRED fields: `dimension` ("value"|"rate"), `unit`, `window`, `limit`,
`consumed`, `remaining`, `window_resets_at`. Currency lives in `unit`, never in a
field name. All numerics are decimal strings.
Present **iff** verdict is `deny` and reason ∈ {`cap_value`, `cap_rate`}.
**Persist it on the audit row (`budget_json`), don't just return it.** Escalation
002/E7: `cap_value` collapses `cap_eur_day` and `cap_eur_month`, so without
persistence the evidence store can no longer tell a day-cap breach from a
month-cap one — a granularity regression against `0.3.5`, where the reason code
alone carried it. Today the window survives only as prose in `detail`
(`caps.py:141`), which is exactly what this ticket replaces. Core asked to confirm
this is a §evidence requirement; delivery builds it either way.
**Depends on:** ND-002 (same enum, same `0.4.0` breaking change — land together).
**Note for ND-018:** because `budget` is deny-only, the GUI's gauges need a
separate read path; they cannot be fed from the decision stream alone.

### ND-001 — Hash-chained audit entries · **L** 🔺 · Veto-parity P1
Migration `0006`: add `prev_hash` and `entry_hash` to `actions_audit`. Each row
hashes its canonical content plus its predecessor's `entry_hash`, so any deletion
or in-place edit breaks the chain. Add a `verify_chain()` walker and expose it.
**Design constraints — read before starting:**
- **Group commit.** `audit.append_buffered` / `flush` writes result rows via one
  `executemany`. A chain is inherently sequential. The chain must be computed
  inside `flush` in row order *before* the insert, or group commit must be
  refused when chaining is enabled. Decide explicitly; test both paths.
  (`CONFORMANCE.md` N2.)
- **Genesis and back-fill.** Existing rows have no hash and the table's triggers
  forbid `UPDATE`, so the chain cannot be retro-fitted. It must start at a genesis
  row that records the id of the last unchained row. Verification of a mixed
  archive must state honestly which prefix is unchained rather than reporting the
  whole log as verified.
- **Canonicalisation.** The bytes that get hashed must be defined once and
  frozen — column order, JSON key order, decimal and datetime rendering. Get this
  wrong and every later verifier disagrees. This same canonical form is what
  ND-015 signs and ND-017 addresses.
**Envelope frozen by E3 — assent granted.** Land the full shape in the `0.4.0`
migration with later fields present-but-empty, so P1 does not re-migrate:
`prev_hash`, `seq`, `row_hash` (this ticket) · `sig`, `key_id`, `alg` (ND-015) ·
`E`, `I`, `T`, `v` digests + Merkle anchor (ND-017).
- **Carry `E`/`I`/`T` as opaque content-addressed digests, never inlined
  structures.** Core's hard exception: `I`'s preimage will generalise from
  verdict-instruments to stage-attribution instruments, and inlining its structure
  would re-hash frozen rows — fatal on an append-only store. This materially
  simplifies the ticket.
**Both Response-001 gates cleared.** E8 fixed the decimal rule (shortest exact form,
uniform, wire = storage = preimage) and [reconcile-01] fixed the digest columns by
ruling — `e_digest`, `i_digest`, `t_digest`, `v_digest`, `anchor_ref`, all nullable
SHA-256 lowercase hex, NULL until `ND-017`. Full canonical form in `CONFORMANCE.md` §6.
🔺 **One new gate, from Escalation 003:**
- **E10 — `params_json` / `payload_json` are in the preimage and outside the
  canonicalisation** (`CONFORMANCE.md` N7). They are written with `default=str` and no
  `sort_keys`, so key order follows the PEP's arrival order and JSON numbers render as
  IEEE doubles. Until core rules on received-vs-normalised evidence and the canonical
  JSON form, a chained row would hash bytes that no second implementation reproduces.
  **The fix lands in `ND-002`'s row format, not here** — same "rename before you chain"
  logic as C1, one level down.
**Depends on:** ND-002, ND-003 (chain a stable row format) — **both shipped in `0.4.0`.**
**DECOMPOSED** (R030 §4): `TICKETS-ND-001.md`. Three findings worth carrying here.
**No migration is needed for the chain columns** — `0007` landed `prev_hash`/`seq`/`row_hash`
dark exactly so P1 would not re-migrate an append-only table; `0012` is an index only.
**The serialization point already exists** — `db.tx()` is `BEGIN IMMEDIATE`, and all nine
`audit.append` sites sit inside one, checked per call site. **The verifier already reports
this check**: `receipt.py::_check_chain` returns `absent` today, so `ND-001` flips one
function and the viewer changes not at all. **Group commit (N2) is decided, not deferred:**
chain inside `flush` before the `executemany`, with both paths asserted to produce identical
`row_hash` values. **RULED (R031 §1) and BUILT, C1–C5:** length-prefixing with `ABSENT` as a type tag,
specified in `docs/row-preimage.md` and cross-checked by a second implementation built
from that document. Chaining is opt-in via `chain.enable()`; `verify_chain()` reports per
region and holds `verified`/`absent`/`unverifiable`/`failed` apart. **The viewer needed no
change** — `_check_chain` flipped and the page rendered real digests, which is the
acceptance test for the single-verification rule.
**DoD extra:** a tamper test — mutate a row via a direct SQLite write with triggers
bypassed, assert `verify_chain()` localises the break to that row.

### ND-004 — Transport security: satisfy the property mandate · **M** · AADP A1
No TLS surface exists at all today. Deliver: uvicorn TLS + client-cert config,
certificate verification on the service side, principal extraction from the client
cert, deployment docs, and a test using a self-signed fixture CA that asserts an
unverified client is refused.
**Settled (E4): the mandate is on the *properties*, mTLS is the RECOMMENDED
profile.** So the deliverable is both, not either:
- onedoor **MUST refuse to serve** decide/report over a channel lacking
  confidentiality, integrity, and mutual authentication. **The test asserts refusal
  of a channel lacking the properties — not refusal of "not-mTLS".** Getting this
  test wrong is how a property mandate silently becomes a mechanism mandate.
- mTLS per RFC 9325 (BCP 195) ships as the documented, tested default.
- A mutual-auth service mesh, or the §uds local socket with peer credentials, remain
  conformant alternatives — which is why **ND-023 is no longer a mere convenience**.
**[reconcile-01]:** if `-01` §12.1 currently says "mTLS MUST", core relaxes it in
`-02`. Build to the property mandate regardless.
**Enables:** ND-005 — a sender-constrained permit needs a verified sender identity
to bind to.

### ND-005 — Sender-constrained permits · **L** · AADP A2
Bind each permit to the identity of the PEP that requested it, so possession
alone is insufficient to report. With ND-004 landed, the natural binding is the
client-certificate thumbprint; the alternative is a PEP-held key with a
proof-of-possession on report.
**Settled (E5):**
- **Binding = client-certificate thumbprint** from ND-004's mTLS, RFC 8705 style.
- **The check is at *report* time** — the permit binds the sender who will report.
- **A mismatch is refused in the decision pipeline with an audited
  `sender_mismatch` entry and a `reason` on the report response — never a silent
  transport-layer drop.** Mirrors the existing "second report → `accepted: false`"
  rule (§idem). A refused report is exactly the event the audit exists to capture.
- **Do not build DPoP.** Proof-of-possession with a PEP-held key (RFC 9449) *is*
  A10, not a step toward A2 — it belongs to ND-016 and to the terminating-
  intermediary case, which is still draft future work.
**Depends on:** ND-004. The reason code itself ships earlier, in ND-002.
**Relates to:** ND-015 (signed receipts) reuses the key-management layer built here.

### ND-008 — Downstream idempotency-key propagation · **M** 🔺 · AADP A3
`request_id` gives exactly-once *decision*. Exactly-once *effect* needs a
permit-derived key handed to the target system (e.g. `Idempotency-Key` on an HTTP
call, the equivalent field on a payment API). Derive it deterministically from the
permit, expose it on `PermittedIntent`, and thread it through the packaged PEPs —
MCP proxy first, then LangChain middleware.
**Ruled early by core (E9) — and the answer re-sizes this ticket M → L.**
- The draft specifies neither the derivation nor the header; `-02` adds both.
- The key MUST be a deterministic function of **the permit alone**, never of the
  request params (equivalent params can be re-encoded, which would break exactly the
  determinism the key exists to provide). RECOMMENDED: **`permit_id` verbatim**, or
  **UUIDv5 over `permit_id`** where the target constrains the format.
- **The field/header name is the adapter's contract, documented per adapter.** The wire
  standard does not own third-party header names.
- **A target that cannot honour the key is handled by an obligation, not by a denial or
  a caveat.** `-02` adds obligation type **`idempotency_key`**; a PEP that cannot
  discharge it **MUST NOT perform the action** and reports `not_attempted`.
- **Policy decides when exactly-once effect matters.** Where the obligation is attached
  the guarantee is enforced; elsewhere adapters MAY propagate best-effort and the docs
  say "exactly-once decision, key offered" — never "exactly-once effect". This resolves
  the overclaiming risk structurally: the strong claim is made only where it is true.
**Depends on `ND-038`.** Escalation 003/E11: core's "old PEPs are safe by construction"
holds for the standard but not for onedoor, whose PEPs have no obligation code path at
all and would silently ignore the obligation and execute.
**Note:** connectors are pluggable (`connectors/mock.py`), so the engine can only
*offer* the key. Whether the connector uses it is the adapter's contract — say so
in the docs rather than implying exactly-once end-to-end.

### ND-009 — PEP-driven resumption via `approval_ref` · **L** · AADP A6
**Re-estimated upward from the roadmap.** `approval_ref` does not exist in the
codebase — the roadmap's "field exists in the model" is incorrect
(`CONFORMANCE.md` §3.1). Full scope: add the field to `ActionRequest`, accept it on
`/v1/decide`, verify it against the `approvals` table, enforce single-use
atomically alongside the existing PDP-driven path, and keep the kill switch
winning after approval.
**Settled (E2) — and the semantics are already normative in `-00`. Build to the
draft; do not invent.**
- **Binding is by action-equivalence, not `request_id`.** A resumption is a *new*
  decide with a *new* `request_id` carrying the ref. A PEP presenting it on a
  different `request_id` is doing the required thing, not a violation. Delivery's
  escalation assumed the opposite — worth reading §idem before coding.
- **Single-use**, marked consumed when a resumed request is decided against it.
- **Expired / consumed / unknown / forged / action-mismatch / principal-mismatch
  are uniform: evaluate as though no approval had been supplied.** The action
  re-evaluates on its own merits, so a proposal-tier action just proposes again.
  **A bad ref never grants — permission stands or falls on the re-evaluation.**
- **Kill switch still wins** after a valid ref (§invariants #1, §approvals).
- Record **`approval_ref_status`** on the evidence entry — {absent, honored,
  expired, consumed, unknown, action_mismatch, principal_mismatch} — so the
  forensic distinction survives without polluting the verdict vocabulary.
- **Approvals are principal-scoped** (a gap this escalation surfaced): a ref under a
  different principal is `unknown` for the verdict, `principal_mismatch` in evidence.
**Introduces zero new reason codes ⇒ no longer depends on ND-002.** Can be built in
parallel with the vocabulary release.
**BUILT, A1–A6** (R035 §4). `TICKETS-ND-009.md`; all three §6 questions ruled by R035. Three findings, all checked against the
schema rather than assumed. **(1) The evidence field collides with the frozen preimage:**
`approval_ref_status` is a new `actions_audit` column, and it records *why an approval did
or did not authorise this action* — flipping `expired` to `honored` is exactly the edit a
chain exists to catch, so it must be **hashed**, which forces `onedoor/row-preimage/2`.
**Free today** (chaining is opt-in and off; no row has been sealed under `/1` outside
tests) and **impossible once one deployer enables it**. **(2) There is no principal:**
`session_id` is caller-supplied and unauthenticated, `decided_by_session` is who approved,
the API key is deployment-wide. Scoping a ref to `session_id` is a check an attacker
satisfies by copying a value out of the same body. Proposal: `principal_mismatch` is
reserved and never emitted until an authenticated identity exists, held by a test exactly
as `sender_mismatch` is. **(3) Action-equivalence needs a boundary:** same `action_type`
plus same resolved effect set is the reading, but effects are computed from `params`, so
the line between *same effects* and *same effects and same bounds-relevant params* is the
line between an approval that can be spent on a bigger transfer and one that cannot.
**A1/A2/A6 unblocked; A3, A4's evidence half and A5 wait on the three rulings.**
**Verified for R034's E10 note:** `params_raw` and `session_id` survive the approval
round trip, so a resumed request keeps its received-bytes provenance with no special
handling.
**DoD extra:** a concurrency test — two simultaneous resumptions with the same
`approval_ref` must yield exactly one execution.

### ND-010 — Rebuild pending intents from the audit log, not memory · **M**
Not in the roadmap; found in the source. `service/app.py`'s own docstring: *"The
service keeps the pending-intent state in memory (single-process, self-hosted
v0.3); a restart between decide and report leaves the honest 'intended,
unconfirmed' row in the audit log, and v0.4 rebuilds intents from that row instead
of memory."* That rebuild has not landed. Today a PDP restart strands every
in-flight permit.
The `exec_intent` row plus `cap_reservations` already hold everything needed.
**Why it belongs in P1:** it is a promise the code makes to its reader and does not
keep, and in-memory intent state blocks the multi-replica goal (ND-019) outright.
**Green-lit by core (C2)** — not wire-observable, so it stays delivery's call.
**One binding constraint from core:** reconstructed intents are **the same durable
rows** (`exec_intent` + `cap_reservations`), **not new ones** — no new evidence
identity, no budget re-reservation. §invariants #9 (intent precedes action) and
§idem (no re-reserve on a known request) both bind. Reconstruct in place; don't
double-count.
**BUILT, R1–R5** (R033 §4). `TICKETS-ND-010.md`. Two findings carried here.
**A `PermittedIntent` cannot be faithfully rebuilt**: `rationale`, `cost_eur` and
`session_id` are stored nowhere in `actions_audit`, and a rebuild passing
`cost_eur=Decimal(0)` would be a default that looks like a fact. So a rebuilt permit is a
distinct type carrying provenance to its rows, not an `ActionRequest`.
**A naive rebuild silently corrupts E10 provenance**: `frozen_params` re-serialises when
`params_raw` is None, so a post-restart result row would record `serialized` for bytes that
arrived `received`. The fix has a precedent — `append_expiry` already inherits the intent
row's bytes and provenance verbatim.
**And a constraint from `ND-001`, first met here:** do **not** add columns to
`actions_audit` for convenience. The preimage is frozen — a hashed column is a new
preimage version, an excluded one is a field an attacker can edit without breaking the
chain. **§7 RULED (R033 §3):** a rebuilt row's `created_at` is its own write time, never
backdated — the ledger records when the ledger learned it, lineage travels by reference,
and a rebuilt record never impersonates a live one. `RebuiltIntent` therefore has
`requested_at` and **no** `created_at`.
**DoD extra:** a restart test — decide, drop and rebuild the app object, report,
assert the report is accepted and the reservation settles. Assert the audit gains
**no** new rows and the reservation total is unchanged across the restart.

---

## Phase 2 — product surface

### ND-015 — Signed decision receipts (Ed25519) · **L** 🔺 · P2 / AADP A2, A10
PDP signs each verdict over the canonical form frozen in ND-001; PEPs and auditors
verify. Needs a key-management story (generation, rotation, distribution,
compromise) — the part that is easy to under-build.
**BUILT, K1–K5** (R038 §5). `TICKETS-ND-015.md`; all three §5 questions ruled by R038. Custody is pre-settled by R037 (private key
deployer-supplied and never in repo/DB/receipt; `key_id` a DERIVED fingerprint, never
assigned; unknown key ⇒ **unverifiable**; rotation append-only, public keys are evidence;
signing per-row over `row_hash`). **Adds no hashed column and needs no preimage version** —
`sig`/`key_id`/`alg` exist dark since `0007` and are already `EXCLUDED` with the reason.
**Three findings.** *(1) The keyring is a trust-anchor problem, not a storage one:* a
signature verified against a public key found in the same store as the data it signs proves
internal consistency, not authenticity — an attacker with write access supplies both halves,
which is R028's tautology-dressed-as-a-check one layer up. Append-only triggers do not close
it (a keyring must accept INSERTs or rotation is impossible) and the chain does not either.
*(2) This is onedoor's FIRST crypto dependency* — checked: the runtime deps are pydantic,
pydantic-settings, pyyaml, tzdata, and the stdlib has no Ed25519. But the `ND-040`/U1 bar is
met differently: U1 refused a dependency because **IDNA output changes between versions**,
whereas **Ed25519 is deterministic per RFC 8032** — pinning here is supply-chain, not
determinism. *(3) The no-key case is two cases:* `sig` NULL is **absent** (signing not in
operation), a signature the verifier cannot check is **unverifiable**, and collapsing them
would report reassurance. **Three questions** (§5): can a store ever say `verified` on its
own; is signing an **X-6** alarm dependency (hard requirement vs extra); does `alg` record
the algorithm only or the library too. K1's table shape, K2 and K4 unblocked.
**Depends on:** ND-001 (canonical form), ND-005 (key layer).

### ND-016 — Action-bound signed permits · **M** 🔺 · AADP A10 (draft future work)
ND-005 extended cross-domain, for terminating intermediaries.
🔺 **Core:** this is named *future work* in the draft. Delivery does not implement
ahead of the standard. Core decides whether `-02` normalises it.

### ND-017 — Content-addressed re-derivable receipts + Merkle anchoring · **XL** 🔺 · P3
**BUILT, M1–M5** (R040 §5) — **the crypto epic is closed.** `TICKETS-ND-017.md`.
**F1 (R041):** the degenerate empty-path inclusion guard, refused **before any Merkle
computation**, with S-EP1/S-EP2 and the positive size-1 vector. Credit recorded to
`draft-schrock-ep-authorization-receipts-12` §7.3. **Both vectors are constructible and
both already failed** against the vendored construction — three independent reasons,
measured — so this is defence in depth at the boundary we own, not a patched hole, and
the record says so.
The four `E`/`I`/`T`/`v` preimages are proposed for sign-off before bytes freeze, written
to the vendored manifest's own scheme rather than invented (read from
`manifest.schema.json`; the shipped `t_digest` `4f53cda1…` is SHA-256 of `[]`, confirming
`T` is a canonical *declared closure*). All four are digests over `canonical_bytes`, so
**no concatenation appears and `len8` is not reached** — stated rather than left implied.
Received bytes enter as a **digest hashed verbatim**, never inlined, which also lets a
deployer hand over a receipt without handing over the request body.
**The export finding:** a third party with only the published root and one receipt needs
the leaf index, tree size and audit path — **none of which is in `actions_audit`**, and
`anchor_ref` names an anchor but cannot carry a proof. So the thing that travels is an
**export**, not a row, and acceptance is a script run in a directory holding those two
files and nothing else. **X-8 fixes the order:** verify the range, compute the root, seal
the anchor, and only then write `anchor_ref` back — an anchor over a broken chain would
publish a root certifying damage, permanently and in public. **Three questions** (§5):
are the four preimages right (`T` least certain); is `anchor_cadence` inside `I` intended
(it makes a cadence change move `i_digest` for every row sealed afterwards); does a root
found in the store report `self_consistent` — R038 §1 one level up, and the second time
this product refuses to vouch for itself. **No preimage version:** the four digest
columns and `anchor_ref` have been dark since `0007` and are already `EXCLUDED`.
Paper 3's verdict manifest (`E`, `I`, `T`, `v`) on each decision, periodic Merkle
root anchored to an external transparency log. This is what *passes* Veto rather
than matching it: their receipts prove "the PDP said this"; these let anyone
recompute the decision and check archive integrity independently.
**Reference shape delivered and checked** (Escalation 004): `rederivable-manifest/`
conforms to Response 002; `canonical.py` is **vendored directly as `ND-001`'s
canonicalisation module** rather than reimplemented — same bytes by construction.
**Four constraints, all in the anchoring layer.** Three carried in from the
Escalation-004 check; the fourth is normative from Response 007.
- **Anchor only what you have re-verified (R007, `-02` change item 22).** Before
  computing and publishing an anchor root, the implementation **MUST re-verify the
  receipt set it covers** — chain verification *and* manifest verification over the
  actual bytes at hand. A root derived from bytes that fail verification **MUST NOT
  be anchored**; the failure is surfaced, not the root. Cheap, because anchoring is
  periodic. **Adopted from delivery's `.gitattributes` reproduction:** a CRLF-corrupted
  checkout silently moved the anchor root from `4e49f63a17cf…` to `576019221d5d…`
  while every *internal* consistency check still passed, so the corrupted root would
  have been published to an external transparency log with full confidence. The rule
  generalises past CRLF to any local byte corruption — encoding, disk, a partial
  vendor update. Binds the forensics session's P2-05/P3 anchoring too; core relays.
- **E12/E13 — `merkle_root` must be replaced before anything is anchored.** The
  shipped construction has the duplicate-last-node collision *and* no leaf/internal
  domain separation. RFC 6962 patch written and exhaustively tested:
  `patches/merkle_rfc6962.py`.
- **Inclusion proofs are missing entirely.** A root alone lets a holder of the whole
  set recompute it; it does not let a third party check *their* receipt — which is
  the claim §3.2 makes. `inclusion_proof` / `verify_inclusion` ship in the same patch.
- **E14 — record the Unicode version** in the receipt and fold it into instrument
  identity, or the re-derivability guarantee is runtime-scoped.
**Decompose before starting.** Preimage definitions (what constitutes `E` for an
onedoor decision) need core sign-off at decomposition. **Carry the re-verify-before-
anchor rule into the decomposition** — it is a constraint on the anchoring component's
interface, not a test to bolt on afterwards.
🔺 **Core owns the whether and why.** Delivery owns how and when.

### ND-018 — GUI: live monitor · **XL** · roadmap §4.2
Decision stream over SSE, budget gauges (reading ND-003's `budget` object),
approval queue, guarded kill switch, audit explorer with a *re-derive this verdict*
button once ND-017 lands. React SPA over the existing FastAPI service, RBAC reusing
the decide/admin split, shipped as `onedoor[ui]`.
**Sequence:** monitor before policy studio — highest visible value, read-only,
lower blast radius.
**Depends on:** ND-003 for machine-readable budget state.

### ND-019 — Postgres backend with linearizable budget state · **L** · roadmap §5
Pluggable store behind the current SQLite implementation so a logical PDP can run
as several replicas. The atomicity guarantees in `caps.py` currently rest on
SQLite `IMMEDIATE` transactions; the concurrency tests
(`test_concurrency.py`) must pass identically against both backends.
**Depends on:** ND-010 — in-memory intent state defeats replicas regardless of the
store.
**Migrated in by `ND-036`:** the old roadmap paired this with **Alembic migrations**.
onedoor's forward-only `.sql` chain is deliberate and cheap; adopting Alembic is a
decision this ticket has to make explicitly rather than inherit, and the
migration-number register above only works while the chain stays linear.

### ND-020 — GUI: policy studio · **XL** · roadmap §4.1
Visual editor for `policies.yaml`, effect catalog, policy diff against the
content-hash history, starter templates. Gains most of its value after ND-028
(simulation) can preview a change's blast radius.

---

## Phase 3 — reach + enterprise

Held at epic granularity; decompose when a phase-2 slot frees up.

| # | Item | Size | Note |
|---|---|---|---|
| ND-022 | PEP `fail_static` / `fail_open` on PDP unreachability (A7) | M 🔺 | At 0% — `test_fail_soft.py` covers connector failure, a different thing. Core: is the default `fail_static`? |
| ND-023 | Unix-socket binding for same-host PEPs (A8) | S | **Reclassified after E4.** With A1 written as a *property* mandate, a UDS binding with peer credentials is a **conforming transport profile**, not just a convenience — it is how a co-located PEP satisfies A1 without certificates. Still cheap once ND-004 factors the transport layer; now worth more. |
| ND-026 | Finish web-push delivery; add email and a mobile approval path | M | `push_subscriptions` schema exists, delivery unwired — Tier-3 approvals are Slack-only today |
| ND-027 | Unit-neutral budgets (tokens, calls, custom dimensions) | L 🔺 | Generalises ND-003's object; core owns the dimension vocabulary |
| ND-028 | Policy simulation / what-if against recorded traffic | L | Reuses the audit log; high value, no standard coupling |
| ND-029 | GitOps policy: version control, CI validation, staged promotion | M | Content-hash snapshotting already makes this natural |
| ND-030 | `isolate` obligation with a real isolation PEP (A5) | XL 🔺 | Needs a micro-VM/container PEP; largest unstarted conformance item |
| ND-031 | Broader PEP catalog: egress proxy, Envoy/Kong plugin, K8s admission, OpenAI/Anthropic native, AutoGen, CrewAI, **coding-agent hook adapter** (e.g. Claude Code `pre_tool_use` consulting the decision service — the dev-workstation doorway) | XL | Split per adapter. Coding-agent hook migrated from `ROADMAP.md` by `ND-036`. |
| ND-032 | Compliance evidence packs (EU AI Act, ISO/IEC 42001) from the audit | L | Differentiated enterprise feature; rides on re-derivability |
| ND-033 | SIEM export to Splunk/Datadog | M | OTel is already partial (`service/telemetry.py`) |
| ND-034 | Identity composition (WIMSE / OAuth agent identity) | L 🔺 | Standards-coupled positioning; core owns the framing |
| ND-035 | Sliding-window and per-principal rate limits beyond `daily_rate` | M | |
| ND-039 | **Report outcome vocabulary** — replace `report_result(..., ok: bool)` with a four-value outcome (`success\|failure\|timeout\|not_attempted`), thread it through both packaged PEPs and `/v1/report`, and make reservation settlement outcome-dependent | M | **New, from Escalation 005 (`CONFORMANCE.md` A4b).** Live conformance defect: the report API has no outcome parameter, so `not_attempted` and `timeout` collapse to `failed` — the audit asserts an attempt that never happened, and the reservation is settled unconditionally, **charging budget for an action that never occurred**. **Lands in `0.4.0`, before `ND-038` emits any obligation.** **Ruled (R005):** `success`/`failure`/`timeout` → settle; **`not_attempted` → release, as an AUDITED event** (symmetric with `append_expiry`, never a silent adjustment). `/v1/report` must accept the wire `outcome` field — already normative in `-00`, so this is catch-up, not a break. |
| ND-038 | **Obligation machinery** — obligation envelope on `PermittedIntent`, registry check, **PEP-side unknown-obligation fail-closed in both packaged PEPs**, discharge evidence on the report, `not_attempted` outcome | L 🔺 | **New, from Escalation 003/E11 (`CONFORMANCE.md` N6).** onedoor has none: all five uses of "obligation" in the package are prose. §obligations' fail-closed guarantee is a property of *conformant* PEPs, and onedoor's would silently ignore an obligation and execute. **`ND-008` (A3), `ND-030` (A5), and `ND-037` (A9a) all depend on this** — it is the shared substrate the roadmap made invisible by listing them as three unrelated items. Promote into P1 alongside `ND-008`. **Core constraints (R003):** **(0)** *report-path completeness first* — `ND-039` lands before this emits anything, or a PEP that correctly refuses an obligation drains the tenant's budget for an action that never ran (Escalation 005); **(1)** *enforcement before emission* — the PDP MUST NOT attach any obligation beyond `report_result` in a release whose own packaged PEPs do not yet fail closed on unknown types, so the reserved surface **ships dark** during any gap; **(2)** *§implstatus discloses the gap now*, in the `0.3.6` ping, not at `0.5.0`. |
| ND-037 | Obligation-type registry hygiene (A9a) | S | **Blocked on ND-038.** Core's B3 called this checkable, and it is — but neither duty (emit only registered types, enforce unknown-obligation-fail-closed) can be *enforced* against machinery that does not exist. Small once `ND-038` lands; not before. |
| ND-036 | Reconcile the repo's `ROADMAP.md` with this backlog | S | **Done, `0.3.6`.** The public `ROADMAP.md` is now a pointer to `BACKLOG.md` + `CONFORMANCE.md` plus the material that does not go stale (goal, strategy, non-goals, the session-aware-trust research track, the v1.0 criterion). **Four work items lived only in that file and are migrated here rather than deleted** — `ND-040`, `ND-041`, `ND-042`, and the research track, which stays on `ROADMAP.md` because it is explicitly unscheduled and not a delivery ticket. Closes `CONFORMANCE.md` N4. |
| ND-040 | **URL-typed parameter canonicalization before effect matching** | L 🔺 | **Migrated from `ROADMAP.md` by `ND-036`; it existed in no other ledger.** `param_effects` full-matches a regex against a parameter's *string* form — the right shape for effect derivation, the wrong parser for a URL. `https://(pay\|bank)\.example\.com/.*` is defeated by percent-encoding, a `user@host` prefix, IDN homographs, a trailing-dot host, case, and open redirectors; `experiments/aliasing_benchmark.py` already prints 0/4 on evasive cases and `tests/guardrail/test_scopegate_regressions.py` exists. A URL-typed matcher must canonicalize first (scheme normalization, IDNA, host lowercasing, explicit subdomain semantics, CIDR awareness) and **deny on canonicalization failure**, so a parse differential is a denial rather than a bypass. Prior art to read and cite rather than reinvent: `scopegate` (Apache-2.0, D. Mellafe Zuvic) — a scope gate must interpret a target at least as strictly as the networking stack that will later connect to it. **RULED (R013): `malformed`, and no new vocabulary.** A URL parameter is *received* data and E10 already routes unparseable received structures to `malformed`. Canonicalize first; deny `malformed` on canonicalization failure. **Condition:** record the canonicalization failure **distinctly in evidence** (an evidence field, not a wire code) so audit separates malformed-JSON from malformed-URL; `sender_mismatch` stays the only new code in `aadp/0.2`. `-02` item 23. Verified: `CheckId.MALFORMED` already exists and is already emitted by the total form of `decide_and_reserve`, so this costs onedoor no new code either. **Placement ruled (R011): `0.4.x`, immediately after the current `0.4.0` scope.** `0.4.0` stays `ND-002` + `ND-003` + `ND-039` — un-replanning a release under a fresh finding is how scope drifts — **and the limitation is disclosed now**, in `CHANGELOG.md`'s known-gaps section, naming the evasion classes and citing `aliasing_benchmark.py` as the measurement. **Scope corrected while writing that disclosure:** the benchmark's evasive set is 4 cases, but only **three are URL-shaped** (redirector, IP literal, percent-encoded host); the fourth is a base64-obfuscated shell command that canonicalization does not touch. Citing 0/4 as evidence for the URL gap would have implied this ticket closes all four. It closes three, and the shell residue is disclosed separately and ticketed as `ND-048` (R012 §2: honest inventory gets a number so it cannot age out). Core's framing: *an evidence vendor's posture is that known evasions are published, not discovered.* **BUILT (U1–U5), unreleased.** `urlcanon.py` + `opaque_hosts.py`, migrations `0010`/`0011`, tests in `test_urlcanon.py`, `test_url_rules.py`, `test_opaque_hosts.py`, `test_param_effects_compat.py` (R026's corpus) and `test_aliasing_acceptance.py`. Benchmark **L3 evasive 3/4**, `innocent-ok` 3/3, `named` 5/5, `generic✓` 4/4, with `ND-048`'s case asserted still-failing. Decomposition and outcome in `TICKETS-ND-040.md`. |
| ND-041 | Effect labels for unanticipated actions | S | **Migrated from `ROADMAP.md` by `ND-036`.** An action carrying a label with no matching effect policy draws on no shared budget. Whether that is fail-open **needs measuring before it needs fixing** — the ticket is the measurement, not a change. |
| ND-042 | Assisted effect-label authoring from MCP tool schemas | M | **Migrated from `ROADMAP.md` by `ND-036`.** Propose candidate effect labels from tool names, parameter names and descriptions for a human to ratify. **Never auto-applied, and never a model in the decision path** — proposal only, with the ratifier recorded on the policy version. |
| ND-043 | MCP streamable-HTTP transport for the proxy (stdio remains) | M | **Migrated from `ROADMAP.md` by `ND-036`.** |
| ND-044 | Graduate the LiteLLM and LangGraph adapters from `examples/` to packaged integrations | M | **Migrated from `ROADMAP.md` by `ND-036`.** Half of the old roadmap's v0.5 entry — "with intent carried to post-call hooks so the audit records true outcomes" — **is already done** (`ND-021`, `0.3.6`); what remains is the packaging move to `onedoor/integrations/` with the support commitment that implies. `CONFORMANCE.md` deliberately calls the LiteLLM row *example, conformant* rather than *packaged* until this lands. |
| ND-045 | OIDC/JWT authentication for the decision service | M | **Migrated from `ROADMAP.md` by `ND-036`.** API-key auth with the decide/admin split ships today; the roadmap promised OIDC "in v0.4" and nothing carried that forward. **Relates to `ND-004`/`ND-005`** — transport-level identity and request-level identity are different layers and should not be conflated. |
| ND-046 | Documentation site | M | **Migrated from `ROADMAP.md` by `ND-036`.** Concepts (the ordered pipeline and *why* that order), policy reference, an integration guide per surface, deployment/operations, threat model. Most of the raw material exists under `docs/`. |
| ND-047 | Audit retention policies | M 🔺 | **Migrated from `ROADMAP.md` by `ND-036`.** 🔺 **Not a simple deletion feature.** `actions_audit` is append-only by trigger and, from `ND-001`, hash-chained: any retention scheme must say what happens to the chain across a pruned prefix, or verification of a retained archive silently becomes unverifiable. Core-gated for that reason. **Do not start before `ND-001`.** **Parked (R011)** with the constraint kept: core has the pruned-prefix/chain interaction under change-list watch and it may surface in `-02`'s evidence-retention prose. No delivery action now. |
| ND-048 | **Indirect / obfuscated command construction defeats parameter rules** | L 🔺 | **Ticketed on core's instruction (R012 §2)** so it cannot quietly age out of the disclosure. `experiments/aliasing_benchmark.py`'s fourth evasive case is `bash -c "$(echo <base64> | base64 -d)"`: the governed effect is real, the parameter carries no matchable literal, and **no deterministic parameter rule catches it** — the benchmark says so in its own output, scoring 0/4 with the shell case included at every layer. **`ND-040` does not close this**; URL canonicalization is a different mechanism, and conflating them would let the disclosure imply a fix that does not exist. Disclosed in `CHANGELOG.md` as an open gap. 🔺 Core owns the framing: the benchmark calls this "the residue a measured, escalate-only semantic layer would own", which touches A9b's research-coupled territory. Delivery does not start this without a ruling on what a conformant answer even looks like. |
| ND-049 | **Suite runtime: diagnosed, accepted cost on Windows** | S | **Ticketed per R020, and diagnosed rather than left as "observed".** Measured: the `db` fixture costs **81 ms** (57 ms `Database.init()` over 8 migrations + 24 ms `load_file`), so ~215 tests floor at **~17 s**. A clean local run took **28 s**; earlier runs took **185–365 s**, one of them spending **82 s in a single fixture setup** doing work that costs 81 ms in isolation — and the slow tests **differ completely between runs**. Non-reproducible, Windows-only. **CI on Linux is stable at 65–73 s across four runs**, which is the number that governs the project. **Verdict: environmental, not algorithmic — an accepted cost, not a defect.** The most likely cause is real-time AV scanning of the thousands of short-lived SQLite files created under `tmp_path`; that specific cause is **unconfirmed** and is not claimed. Revisit only if CI moves. One real fix already landed in W4: two whole-repo assertions walked `.venv` (10,788 paths, ~6 s per call, twice per run) and now prune in place (199 files, ~0 s). |
| ND-050 | **An envelope-validation `malformed` denial writes no audit row** | S 🔺 | **Ticketed on core's instruction (R027 §2)**, found while building `ND-040`/U3 and recorded as **pre-existing: present in `≤0.4.0`, not introduced by `ND-040`.** `decide_raw` denies a request whose envelope fails validation *before* a policy or an `ActionRequest` object exists, so there is nothing to `audit.append` against: the returned `ActionResult` carries no `audit_id` and the ledger has no row. **Severity: low blast radius, high principle.** Low, because the action does not happen — the denial is correct and the caller is told; nothing is mis-permitted, and the affected requests are by definition ones the engine could not parse. High, because *"the audit log is append-only — decisions, results, denials, dry-runs, and kill-switch blocks"* is a claim this repository makes in its README, and one class of denial is silently outside it. An operator watching for a spike of malformed requests has nothing in the evidence store to watch, and a receipt-based product whose ledger omits a category of verdict has a gap in exactly the surface it sells. Note the asymmetry `ND-040` created and did not cause: a malformed **URL** now writes a row with `malformed_kind='url_canonicalization'`, while a malformed **envelope** writes none — which is why migration `0010` names only the value the code emits rather than inventing a `request_validation` one for code nobody wrote. **The fix is not free**: appending needs a row shape for a request that failed to parse (what is `action_type`? what are `params`?), and E10's received-verbatim discipline says the unparseable bytes are exactly what must be frozen — so this is a small ticket with a real design question inside it, not a one-liner. |
| ND-051 | **The onedoor receipt viewer (oneview skin)** | M 🔺 | **Declared by R028 §4**, Phase-B launch asset, built **before** the crypto epic resumes. `python -m onedoor.viewer` reads a store and emits one static, read-only HTML page: the decision-receipt card with deny-with-budget as hero, plus the tail of verdicts. Spec and reference mockup in `docs/oneview/`; decomposition in `TICKETS-ND-051.md`. The structural rule from the forensics channel binds it: **one verification, and the viewer does not own it** — `onedoor/guardrail/receipt.py` is the single implementation and the viewer renders its output. **Two findings shaped the build:** there was no receipt verification and no CLI to call, so the requirement is met by creating exactly one implementation outside the viewer; and the mockup's chain block cannot be rendered truthfully in `0.4.1` because `row_hash`/`prev_hash`/`seq` are dark until `ND-001`, so it renders the **absent** state naming the ticket. Four outcomes in a UI: verified · absent · unverifiable · failed, with unverifiable as loud as failed. |
| ND-052 | **The Policy Studio — describe your world, ratify your rules** (EPIC) | XL 🔺 | **S1 DECOMPOSED** (R042 §5): `TICKETS-ND-052-S1.md`. Two rulings arrived with it and are
built to, not rediscovered: **a backtest writes nothing to the decision ledger, ever** —
it borrows the ledger's witness by citing the sealed chain, so *the ledger vouches for the
backtest, never the reverse* — and **day one resolves as a hashed
`ledger_provenance: live | fixture`** on that receipt, with a shipped fixture ledger that is
mechanically real and declares itself synthetic. **Two findings.** *(1) Dry-run is not the
isolation:* the obvious implementation writes an audit row per replayed action **and
reserves budget**, because `decide_and_reserve` is check-and-reserve — a backtest of
yesterday's traffic would consume today's caps. The isolation is a **separate store**, with
the real ledger opened read-only, asserted by a test that no audit row and no cap counter
moved. Worth stating because the wrong implementation produces right answers and pollutes
quietly. *(2) `cost_eur` is not stored* (the `ND-010` finding, landing again): defaulting it
to zero would understate every cap denial the candidate policy would have produced, in the
direction of reassurance. **Three questions** (§6): how a replay obtains `cost_eur`; whether
`ledger_provenance` needs a third value for a partly-chained store; whether the fixture
ledger ships in the wheel. B1 unblocked.
**RE-SEQUENCED (R036) by Shamik's decision, recorded as a principal's call rather than a delivery judgment: the Studio is a PRE-LAUNCH epic**, demo-grade, opening the day `ND-017` closes — superseding the design note's *after the epic, no code before launch* line. The five-principle constitution is unchanged and still binds every sub-ticket; only the *when* moved. **Build order is normative** — the deterministic spine first and the model last, and launch pressure is the reason that ordering exists rather than a reason to skip it: **S1** backtest engine (replay a candidate policy against the real ledger, dry-run, zero LLM — the flourish that needs no model); **S2** ratification ceremony (diff, canonical form, the hash becoming `version_hash`, receipt on signing); **S3** policy canvas (plain-English meaning *derived from the artifact*, per principle 2); **S4** coverage map (the honest gap as a first-class element, principle 4); **S5** one finance/payments template pack; **S6** the LLM proposer LAST, landing on a proven spine. **Two gates.** The Studio **never gates the launch** — if a sub-ticket slips, launch ships without it and the vision slide stands in; no date moves for it. And the demo bar is separate from the ship bar: S1–S4 demo on real artifacts, and **S6 demos only if its output is real, its derivation receipted, and its limits stated** — a Studio demo that faked a proposal would cost more than the Studio earns. **Ticketed on R029's instruction** from `docs/from_core/Policy_Studio_Design_Note_2026-08-22.md`, elevated by Shamik from a GUI-epic component to a **core product feature**. Sequenced **after the crypto epic** (`ND-001` → `ND-015` → `ND-017`); **no Studio code before launch** — one labelled roadmap slide, nothing more. The design note's §2 is a **constitution that binds every sub-ticket**, and each of its five principles is a programme rule wearing product clothes: (1) *the proposer is never the enforcer* — the LLM emits a candidate document and is structurally outside the decision path, permanently, with only a human-ratified artifact hashed into `version_hash` ever active; (2) *the explanation derives from the artifact, never the model's memory* — X-11 for policies; (3) *adjustable parameters are the review surface and defaults are fail-closed*, with **R027's rule binding the generator**: it may never emit a rule whose safety depends on an optional second declaration — the ND-040/U4 defect, promoted to a constraint on a component that does not exist yet, which is the programme working; (4) *non-coverage is stated, never silent* — the dark-surface list is the three-outcome rule applied to drafting, and a policy set that does not declare its gaps is an E11 violation in product form; (5) *the derivation gets a receipt* — description frozen as received bytes, model + prompt + template pack recorded as the instrument, proposal/edits/ratification chained. **Acceptance posture (§5), and it is unusually strong: principle violations are CI failures, not review notes.** A proposal whose safety depends on an optional declaration must **fail a test**, not attract a comment. The generator is benchmarked like every other instrument on the aliasing-benchmark pattern — published cases, **published misses**. It ships when the five principles are enforced structurally, or it does not ship. **Dependencies:** the backtest flourish requires the append-only ledger (have it) and dry-run replay (have it); the ratification receipt requires `ND-001`'s chain, which is why the sequencing is not negotiable. Competitive note from §4 is core's and not delivery's to restate. |

---

## Migration-number register

| Number | Ticket | Status |
|---|---|---|
| `0001`–`0005` | shipped in `0.3.5` | in `main` |
| `0006` | **`ND-024`** — retire vestigial schema | **landed** `ebdef05`, `0.3.6` |
| `0007` | **`ND-002`** — `0.4.0` row format: `protocol`, `budget_json`, `outcome`, and the full receipt envelope (`prev_hash`/`seq`/`row_hash`, `sig`/`key_id`/`alg`, four digests + `anchor_ref`) landing **dark** | **written**, `0.4.0` |
| `0008` | **`ND-002`/R019** — `policy_versions.snapshot_schema`, so a content-hash change is attributable | **written**, `0.4.0` |
| `0009` | **`ND-002`/W7** — `params_provenance` / `payload_provenance`, so received-verbatim is distinguishable from PDP-serialized | **written**, `0.4.0` |
| `0010` | **`ND-040`/U3 · R013** — `actions_audit.malformed_kind` / `canon_schema`, so a `malformed` denial says which malformed it was and under which canonicalization | **written**, `0.4.x` (ND-040) |
| `0011` | **`ND-040`/U4 · R025** — `actions_audit.opaque_class`, so a verdict that rests on a declared opaque-host class names which class and which version of it | **written**, `0.4.x` (ND-040) |
| `0012` | **`ND-001`/C2** — a `UNIQUE` index on `actions_audit.seq`, so the database refuses a duplicate chain ordinal rather than leaving the ambiguity to the walker. **Index only; the chain COLUMNS already exist** from `0007`. | **written**, `0.4.x` |
| `0013` | **`ND-009` + R035 §1** — `approval_ref_status` (**hashed**, forcing `onedoor/row-preimage/2`) and `preimage_version` (an **excluded**, self-authenticating hint that lets `verify_chain` walk version transitions on live chains) | **written**, `0.4.x` |
| `0014` | **`ND-015`/K1** — the signing keyring: append-only public keys with derived `key_id` fingerprints, so rotation grows the ring and old receipts verify forever | **written**, `0.4.x` |
| `0015` | **`ND-017`/M2** — the anchors table: published Merkle roots with their tree size and sealed range, so an anchor is a row rather than a note. **`anchor_ref` stays dark — it cannot be written on an append-only table**, so membership resolves by range | **written**, `0.4.x` |
| `0016` | **`ND-052`/S1-B2** — the backtest receipts table: the Studio's own, append-only, holding a run's policy digest, cited range, provenance and divergence. **Never touches `actions_audit`** — a backtest proves it saw real data by citation, not by writing | **claimed**, not yet written |
| `0017`+ | unclaimed | — |

Forward-only migrations mean a collision is a merge conflict that cannot be resolved by
renumbering after the fact. Claim a number here before writing one.

## Sequencing notes

**Phase B, from R028/R029:** `ND-051` (the viewer) is current work and comes **before**
the crypto epic resumes. `ND-052` (the Policy Studio) is sequenced **after** the crypto
epic and has **no code before launch** — its design note is a constitution, not a
backlog of tasks, and the ratification receipt it promises needs `ND-001`'s chain to
exist first.

**P1 order:** ND-025 → ND-021 → **ND-002 + ND-003 together as one `0.4.0`** →
ND-001 → ND-010 → ND-004 → ND-005 → ND-008. **ND-009 runs in parallel** from any
point after `0.4.0` — E2 removed its dependency on the vocabulary change.

Both deviations from roadmap §6 now have core's assent (Response 001):

1. **A4 before P1 — assent granted (C1).** Chaining first means freezing a hash over
   a row format that ND-002/ND-003 are about to change, and the audit table is
   append-only, so the old rows can never be re-chained. Rename first costs nothing;
   rename second is a permanent seam at the exact point tamper-evidence must be
   strongest.
2. **ND-010 pulled into P1 — green-lit (C2).** Not a roadmap item. It is an unkept
   promise in the shipped code and a hard blocker on ND-019.

**Not delivery's, and not to be picked up:** the multi-dependency trust base (A9b —
research-coupled), DPoP / A10 (draft future work), and lifting the T-set into the
wire (core's call). Implement the §evidence floor only.

Everything else follows §6. The crypto epic (ND-001 → ND-015 → ND-017) stays
sequenced as a single arc with its design frozen up front; per the brief it is not
to be quietly deprioritised, and splitting it across phases is safe only if the
receipt entry shape is designed once at ND-001.

## Release mapping

| Release | Contents | AADP status change |
|---|---|---|
| `0.3.6` | ND-021, ND-024, ND-025, ND-036 | **Shipped 2026-08-21.** LiteLLM enforcement point ❌ → ✅ *example, conformant*. §implstatus revised. Known-evasion disclosure for `ND-040` published with the release. |
| `0.4.0` | ND-002, ND-003, ND-039 — **shipped 2026-08-22** | **Breaking for archives and readers, not for PEP enforcement.** Reason codes → `cap_rate`/`cap_value`; `sender_mismatch` reserved; `budget` object added and persisted; `reason` on the report response; protocol → **`aadp/0.2`**; `protocol` column on the audit; report outcome reworked to the four-value vocabulary with outcome-dependent settlement (`ND-039`); obligation surface landed **dark** (conformance catch-up, already normative in `-00`); **receipt envelope migrated with later fields present-but-empty** so `0.4.1` does not re-migrate. A4 closed. Ping core. |
| `0.4.1` | ND-001, ND-010 | P1 (Veto parity, partial). Tamper-evidence claim becomes true. Gated on **E8**. |
| `0.5.0` | ND-004, ND-005, ND-038, ND-008, ND-009 | A1, A2, A3, A6, A9a closed. The largest conformance jump. **Breaking unless E11 reserves the obligation surface in `0.4.0`** — `not_attempted` and discharge evidence are wire-observable. Core handles §implstatus centrally — ping on release. |

Version↔draft mapping is maintained in `CONFORMANCE.md`'s header and must be
updated in the same PR as any release.
