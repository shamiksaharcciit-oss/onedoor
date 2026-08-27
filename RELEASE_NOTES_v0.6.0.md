# onedoor 0.6.0

Notes drawn **verbatim** from [CHANGELOG.md](CHANGELOG.md)'s `0.6.0` section (R011:
release notes are a slice of the changelog, never a rewrite of it). Conformance status
with every gap named lives in [CONFORMANCE.md](CONFORMANCE.md); the ticket-by-ticket
plan is in [BACKLOG.md](BACKLOG.md).

---

**Additive. Nothing existing changes meaning.** No wire-observable change: no new reason
codes, no changed verdict shapes, no altered two-phase exchange, and a `-00` enforcement
point is unaffected. **No new enforcer migrations** — the last is `0018`, as in `0.5.0`.

**This release completes the Policy Studio.** `0.5.0` shipped its first three tickets;
this one adds the remaining three — the **coverage map**, the **payments template pack**,
and the **proposer** — so `ND-052` is delivered end to end: backtest, ratification,
canvas, coverage, packs, proposer.

The line the whole epic holds: **the proposer is never the enforcer.** The thing that
drafts policy has no path to the active set except the ratification ceremony, and it
enters as a candidate like any other — asserted structurally by a test that walks the
decision path's import closure and refuses to find the Studio, or any network client, in
it.

**Everything Studio is behind the `[studio]` extra and off by default.** An installation
that changes nothing behaves exactly as it did under `0.5.0`. The Studio keeps its own
`studio.db` — schema version 2 in this release, upgraded forward automatically — because
**the enforcer's database contains no row the Studio can edit.**

**A word changed meaning, deliberately.** Constitution principle 5 said *"the derivation
gets a receipt"*; a proposal is not recomputable, so it gets a **derivation record**
instead — one that says on its face that it does not attest re-derivability, and that
*the candidate's authority comes from the checks it passes, never from the record*. The
amendment and its reasoning are in [docs/studio-constitution.md](docs/studio-constitution.md).

**Upgrading:** nothing to do. No engine migrations; the Studio store upgrades itself on
first open.

### Added — `ND-052` / S6: the policy proposer, and the epic completes

The Studio's last ticket. **The proposer is never the enforcer**: it drafts a candidate and
has no path to the active set except the ratification ceremony, entering it as a candidate
like any other.

- **A derivation record, not a receipt.** Every other artifact this project emits is
  *recomputable* — that is what makes it a receipt. A proposal is not: the same description
  through the same model twice may differ, and recording the instrument pins the
  *conditions*, never the output. Constitution principle 5 was **amended rather than
  stretched** to say so, and the record states on its face both that it is not
  re-derivable and that **the candidate's authority comes from the checks it passes, never
  from the record.**
- **`proposer_provenance: live | fixture`** — the same value pair as `ledger_provenance`,
  because it is the same distinction and a renderer must not learn a second dialect for it.
  Inside the record's digest, so relabelling a fixture-drafted candidate as a model's work
  breaks the record's own address.
- **Descriptions are received data.** Stored as BLOBs, byte-for-byte, never normalised —
  the digest a record cites is taken over exactly the bytes the operator wrote.
- **One surface, two sections, never one table.** The coverage map's rows are measurements;
  the proposal's mentioned-but-unruled rows are a model's reading of a sentence. Each
  section states its warrant, and every asserted row cites the coverage state it was
  checked against.
- **The decision path cannot reach a proposer** — a structural test walking the import
  closure from source, lazy imports included, and refusing any network client at all.
- **A benchmark that publishes its misses first.** No score gates anything; the demo may
  run when the results, misses included, are published beside it and the demo states its
  number. The corpus includes adversarial descriptions and the published misses include the
  security-shaped ones.

New module `onedoor/studio/proposer.py` with a deterministic fixture proposer so CI runs
with no key and no network. A model-backed proposer is a separate credentialed component
and is **not** part of this build — and nothing falls back to the fixture silently.

### Added — `ND-052` / S5: the payments template pack

`onedoor/templates/payments/` — **worked examples**, shipped in the wheel, adopted through
the ratification ceremony.

- **No placeholders, anywhere.** Every value is concrete and fail-closed. *A blank is a
  promise that someone will remember* — and a template with blanks cannot be checked,
  because it is not yet the thing the check checks: `{{daily_cap}}` is not a `Policy`, so
  a pack full of blanks would pass its own law tests against an artifact that does not
  exist yet. Adjusting means editing a real number that was already safe.
- **Every effect the pack names is declared**, asserted through `coverage.build`'s own
  `declared_inert` detector rather than a checker written for the pack — and no declared
  effect has a null floor, which is the `ND-040`/U4 half of the same law.
- **`PACK_DIGEST`** is the pack's *file* identity — byte-for-byte what shipped, comments
  included — generated by `python -m scripts.pack_digest`, never typed. The *meaning*
  identity is the existing `policy_digest`, cited rather than re-minted.
- **Adoption goes through the ceremony**, so the receipt's `candidate_digest` **is** the
  pack's `policy_digest` by construction: lineage is recoverable by recomputation rather
  than by a stored pointer. No schema change.
- **The boundary is named, not disclaimed.** `PACK.md` states plainly that this is not a
  compliance artifact and that nobody who wrote it has payments domain authority, then
  names what is absent: sanctions screening, KYC, chargebacks, multi-currency settlement,
  regulatory reporting. *A named gap is a service to the reader; a disclaimer is a service
  to the writer.*

### Fixed — the wheel shipped no template data files

`include = ["onedoor*"]` ships Python modules; the pack's `.yaml` and `.md` needed a
`package-data` entry. This is the `0.3.0` defect — a wheel that shipped no migrations —
reproduced exactly, and caught by a test written before the build rather than by a user's
first query.

### Added — `ND-052` / S4: the coverage map

Constitution principle 4 — *non-coverage is stated, never silent* — as something a
deployer can look at. Four states, and the ranking is by **what each does at decision
time**, not by how alarming its name sounds:

- **`declared_inert`, first and loudest** — a rule labels an effect with no
  `effect_policies` row behind it. The label is **silently dropped**: no tier floor, no
  effect caps. It sounds fine and behaves dangerously, which is why it outranks
  everything else on the map.
- **`uncovered_observed`** — the ledger saw this action type and no policy declares it.
  `default_deny`: it sounds bad and behaves safely, because the engine refuses loudly and
  the operator finds out.
- **`unobserved`** — a **declared** effect nothing in the cited range exercised. Rendered
  *absent*, never as safe: a measurement nobody took is not a clean result.
- **`covered`**, quiet.

The map's sources are the policy set and **the ledger** — not a description, which does
not exist until the proposer ships. *A description says what someone remembered to write
down; the ledger says what happened.*

**It is a view that cites, not a receipt.** Its result is a pure function of the policy
snapshot's `version_hash` and the ledger's cited range, both already content-addressed,
so a coverage digest would be a second address for facts that have one.
[docs/coverage-derivation.md](docs/coverage-derivation.md) documents the derivation well
enough for a second implementation — and records the impurity that writing it exposed:
`actions_audit` stores action types but **not resolved effects**, so effect exercise is
*derived from today's rules applied to past traffic*, which every rendering states.

Rendered without `--ok`/`--bad`. Those are verdicts' alone: red on a receipt means *this
was denied*, a past fact; on a coverage cell it would mean *this would be denied*, a
prediction about a class — and a colour that means two things means neither.

### Added — `python -m scripts.gate`, the documented way to run gates

A gate now runs through `subprocess` with **no shell and no pipe**, and passes only when
the exit code **and** the declared output contract both hold. It prints what it ran,
where, and with which tool versions, so its output cannot be mistaken for a hand-run
transcript.

This exists because a documented rule was not holding: `cmd | tail` then `$?` reads
*tail's* status, and that landed for the third time despite being written down. Laws
pushed into construction outrank laws kept in memos. `tests/test_gate_discipline.py`
refuses any committed shell that reads `$?` after a pipe, holds the gate contracts apart
so one gate's output cannot satisfy another's, and asserts a path carrying a backslash
escape survives being passed as argv.

Building it reproduced the very defect it targets: the first contract table declared the
tests gate as the literal `" passed"`, which is a substring of ruff's *"All checks
passed!"* — so a lint run would have satisfied the test gate. The contracts are now
patterns requiring a **count**, and a test compares each against every other gate's real
output.
