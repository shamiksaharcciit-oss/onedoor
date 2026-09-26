# Decision-record export

`python -m onedoor.export --store <db> --out <file> [--since <utc>]`

Writes every row of `actions_audit` **as it is stored** — one JSON object per
line (JSON Lines / NDJSON), keys sorted, no reinterpretation of any column's
value. `params_json`, `payload_json` and `budget_json` are exported as the
*strings* onedoor already wrote into those columns, not re-parsed into nested
objects: the export shows what the row holds, not a redigested view of it. No
field is invented that the row does not already carry, and none is dropped.

A `<file>.sha256` is written alongside, one line, in the form `sha256sum`
reads:

```
<hex digest>  <basename of <file>>
```

## Ordering

Rows are written in `id` ascending order — the table's own append order
(`actions_audit` is append-only; `id` is assigned in write order and never
reused). Two exports of the same, unchanged data are therefore byte-identical.

## `--since`

`--since <utc>` keeps only rows whose `created_at` is **greater than or equal
to** the given instant (inclusive), parsed as ISO-8601 (`Z` or `+00:00`
accepted). The comparison parses both sides as datetimes rather than comparing
the stored strings lexicographically. (Lexicographic comparison of the stored
form happens to agree here — `created_at` omits the microsecond field only
when it is exactly zero, and `.` sorts after `+` in ASCII, so a fractional
second still sorts after the same whole second — but the exporter compares
what a timestamp *means*, not what its storage format happens to allow.)

## Fields

One JSON object per line, with these keys (a row's `NULL` columns are
exported as JSON `null`, never omitted — omission would be indistinguishable
from a field this version of onedoor does not have):

| Field | Meaning |
| --- | --- |
| `id` | The row's position in the append-only log. Export ordering key. |
| `request_id` | The `ActionRequest.request_id` this row was written for. |
| `kind` | `"decision"` or `"undo"` — what kind of row this is. |
| `parent_id` | For a follow-up row (e.g. a report), the `id` of the row it completes. |
| `action_type` | The action type decided on. |
| `source` | Who originated the request (`llm`, `ui`, `undo`, …). |
| `params_json` | The frozen request params, as stored — verbatim received bytes when available, else a serialization (see `params_provenance`). A JSON-encoded **string**, not an object. |
| `params_provenance` | `"received"` (verbatim bytes) or `"serialized"` (no bytes were received; the PDP serialized once). |
| `decision` | The verdict: `permitted`, `denied`, `proposed`, `executed`, … |
| `reason_code` | The machine-readable reason for the verdict. |
| `nominal_tier` | The action's declared tier, before any escalation. |
| `effective_tier` | The tier the verdict was actually evaluated at. |
| `detail` | Free-text explanation. Not machine-readable; see `budget_json` and `reason_code` for that. |
| `connector_ok` | Whether a connector call inside this row succeeded, or `null` if none ran. |
| `error` | Connector or execution error text, or `null`. |
| `payload_json` | The reported outcome payload, as stored. A JSON-encoded **string**, or `null` before a report lands. |
| `payload_provenance` | Same meaning as `params_provenance`, for `payload_json`. |
| `approval_id` | The `approvals` row this decision is linked to, or `null`. |
| `undo_until` | The deadline by which this permit can still be undone, or `null`. |
| `undo_of` | For an undo row, the `id` of the row it undoes. |
| `created_at` | When this row was written, ISO-8601 UTC. |
| `policy_version` | The policy snapshot hash in force when this row was decided. |
| `protocol` | The AADP wire vocabulary this row is stamped with (e.g. `aadp/0.2`), or `null` for a pre-`ND-002` row (read as `aadp/0.1`). |
| `budget_json` | ND-003 machine-readable budget state, present iff the verdict is a cap denial. As stored — a JSON-encoded **string**, or `null`. |
| `outcome` | The reported outcome (`success`, `failure`, `timeout`, `not_attempted`), or `null` before a report lands. |
| `prev_hash`, `seq`, `row_hash` | Hash-chain linkage (ND-001), or `null` where chaining is not in operation. |
| `sig`, `key_id`, `alg` | Row signature (ND-015), or `null` where signing is not in operation. |
| `e_digest`, `i_digest`, `t_digest`, `v_digest` | The four receipt digests (ND-017, `docs/receipt-digests.md`), or `null` where not computed. |
| `anchor_ref` | A published-anchor reference for this row, or `null`. |
| `malformed_kind` | What kind of malformed input this row records, when `reason_code` is `malformed`, else `null`. |
| `canon_schema` | Which URL-canonicalisation schema ran for this row, or `null`. |
| `opaque_class` | The declared opaque host class that matched, or `null`. |
| `approval_ref_status` | The `approval_ref` evidence value (ND-009): `absent`, `honored`, `expired`, `consumed`, `unknown`, `action_mismatch`, or `null` on a pre-`ND-009` row. |
| `preimage_version` | Which row-preimage version (`docs/row-preimage.md`) this row's hash was computed under, or `null`. |
| `evaluation_trace_json` | AADP -03 §10: the ordered list of checks actually evaluated for this verdict (`kind` `decision`/`exec_intent` only), as stored — a JSON-encoded **string**, or `null` on a pre-WO-D1-step-5 row or a row of a different `kind`. Each entry: `check`, `rule`, `condition`, `value`, `result` (`pass`\|`fail`\|`unresolved`). **Dark (unhashed)** — see `docs/row-preimage.md` §4. |

The authoritative column list and types live in the migrations
(`onedoor/store/migrations/`); this table is a reading aid, not a second
schema — if the two disagree, the migrations are right and this file is
stale.

## Join field

`request_id` is the key an external reader — including the onetrace extension
(decision record D-2026-09-26) — joins on. It is the same value end to end:

- On the wire, `DecideBody.request_id` (`onedoor/service/app.py:95`), optional —
  the caller supplies it or the service mints one with `uuid4()`
  (`onedoor/service/app.py:254`).
- Stored verbatim as `str(request.request_id)` in every `actions_audit` row the
  decision produces (`onedoor/guardrail/audit.py:437`).
- Returned on the same response as `DecideReply.request_id`
  (`onedoor/service/app.py:109`).
- Exported unchanged, like every other column (`onedoor/export.py`'s
  `export_rows` is generic over columns; it does not special-case this one).

A row's `id` (this file's own primary key, and the export's ordering key — see
above) is **not** stable across a request's own lifecycle: a decide, its
report, and any reservation-disposition row each get their own `id`, linked by
`parent_id`/`undo_of` rather than by `request_id` alone (a report shares its
originating decide's `request_id` but is a different row). `request_id` is the
field that identifies *the request*, across every row it produced.

`tests/service/test_service.py::test_request_id_survives_decide_to_audit_row_to_export_unchanged`
sends a request with a known `request_id`, decides it, and asserts the same
value appears on the wire response, in the audit row, and in the export.

## Round-tripping

Every value in an exported line came from `SELECT * FROM actions_audit`
unmodified: an `INTEGER` column round-trips as a JSON number, a `TEXT` column
as a JSON string, and a `NULL` column as JSON `null`. No column on this table
is ever a float (E10 forbids floats on the evaluation path); the exporter
raises rather than silently write one if it ever found one.
