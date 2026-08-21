# `0.4.0` — decomposition

**Release:** `0.4.0` — `ND-002` + `ND-003` + `ND-039` as **one breaking increment**.
**Breaking for archives and readers, not for PEP enforcement.**
**Baseline:** `0.3.6` @ `6a95a69`, published; 185 passed / 8 skipped, four gates green.
**Migration:** `0007` (claimed in `BACKLOG.md`'s register).
**GO:** R015 §2 — decompose first, migration shape and ACJ renderer property tests
leading, no core sign-off on the decomposition unless it surfaces a question.
**It surfaced one.** See §7; it gates `ND-001`, not `0.4.0`.

## 1. The three constraints this builds to, cited not rediscovered

- **E8 at the renderer.** Shortest-exact decimals, one form, **wire = storage =
  preimage**. The property tests assert the **tripartite equality**, not each leg
  separately — three legs tested apart can each pass while the equality fails.
- **R005 at the outcome.** Four values with outcome-dependent settlement: settle on
  `success`, `failure`, `timeout`; **release only on `not_attempted`, as an audited
  event**. *Settle-on-doubt* is the invariant the tests protect — release requires a
  positive assertion of non-occurrence, never an absence of information.
- **E11 at the envelope.** Receipt fields landing NULL are **dark surface** —
  present, declared, governed by the dark-surface clauses from day one, never
  "unused columns". **A NULL meaning "not yet produced" must be distinguishable from
  one meaning "produced empty"**, wherever the envelope is read.

## 2. What the code survey found that the backlog does not say

Grounded in the source at `6a95a69`, not in the ticket text. Four of these are live
defects rather than missing features.

| # | Finding | Why it matters here |
|---|---|---|
| S1 | **`canonical.py` is not vendored into the package.** It exists only at `reference/rederivable-manifest/canonical.py`. | `BACKLOG.md` assigns vendoring to `ND-001` (`0.4.1`). **Wrong order:** `ND-002`'s row format and `ND-003`'s budget object both need the renderer. **Vendoring moves into `0.4.0`, first.** |
| S2 | **`NumericBound.min/max` are `float`** (`models.py:81-82`) while `cost_eur` is `Decimal`. | This is E10's warning already true in shipped code: bounds compare a Decimal against a float. Visible in output today — the LiteLLM self-test prints `above max 500.0`. |
| S3 | **Money is stored through `str(Decimal)`** (`caps.py:174,178,182` write `str(total + cost)`; `175,179,183` write `str(cost)`). | E8's named trap. `str(Decimal("250.00"))` keeps authored scale and `str(Decimal("2.5E+2"))` is exponent form. Two equal-value amounts store as different text **today**, in `counters.eur_total` and `cap_reservations.deltas_json`. |
| S4 | **`yaml.safe_load`** loads policies (`policy_loader.py:114`). | Produces IEEE floats for `250.00`. E10: *applies to policy YAML loading too, or the money-through-a-float defect reopens.* Feeds S2. |
| S5 | **Eight `json.loads` call sites**, none with `parse_float=Decimal` — including `undo.py:66` (original params) and `decision.py:349` (reservation deltas), both on the evaluation path. | E10 ingress rule. |
| S6 | **No protocol version is stamped anywhere** in the package or the store. | `ND-002` adds it; there is nothing to migrate *from*, so every pre-`0007` row is read under `aadp/0.1` by the absent-value rule (E6). |
| S7 | `Decision` (`executed\|dry_run\|proposed\|denied\|failed`) is a **verdict** vocabulary, not an outcome one. | `ND-039`'s four values are a **new, separate** enum. `report_result(ok: bool)` currently collapses them into `EXECUTED`/`FAILED`. Do not overload `Decision`. |

## 3. Work order

Sequenced so nothing depends on bytes that are not yet frozen.

**W1 — Vendor the canonical renderer, and pin it with property tests.** (S1)
Copy `canonical.py` verbatim from the pinned v3 artifact into
`onedoor/guardrail/canonical.py`. **Vendored, not reimplemented** — same bytes by
construction, which is the whole reason the artifact exists. `tests/reference/`
already asserts the source copy is unmodified; add a test that the vendored copy is
**byte-identical to it**, so the two cannot drift.

Property tests, over **generated** inputs (discipline 4 — spot-checks find only the
violations you thought of; the `⇒` miss is the standing reminder):
- equal-value/different-scale decimals (`250`, `250.00`, `2.5E+2`, `0.50`, `-0`)
  render byte-identically;
- canonical output re-canonicalises to itself (idempotence);
- **the tripartite equality**: for a generated value, the bytes on the wire, the
  bytes stored, and the bytes hashed are the *same object*, asserted as one property
  rather than three;
- datetimes: RFC3339, UTC, uppercase `Z`, seconds always present, fractional
  shortest-exact and omitted at zero;
- floats are refused at the boundary (`canon_decimal` already raises).

**W2 — Migration `0007`, the row format.** (§4 below.) Nothing else lands first.

**W3 — Decimal at every ingress.** (S2, S4, S5) `parse_float=Decimal` on all eight
`json.loads`; a Decimal-preserving YAML loader; `NumericBound` to `Decimal`.
Duplicate keys / NaN / Infinity / non-UTF-8 ⇒ deny `malformed` — no new vocabulary,
`CheckId.MALFORMED` is already live in `decide_and_reserve`'s total form.

**W4 — Reason-code vocabulary + protocol stamp.** (`ND-002`) `CAP_DAILY_RATE` →
`cap_rate`; `CAP_EUR_DAY` **and** `CAP_EUR_MONTH` → `cap_value`; add
`sender_mismatch` **reserved, never emitted** until `ND-005` wires the check. Stamp
`aadp/0.2` on every row. Clean break, no dual emission.

**W5 — The `budget` object.** (`ND-003`) Seven REQUIRED fields, present **iff**
verdict is `deny` and reason ∈ {`cap_value`, `cap_rate`}. Persist to `budget_json`
in canonical form — without it `cap_value` cannot say which window it broke, a
granularity regression against `0.3.5`. Replaces the free-text `detail` at
`caps.py:139-149`.

**W6 — The four-value outcome.** (`ND-039`) New `Outcome` enum (S7). `/v1/report`
accepts the wire `outcome` field. Settlement becomes outcome-dependent per R005.
Thread through both packaged PEPs and the LiteLLM example.

**W7 — Verbatim freeze at ingress.** (E10/R004) `params_json` and `payload_json`
frozen as received, never re-serialised; the `parse → json.dumps(default=str)` round
trip abolished. Generated structures (`budget_json`, receipt fields) are ACJ. The
in-process binding receives no bytes, so its frozen form is **one** ACJ serialisation
at ingress, and the row must make that provenance distinguishable.

## 4. Migration `0007` — shape

Forward-only. `actions_audit` is append-only by trigger, so every column is added
`NULL`-able and back-fill is impossible by construction.

| Column | Type | Lands | Meaning of NULL |
|---|---|---|---|
| `protocol` | TEXT | `0.4.0` | **Absent ⇒ read the row under `aadp/0.1`** (E6). Rows written from `0.4.0` always stamp it. |
| `budget_json` | TEXT | `0.4.0` | Not a cap denial. Present iff deny + `cap_value`/`cap_rate`. |
| `outcome` | TEXT | `0.4.0` | Not a result row. |
| `prev_hash` | TEXT | `0.4.0`, **dark** | not yet produced — **see §7** |
| `seq` | INTEGER | `0.4.0`, **dark** | not yet produced |
| `row_hash` | TEXT | `0.4.0`, **dark** | not yet produced |
| `sig`, `key_id`, `alg` | TEXT | `0.4.0`, **dark** (`ND-015`) | not yet produced |
| `e_digest`, `i_digest`, `t_digest`, `v_digest` | TEXT | `0.4.0`, **dark** (`ND-017`) | not yet produced |
| `anchor_ref` | TEXT | `0.4.0`, **dark** (`ND-017`) | not yet anchored |

All digests SHA-256, lowercase hex. The whole envelope lands now so `0.4.1` and
`ND-017` never re-migrate a table that cannot be updated.

**Dark surface is declared, not merely empty** (E11): the columns exist, are
documented as reserved with the increment that fills them, and `ND-038`'s
enforcement-before-emission rule governs anything read from them. A reader must not
be able to mistake "not yet produced" for "produced and empty" — for the digest
columns that distinction is free, because a produced-but-empty digest is
`sha256("")` = `e3b0c442…`, a real value that is not NULL.

## 5. Test plan

- **Property tests over generated inputs** for the renderer (W1), including the
  tripartite equality as a single property.
- **Round-trip**: `250` and `250.00` produce identical canonical bytes **and**
  identical `row_hash` once `ND-001` chains them.
- **Old-row reading**: a fixture DB of pre-`0007` rows with no `protocol` stamp still
  renders correctly under the `aadp/0.1` reading (`ND-002` DoD).
- **Settlement matrix**: all four outcomes × (reservation held / already reclaimed),
  asserting settle-on-doubt and that `not_attempted` **releases and audits**, never
  silently adjusts.
- **Migration**: a `0.3.6` database migrates forward cleanly and the append-only
  triggers survive — the `ND-024` test is the template.
- **No dual emission**: no deprecated reason code is emitted by a PDP stamping
  `aadp/0.2`.

## 6. What is explicitly NOT in `0.4.0`

`ND-001`'s chaining (fields land dark, unfilled) · `ND-015` signing · `ND-017`
digests and anchoring · `ND-038` obligation machinery — the surface ships **dark**
per E11, and `ND-039` lands **before** anything emits an obligation, per R003 clause
0 · `ND-040`, which follows immediately after per R011.

## 7. The one question this decomposition surfaced

**Genesis `prev_hash` is ambiguous under R015's null-versus-empty rule.**

`ND-001` starts the chain at a genesis row, because existing rows cannot be
retro-chained. On that row `prev_hash` has no predecessor to name. But NULL there
would mean *both* "no predecessor exists" **and** "not yet produced" — which is
exactly the collapse R015 makes programme-wide in both directions. A verifier walking
a mixed archive cannot tell the first chained row from an unchained one.

Options delivery can see: a reserved sentinel (64 zeros) for genesis; or a distinct
`chain_state` column; or genesis carrying the id of the last unchained row in a field
of its own, which `ND-001` already requires it to record.

**This is receipt content, so it is core's call, not delivery's.** It does **not**
block `0.4.0` — `0.4.0` only creates the column NULL — but it must be settled before
`ND-001` writes the first chain. Raised now rather than at implementation time,
because a rule discovered at decomposition is a rule, and one discovered afterwards
is a retrofit.
