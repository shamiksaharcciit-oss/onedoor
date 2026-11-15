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
