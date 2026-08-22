# Changelog

onedoor is the reference implementation of the AADP Internet-Draft
(`draft-saha-aadp`). Per-requirement conformance status, gaps included, lives in
[CONFORMANCE.md](CONFORMANCE.md); the ticket-by-ticket plan is in
[BACKLOG.md](BACKLOG.md).

## 0.4.1 — 2026-08-22

**Additive. Nothing existing changes meaning.** New opt-in policy vocabulary and two
forward-only migrations; every rule you have deployed matches exactly what it matched
under `0.4.0`, which is asserted rather than intended (see the compatibility corpus
below). No wire-observable change: no new reason codes, no changed verdict shapes, no
signature changes. A `-00` enforcement point is unaffected.

**Upgrading:** run the engine once to apply migrations `0010`–`0011`. Nothing else.

### Added — `ND-040`: URL-valued parameters are matched as URLs

A `param_effects` rule may now declare a `url:` block instead of a `pattern:`, and
matching happens against the **canonicalized target** rather than the parameter's
string form. Opt-in: a rule without a `url:` block matches exactly what it matched
before, and `tests/guardrail/test_param_effects_compat.py` asserts that against every
pattern shipped in this repository plus generated inputs — no deployed policy changes
meaning because the engine was upgraded.

```yaml
param_effects:
  - param: url
    add_effects: [money.egress]
    url:
      hosts: [bank.example.com]      # canonicalized on both sides
      include_subdomains: false      # explicit, never implied
      cidrs: [203.0.113.0/24]        # for IP-literal targets
      schemes: [https]
      opaque: {builtin: true}        # hosts whose target cannot be known
```

**Correcting the mechanism sentence in the `0.4.0` disclosure.** That entry said the
three URL-shaped evasions would be closed by canonicalizing first. Building it showed
that is true of **one** of them. The promise stands and is kept; the description of
how was wrong, and a disclosure that keeps a wrong mechanism to avoid an edit is not
a disclosure register working:

| Evasive case | What actually closes it |
|---|---|
| `https://bank%2Eexample%2Ecom/transfer` | **Canonicalization.** `%2E` decodes to `.`; this is the canonicalization case proper. |
| `https://203.0.113.7/transfer` | **CIDR matching, and a deployer who declares the network.** A hostname pattern cannot express an address at all. The mechanism makes the case expressible; it does not supply the knowledge. |
| `https://t.co/x9k2` | **Not canonicalization at all.** The host really *is* `t.co`; the bank is behind a redirect, and following it is a network call the PDP's offline model forbids. Closed by a **declared class of opaque hosts** — a shipped, versioned starter list plus the deployer's own, matched by exact host after canonicalization, treated as *possibly the declared target* because it might be. |

**The semantics in one sentence:** *a host in the declared redirector class is never
auto-executed; a human approves it, or policy denies it.* An action whose consequences
cannot be **verified** must not be auto-executed — that is not the same as saying it
can never happen. A redirector's true destination is unknowable without the network
call determinism forbids, and the honest governance answer to *unknowable* is "a human
decides", not "nobody decides".

This is an **invariant, not tier arithmetic**. It holds whatever the action's tier is
and whether or not the effect you attached declares a floor. Stating it that way is
not pedantry: relying on the effect floor alone left a real hole, found by probing this
exact condition before release. A policy could declare `opaque` and point at an effect
with `min_tier: null`, and a declared redirector would then auto-execute silently — the
deployer asked for the protection, the engine took the declaration, and nothing
escalated. The mechanism was one YAML line away from being decorative. It never shipped
that way.

**Measured on the instrument that disclosed the gap.**
`experiments/aliasing_benchmark.py` gains an **L3** layer beside L2 — L2 is left
exactly as it was, because a fix that edits the baseline it is measured against has
destroyed its own evidence:

```
layer    named  generic✓  evasive  innocent-ok   note
L2     5/5     4/4       0/4      3/3           + deterministic param rules
L3     5/5     4/4       3/4      3/3           + URL-typed rules (ND-040)
```

`tests/guardrail/test_aliasing_acceptance.py` asserts every number in that table in
CI, **including the one that did not move**: the base64 shell case (`ND-048`) is
asserted *still failing*, so this fix cannot be read as closing more than it does.
`innocent-ok` staying 3/3 is the over-blocking guard — governance that fires on
innocents is a defect, and the opaque-host class is exactly what could have broken it.

- **A target that cannot be interpreted is denied, not guessed.** A parse differential
  becomes a denial rather than a bypass — the governing sentence is `scopegate`'s
  (Apache-2.0, D. Mellafe Zuvic), cited rather than reinvented: *a scope gate must
  interpret a target at least as strictly as the networking stack that will later
  connect to it.* The reason code is the **existing** `malformed`; no new wire
  vocabulary. The audit row records `malformed_kind='url_canonicalization'` and the
  `canon_schema` that produced the verdict, so an operator can tell a broken client
  from someone probing the effect matcher, and so a verdict that changes after an
  upgrade is attributable to the canonicalizer rather than to the rules.
- **No new runtime dependency.** The canonicalization is part of the instrument, so a
  canonicalization that changes under a library upgrade would be an instrument change
  wearing a patch release. The standard library's IDNA codec maps the Cyrillic
  homograph to `xn--ank-9cd.example.com` — visibly not `bank.example.com` — which is
  the whole security property: **non-collision and determinism, not IDNA2008
  completeness**. IPv4 shorthand (`0x7f.1`, `2130706433`, `127.1`) is parsed in-module
  rather than by `socket.inet_aton`, whose acceptance of those forms is
  platform-dependent.
- **Upgrading:** run the engine once to apply migrations `0010`–`0011`, which add
  `malformed_kind`, `canon_schema` and `opaque_class` to `actions_audit`. Forward-only,
  all NULL on existing rows, and NULL means "this verdict did not depend on a
  canonicalization or an opaque declaration" — which for a pre-`ND-040` row is simply
  true.

### Known gaps this does NOT close

- **An undeclared shortener is not caught.** The opaque class is a starter list, not a
  census: new redirectors appear constantly, anyone can run one on their own domain,
  and a caller can use one this list has never heard of. The mechanism raises the cost
  of that evasion and names the ones worth naming; `opaque.extra` exists because a
  deployer knows their own environment's link-wrappers better than we do.
- **The IP-literal case needs a declared network.** A deployer who does not know their
  target's address range cannot write the CIDR that catches it.
- **`ND-048` is untouched.** `bash -c "$(echo <base64> | base64 -d)"` carries no
  matchable literal; the governed effect is real and no deterministic parameter rule
  reaches it. Ticketed as `ND-048` so it cannot age out of the disclosure, with **no
  fix scheduled** — and now asserted as still-failing in the test suite, so the gap
  cannot close by accident either.
- **The stdlib implements IDNA2003**, which differs from IDNA2008 on a handful of
  characters (`ß`, final sigma, a few others). A difference produces a **non-match,
  never a false match**, so the failure direction is safe — but a policy written
  against an IDN host in that set would not match a request spelling it the other way.
- **An envelope-validation `malformed` denial writes no audit row** (`ND-050`). A
  request whose envelope fails validation is denied before a policy or a request
  object exists, so there is nothing to append against and the returned result carries
  no `audit_id`. **Present in `≤0.4.0`; found while building `ND-040` and not caused by
  it.** The action does not happen and the caller is told, so nothing is mis-permitted
  — but "the audit log is append-only: decisions, results, denials, dry-runs and
  kill-switch blocks" is a claim this project makes, and one class of denial is outside
  it. Note the asymmetry this release creates and did not cause: a malformed **URL**
  now writes a row naming `malformed_kind`, a malformed **envelope** writes none.
  Ticketed, not fixed here — appending needs a row shape for a request that failed to
  parse, which is a design question rather than a one-liner.

## 0.4.0 — 2026-08-22

**One breaking increment: breaking for archives and readers, not for PEP enforcement.**
A `-00` enforcement point still denies correctly against this release — a PEP's
behaviour is fixed by the verdict, never by the reason string. What changes is what
the audit says, what the decide response carries, and the signature of
`report_result`.

**Upgrading:** run the engine once to apply migrations `0007`–`0009`; they are
forward-only and add columns to `actions_audit` and `policy_versions`. Then, in order
of how likely it is to touch you:

1. `report_result(..., ok: bool)` is now `report_result(..., outcome: Outcome)`, and
   `POST /v1/report` takes `"outcome"` instead of `"ok"`.
2. Reason codes `cap_daily_rate` / `cap_eur_day` / `cap_eur_month` are gone; match on
   `cap_rate` / `cap_value` and read the window from the new `budget` object.
3. Your policy content-hash changes once even if your rules did not — see below.

### Changed — BREAKING for archives and readers, not for enforcement

- **Reason codes are unit-neutral (`aadp/0.2`).** `cap_daily_rate` → **`cap_rate`**;
  `cap_eur_day` **and** `cap_eur_month` → **`cap_value`**, with the window and unit
  moving into `ND-003`'s `budget` object rather than the code. `sender_mismatch` is
  **reserved and never emitted** until `ND-005` wires the check it reports on. Clean
  break, **no dual emission** — safe because reason codes are *audit* vocabulary: a
  PEP's behaviour is fixed by the verdict, never by the reason string, so an older PEP
  that has never heard of `cap_value` still denies correctly. **If you match on reason
  strings in dashboards or alerts, they change here.**
- **Received params are stored verbatim; generated structures are canonicalised.**
  The `parse → json.dumps(default=str)` round trip is gone. When an enforcement point
  sends bytes — over HTTP or the MCP proxy — the audit row stores *those* bytes:
  `250.00` stays `250.00`, because the record must show what was transmitted, not
  what this PDP would have written. The in-process binding is handed objects and has
  no sender's bytes, so it serialises once, canonically, at ingress. **Which of the
  two produced a row is recorded** (`params_provenance`: `received` | `serialized`,
  migration `0009`) rather than inferred — a `received` row can be re-derived against
  what the caller sent, a `serialized` one only against what this PDP produces, and
  letting the second pass for the first is the thing the column prevents. **NULL means
  unknown**: rows written before `0.4.0` were neither verbatim nor canonical, and
  inferring either for them would be inventing evidence. There is deliberately no
  `received_digest` column — the bytes are stored, so the digest is derivable.
- **`report_result` takes a four-value `outcome`, not `ok: bool` — BREAKING for
  enforcement points.** `success | failure | timeout | not_attempted`, and
  `/v1/report` accepts the wire `outcome` field (already normative in `-00`, so this
  is conformance catch-up rather than a wire break). **Settlement now depends on the
  outcome:** `success`, `failure` and `timeout` settle the budget reservation;
  **`not_attempted` releases it, as an audited event.** Settle on doubt — a timeout
  is not evidence the action did not happen, so only a positive assertion of
  non-occurrence frees budget. **This closes a live conformance defect** (A4b): before
  `0.4.0`, `not_attempted` and `timeout` both collapsed into `failed` and the
  reservation settled before anything examined the outcome, so a PEP that correctly
  refused to act still had its tenant charged for an action that never occurred.
  `connector_ok` is now NULL rather than false for `not_attempted`, because recording
  false asserts an attempt that did not happen. The in-process executor reports
  `not_attempted` when no connector is registered — that path was charging budget for
  a dispatch that found nothing to call.
  **If you call `report_result` or `POST /v1/report`, this is the change to make.**
- **Cap denials carry a machine-readable `budget` object.** Present **iff** the
  verdict is a denial with reason `cap_value` or `cap_rate`, on the decide response
  **and persisted** to `budget_json`. Seven required fields: `dimension`
  (`value`|`rate`), `unit` (ISO 4217 for value, a token like `calls` for rate),
  `window`, `limit`, `consumed`, `remaining`, `window_resets_at`. Currency lives in
  `unit`, never in a field name. **This is what makes the unit-neutral codes safe:**
  `cap_value` collapses the old `cap_eur_day`/`cap_eur_month`, so without it an
  evidence reader could no longer tell a day breach from a month one. Numerics are
  canonical decimal strings; `window_resets_at` is RFC3339 UTC derived from the same
  timezone the counters are keyed in.
- **Every audit row is stamped `aadp/0.2`.** A row with **no** stamp MUST be read
  under `aadp/0.1` — that absence is a fact about when the row was written, not a
  value to infer. Existing rows keep the codes they were written with; history is not
  rewritten.
- **The policy snapshot records which canonicalisation produced its hash**
  (`snapshot_schema`, migration `0008`). The content-hash changes on upgrade for
  unchanged rules, and this is what makes that diff *attributable* — "renderer
  changed, rules did not" versus "rules changed" — from the record rather than from
  memory of when you upgraded. Absent means schema 1.
- **Numeric policy bounds and parameters are `Decimal`, never IEEE doubles.** Policy
  YAML numbers load as `Decimal`, JSON ingress parses with `parse_float=Decimal`, and
  bounds, cost resolution and settlement all carry the exact value through. **Two
  visible consequences:** denial messages no longer show float artefacts (`above max
  23`, not `above max 23.0`), and **the policy content-hash changes on upgrade even if
  your rules did not** — `bounds_json` and `caps_json` now record decimals in canonical
  shortest-exact form (`100`, `100.00` and `1E+2` all record as `100` and hash
  identically), so an unchanged policy set gets a new `version_hash` once. Existing
  audit rows keep the hash they were stamped with.
- **Migration `0007`** adds the `0.4.0` row format to `actions_audit`: `protocol`,
  `budget_json`, `outcome`, and the whole receipt envelope. Everything past the first
  three lands **dark** — declared and governed, filled by later increments — so a
  table that cannot be updated is migrated once rather than three times.

### Defects present in `0.3.6` and earlier, closed by this release

Found by the `0.4.0` code survey rather than by incident, and named here because the
known-gaps register applies to bugs found *after* a release exactly as it applies to
gaps known at one.

- **Numeric parameters are compared as IEEE doubles, and a bound can admit a value
  that exceeds it.** `json.loads` runs with no `parse_float`, so a numeric parameter
  becomes a double before any check sees it; a wire amount carrying more precision
  than a double holds is rounded onto the bound and allowed. Demonstrated: policy max
  `500.10`, wire amount `500.1000000000000000001`, verdict **allowed**. The admitted
  excess is about half an ulp of the bound — ~5e-14 at `500.10`, but ~10 at a bound of
  `1e17`, so it is negligible at money scale and material for large-magnitude bounds.
  The symmetric case (a compliant value falsely denied) also exists and fails closed.
  **Mitigation for `0.3.6` deployments: send money amounts as JSON *strings*** —
  `"500.10"` is exact end to end, because cost resolution accepts strings. Closed in
  `0.4.0` by parsing with `parse_float=Decimal` at every ingress and typing numeric
  bounds as `Decimal`.
- **Policy YAML numbers are loaded as floats** (`yaml.safe_load`), which is how the
  bounds above became doubles. Closed by the same change.
- **Money is stored through `str(Decimal)`**, so equal amounts persist as different
  text (`2.50`, `5.00`, `7.500`, `10.000` for four €2.50 spends). **Assessed and
  benign for enforcement**: the money is in no key or index, is never compared as text
  in SQL, and the round trip is value-preserving — 4000/4000 generated values, zero
  comparison flips in 40,000 comparisons, accumulation exact. It makes the audit's
  text untidy and would break a digest computed over that column, which is why it is
  fixed rather than left.

## 0.3.6 — 2026-08-21

Hygiene and one real conformance fix. No wire-format change; no behaviour change
for existing policies.

### The reference implementation stops publishing a contract violation (ND-021)

`examples/litellm_guardrail.py` called `report_result(ok=True)` from
`async_pre_call_hook` — **asserting an action had succeeded before the gateway had
done anything.** That is a violation of the two-phase contract this project exists
to define, shipped as a documented example and cited in the draft's Implementation
Status as "not conformant as written".

Decide and report are now split across hooks: the pre-call hook decides and holds
the permit, reporting nothing; `async_post_call_success_hook` and
`async_post_call_failure_hook` report the real outcome. Correlation is
`data["litellm_call_id"]`; when it is absent the adapter refuses *before* deciding,
so no permit is issued that it could not report on. The pending-intent map is in
process memory — a documented limitation, mirroring `ND-010` in the decision
service, with reservation reclamation as the backstop.

Ten new tests, including the regression that fails against the old behaviour.

### Also in this release

- **`ND-024`** — the vestigial `intake_policy`, `preferences` and `sessions` tables
  (inherited from a pre-onedoor product) are dropped by migration `0006`.
  `push_subscriptions` is kept and now says in a comment that it is reserved for
  web-push delivery, so nobody mistakes it for dead schema.
- **`ND-025`** — CI actually enforces the gates. `ruff`, `ruff format`, `mypy
  --strict` and `pytest` run on a 3.12/3.13 matrix; `ruff` is **pinned**, because an
  unpinned linter makes CI non-deterministic. All four now pass; none of them did
  before.
- **`ND-036`** — `ROADMAP.md` is a pointer to the live documents rather than a
  stale feature list. Eleven work items that lived only in it were migrated into
  `BACKLOG.md` rather than deleted.
- **Packaging:** a `[litellm]` extra. The LiteLLM example imported a package no
  extra installed, so anyone following the docs hit `ModuleNotFoundError`.
- **Repository integrity:** `.gitattributes` forces LF and freezes the vendored,
  digest-pinned reference artifact byte-for-byte. Windows' `core.autocrlf` default
  silently rewrote those bytes, which made every pinned manifest fail verification
  in a way that reads as *evidence tampering* rather than as an encoding bug.
- **`README`** no longer advertises a stale test count; the CI badge carries it.

### Fixed

- `pytest` and `python -m pytest` no longer disagree. 19 test modules import
  `tests.conftest`, which needs the repository root on `sys.path`; `python -m`
  supplies it implicitly and the bare `pytest` that CI runs does not. The suite
  passed locally and could not even be collected in CI.

### Known gaps, stated rather than implied

- No obligation machinery at all (`CONFORMANCE.md` N6 / `ND-038`). A conformant
  PDP obligation attached to a permit would be silently ignored by onedoor's own
  enforcement points.
- `report_result` has no outcome parameter, so `not_attempted` and `timeout`
  collapse into `failed` (`CONFORMANCE.md` A4b / `ND-039`). A reservation is
  settled before the outcome is examined, which charges budget for an action that
  may never have occurred. Fixed in `0.4.0`.
- Transport security (A1), sender-constrained permits (A2) and hash-chained audit
  entries (P1) are not implemented.
- **URL-valued parameters are matched as strings, and known evasions defeat that**
  (`ND-040`). `param_effects` full-matches a regex against a parameter's string form,
  so a pattern like `https://(pay|bank)\.example\.com/.*` does not survive contact
  with an adversarial URL. **Measured, not suspected:**
  `experiments/aliasing_benchmark.py` scores **0/4 on its evasive set at every layer**,
  including the layer with deterministic parameter rules. The four cases are a
  redirector/shortener (`https://t.co/...`), an **IP literal**, a **percent-encoded
  host** (`bank%2Eexample%2Ecom`), and a **base64-obfuscated shell command**.
  **Three of those four are URL-shaped and are what `ND-040` addresses** — canonicalize
  first (scheme normalization, IDNA, host lowercasing, explicit subdomain semantics,
  CIDR awareness) and deny on canonicalization failure, so a parse differential is a
  denial rather than a bypass. Scheduled for `0.4.x`, immediately after `0.4.0`.
  Reasoned from the matcher's design rather than individually measured, the same
  string-matching weakness also covers IDN homographs, a `user@host` prefix, a
  trailing-dot host and case variation.
- **The fourth evasive case is a separate gap that `ND-040` does not close.**
  Indirect or obfuscated command construction (`bash -c "$(echo <base64> | base64 -d)"`)
  is not a URL-canonicalization problem, and no deterministic parameter rule catches
  it; the benchmark says so in its own output. Nothing in this release addresses it.
- **What follows for a deployer, plainly:** do not rely on `param_effects` patterns as
  a network scope control against an adversarial input. Use them to label effects of
  cooperative inputs, and put a fail-closed egress control in front of anything that
  matters. Known evasions are published here rather than left to be discovered.

## Earlier releases

Reconstructed from git tags; these predate this file.

| Version | Tag subject |
|---|---|
| 0.3.5 | integrations: onedoor as LangChain agent middleware |
| 0.3.4 | guardrail: reservation reclamation (AADP §6) |
| 0.3.3 | F7 — every euro cap was inert unless the caller set `cost_eur` by hand |
| 0.3.2 | onedoor did not work on Windows |
| 0.3.1 | release the packaging fix |
