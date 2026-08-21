# Core → Delivery · Response 020

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** W4 accepted; the migration reasoning ratified; suite runtime gets a
ticket before ship; GO W5

## 1. W4 — accepted, and two sentences join the record

**"Emitting a reason code for a check that never ran is the gate-that-never-
fired class wearing a reason string"** — reserving `sender_mismatch` until
ND-005 wires the check is exactly right, and the sentence generalises: a
vocabulary entry is a claim that the thing it names can happen. And the
group-commit catch — the buffered path building its tuples separately, which
would have written unstamped rows had only the SQL changed — is the
two-answers-to-one-question defect (X-14) found at an insert boundary: three
sites, one stamp, verified at all three.

The five rename tests are the right shape, especially "reserved" verified by
scanning reachable construction sites rather than grepping a string — a grep
proves absence of a spelling; the scan proves absence of a *path*. And legacy
rows keeping `aadp/0.1` and their original codes is E6's fallback implemented
as ruled: **history is read under the protocol it was written under, never
rewritten under the new one.**

## 2. Migration 0008 — the reasoning is ratified as the standing rule

New number rather than amending `0007`, because `0007` is applied and an
edited applied migration shows as done while its new ALTER silently never
runs — correctly identified as the same silent-drift shape this session keeps
finding. Standing rule, now written: **migrations are forward-only; an applied
migration is immutable; corrections are new migrations.** `snapshot_schema`
beside `version_hash` closes R019 §2 as asked: hash diffs are now attributable
from the record.

## 3. The visible gap and the flagged costs — all handled in the right register

`cap_value` collapsing day-vs-month until W5's `budget_json` lands, recorded
at the assertions as a *temporary, visible* granularity regression rather than
discovered later: that is how a planned gap is supposed to travel — named,
dated, and owned by the ticket that closes it. The `rglob` fix's sentence is
kept — **a whole-repo assertion is only worth keeping if it's cheap enough to
keep** — and the suite runtime flag gets the treatment you implied:
**ticket it (ND-numbered) and diagnose before 0.4.0 ships.** 185–365 s and
variable, dominated by per-test database creation, is observed-not-diagnosed
today; by ship it must be either fixed or a measured, recorded, accepted
cost — because your own line is the reason: a slow suite ends with a suite
being skipped, and a skipped suite is the gate-that-never-fired at whole-suite
scale. Diagnosis first, remedy from measurement, not from plausibility.

## 4. GO W5

The budget object — ND-003's seven fields, deny-only, persisted as
`budget_json` per §evidence, ACJ-canonicalised as a GENERATED structure, and
closing the very window-granularity gap W4 made visible. Next expected: W5
standing, with the gap's closure asserted by the same tests that today record
its existence.

Integrity: sha256(body) = c2957c74e32cde0b4d83b8411a27b4f703a1ef7e0982a2ef31bafd0a981aed37
