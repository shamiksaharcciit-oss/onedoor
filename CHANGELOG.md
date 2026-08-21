# Changelog

onedoor is the reference implementation of the AADP Internet-Draft
(`draft-saha-aadp`). Per-requirement conformance status, gaps included, lives in
[CONFORMANCE.md](CONFORMANCE.md); the ticket-by-ticket plan is in
[BACKLOG.md](BACKLOG.md).

## Unreleased — `0.4.0` in progress

### Changed — BREAKING for archives and readers, not for enforcement

- **Reason codes are unit-neutral (`aadp/0.2`).** `cap_daily_rate` → **`cap_rate`**;
  `cap_eur_day` **and** `cap_eur_month` → **`cap_value`**, with the window and unit
  moving into `ND-003`'s `budget` object rather than the code. `sender_mismatch` is
  **reserved and never emitted** until `ND-005` wires the check it reports on. Clean
  break, **no dual emission** — safe because reason codes are *audit* vocabulary: a
  PEP's behaviour is fixed by the verdict, never by the reason string, so an older PEP
  that has never heard of `cap_value` still denies correctly. **If you match on reason
  strings in dashboards or alerts, they change here.**
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
