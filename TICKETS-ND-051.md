# `ND-051` — the onedoor receipt viewer (oneview skin) · decomposition

**Ticket:** `ND-051`, Phase-B launch asset, **before** the crypto epic resumes.
**Baseline:** `0.4.1` @ `7e9fd07`, published; 392 passed / 8 skipped, four gates green.
**GO:** R028 §4. **Spec:** `docs/oneview/ONEVIEW_DESIGN_SPEC.md` + `docs/oneview/oneview.html`.
**Out of scope, explicitly:** `ND-018` (live monitor GUI) and `ND-020` (policy studio).
This is demo-grade, read-only, and the spec's §3 fence is what says no to everything else.

---

## 1. The finding that shapes the whole build

R028's first requirement is: *"the generator calls the same verification the
engine/CLI uses — never its own copy."*

**There is no such verification, and there is no CLI.** Checked, not assumed:

- `onedoor/` has no `cli.py`, and `pyproject.toml` declares no `[project.scripts]`.
- `grep "def verify" onedoor/` returns exactly one hit, `verify_inclusion` in the
  vendored `canonical.py` — a Merkle helper, not a receipt check.
- The receipt envelope columns exist and are **dark**: `prev_hash`, `seq`, `row_hash`,
  `sig`, `key_id`, `alg`, `e_digest`, `i_digest`, `t_digest`, `v_digest`, `anchor_ref`
  all landed NULL in migration `0007`, waiting on `ND-001`/`ND-015`/`ND-017`.

So the requirement cannot be met by *calling* something. It can be met by *creating
exactly one implementation, outside the viewer*, which is what the rule is actually
for: the forensics build's structural rule exists so a viewer cannot drift from the
checker. **The verification lands in `onedoor/guardrail/receipt.py`** — engine code,
importable by a CLI the day one exists — and the viewer imports it and renders its
output. A structural test asserts the viewer package contains **no** verification of
its own: no `hashlib`, no `sha256`, no digest arithmetic anywhere under
`onedoor/viewer/`. That is the enforceable form of "never its own copy", and it fails
loudly the moment someone adds a convenience hash to the renderer.

**Reported rather than assumed:** if core intended the viewer to wait for `ND-001` so
there is a real chain to check, this is the moment to say so. The build below does not
need it, and §2 explains why the absence is an asset rather than a hole.

## 2. The mockup's chain block cannot be rendered truthfully today — and that is the demo

`oneview.html`'s onedoor card shows:

```
Row hash    a3c1e7f0…
Previous    7f2b9e04…
Sequence    18,442 · chain intact
```

Those are precisely the columns that are NULL in `0.4.1`. Rendering them would be
fabrication, and the spec's own law forbids it: *every displayed value is read from a
verified artifact.*

So the chain block renders the **absent** state, in frame, naming the ticket that will
fill it. This is the three-outcome rule and R015's null-versus-empty rule arriving in
a user interface:

| State | Means | Renders as |
|---|---|---|
| **verified** | checked and it holds | the value, with its check |
| **absent** | not yet produced — `ND-001` has not run | "not yet produced (`ND-001`)", faint |
| **unverifiable** | should be checkable and is not — a snapshot row missing, a half-written chain | **failure state**, loud |
| **failed** | checked and it does not hold | **failure state**, loud |

*Unverifiable* is not a skip. A half-written chain — some columns set, others NULL —
is `unverifiable`, never "absent", because absence is a claim about a feature that has
not run and this would be a feature that ran badly.

A viewer that says plainly what it cannot yet prove is a better artifact for this
product than one that shows a green tick over a dark column. The category we are
avoiding is the dashboard, and a dashboard's characteristic lie is exactly a confident
number with nothing behind it.

## 3. What *can* be verified in `0.4.1`, and it is not nothing

Seven checks, all reading the store, all in the one engine module:

| Check | What it proves | Outcomes it can return |
|---|---|---|
| `params_byte_form` | `params_json` is bytes that decode as UTF-8 and parse as JSON | verified · failed |
| `params_provenance` | the value is a declared `Provenance` member | verified · absent (pre-`0.4.0` row) · failed |
| `reason_vocabulary` | `reason_code` is a live `CheckId`; `protocol` stamp read, absent ⇒ `aadp/0.1` | verified · failed |
| `budget_object` | a cap denial carries all seven `Budget` fields, parseable (E7) | verified · absent (not a cap denial) · failed |
| `policy_snapshot` | `sha256(stored snapshot_json) == recorded version_hash` | verified · absent · **unverifiable** (snapshot row gone) · failed |
| `append_only` | the `actions_audit` no-update/no-delete triggers are installed | verified · failed |
| `chain` | `row_hash`/`prev_hash`/`seq` | **absent** today · unverifiable (partial) · failed |

**Byte-form before digest (R028).** `params_byte_form` runs before anything hashes,
and `policy_snapshot` hashes the *stored snapshot text* and compares it to the
*separately stored* `version_hash` — two fields written at different times, so a
disagreement is real evidence. It is not the tautology R028 warns about, which would
be hashing a row and comparing it to a hash computed from the same row in the same
breath.

## 4. Scope fence (spec §3), enforced by a test and not by intention

Static HTML, inline CSS/JS, opened from disk. No backend, no auth, **no network call
at view time** — asserted by a test that greps the emitted page for `fetch(`,
`XMLHttpRequest`, `<form`, `<input`, and any `src`/`href` to an off-disk origin. The
one exception is the Google Fonts stylesheet the reference mockup uses; a local
fallback stack is declared so the page is correct without it, and the test allows that
one origin by name rather than by pattern.

Live tail = the append-only ledger's recent rows, appended. Nothing mutates. No
dashboards, charts-over-time, filters, search or settings — and the test that greps
for `<input` is also the test that keeps a search box from ever appearing.

## 5. Tokens

The `:root` block is vendored **byte-identical** from the spec's §4 code fence, with a
digest pin in the vendoring module, the `rederivable-manifest` pattern. Two guards:

1. `test_tokens_are_vendored_verbatim` — the block in `onedoor/viewer/tokens.py`
   matches the spec file's fence byte for byte, and the recorded digest matches.
2. `test_no_foreign_hex_colour` — every `#rrggbb` in the emitted page is a token value
   or is declared in a small allowlist with a reason. Semantic green/red never doubles
   as brand accent, and seal gold never signals state, which this catches by finding
   `--seal` in a verdict rule.

## 6. The two mandatory tests, and the sabotage that proves them

R028: *"render-as-if-verified must fail exactly the failure-state tests; a fabricated
digest must fail exactly the digest tests."* A test that passes tells you nothing about
what it would catch, so both are sabotage-verified — the sabotage is applied, the suite
is run, and the **set of failing tests is recorded and asserted to be exactly the
intended set**. Not "some test failed": the right tests failed, and no others.

- **Sabotage A — render as if verified.** Force the renderer to emit values for a
  receipt whose verification failed. Must fail the failure-state tests and nothing else.
- **Sabotage B — fabricate a digest.** Change one stored digest so the snapshot check
  cannot hold. Must fail the digest/X-11 tests and nothing else.

## 7. Cold clone (spec §7)

`python -m onedoor.viewer --store <path> --out <path>` produces the page from a store.
A fresh clone has no store, so the cold-clone path is: create one, run decisions
through the engine, generate. `--demo-store` builds a labelled sample store for the
demo, and **the label travels in the store, not in the command line** — the seeder
writes a marker row that the generator reads and renders in-frame. A sample page that
loses its "sample" label because someone re-ran the generator without the flag is
exactly the failure the spec's *"labelled in-frame, always"* is about.

## 8. Work order

- **V1** — `onedoor/guardrail/receipt.py`: the one verification, four outcomes, seven
  checks, tests first for the outcome algebra.
- **V2** — `onedoor/viewer/tokens.py`: vendored block, digest pin, both guards.
- **V3** — the generator and template: hero receipt (deny-with-budget), live tail,
  absent-state chain block, failure state.
- **V4** — the X-11 test (every displayed digest and number appears in the store),
  the failure-state test, the scope-fence test, the no-second-verification test.
- **V5** — the sabotage runs, with the failing-set assertion, plus cold-clone.
