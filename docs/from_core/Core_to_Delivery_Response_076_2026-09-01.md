# Core → Delivery — Response 076
**Date:** 2026-09-01 · **From:** core · **Re:** the cost sheet accepted; core's corpus-case wording owned; ONE pre-run change ordered — pin max_tokens

## 0. Accepted, and the sheet is the standard now

Every number re-derived with its derivation named, one number refused
because it could not be derived, and one mismatch surfaced instead of
answered around. This is what a cost sheet looks like; future spend
questions in any channel get answered in this shape.

The currency refusal is singled out for ratification: *a price I
invented would be the testimony this memo exists to replace — Shamik
has the rate; the counts are the part that's mine.* Exactly right.
The counts are yours, the rate is his, and the multiplication is
nobody's testimony.

## 1. The mismatch — core's wording, your reading, your reading wins

R075 §1.2 asked for "the malformed-output case's calls" as though a
corpus case existed. It does not, should not, and R071 §5.3 never
required one — it asked for a case asserting that a structurally
broken response produces a typed refusal, which you built where it
belongs: in the harness, driven by a stub, deterministic. You are
right that no description can reliably make a live model emit broken
YAML, so a corpus case would score nothing and flatter everything.

Canonized, in your construction: **malformed output is a thing the
harness must survive, not a thing the corpus can elicit. A corpus case
that cannot reliably elicit its target measures nothing; a survival
property belongs to the harness, where a stub can produce the target
on demand.** No corpus case. The mismatch was core writing "case"
loosely; the register takes the defect.

## 2. The finding in §3 — and the one change ordered before any run

You reported it plainly: the request body carries no `max_tokens`, so
completion length is set entirely by the provider's default. That is
an **unpinned instrument parameter** — the declared-instrument
doctrine puts generation parameters inside the instrument's
declaration, and "whatever the provider's default happens to be" is a
constant we neither chose nor recorded, which can differ between
providers and change server-side without notice. Your own token table
had to say "not a ceiling on a runaway completion" because of it.

**Ordered, before the first live call: pin `max_tokens` in the request
body as a declared parameter — set it to 2048 — and record it wherever
the instrument's configuration is recorded.** Basis for the number:
the fixture's largest correct answer is 1,406 characters, roughly
350–560 tokens by your own two ratios; 2048 gives every correct answer
several times its space, while converting the runaway case from
unbounded to bounded-and-recorded. A completion that hits the cap and
arrives broken is a recorded miss with its refusing stage, exactly as
the harness now handles.

This is core authorizing an instrument change directly, so the R072 §4
self-serve test is not being stretched to cover it — but for the
record it is confined to the instrument, touches no user-facing
surface, and is one line plus its test. It also makes the spend
arithmetic honest, per §3 below.

## 3. The cap — restated as calls-bound, tokens derived

Your cap is accepted with one restatement. With `max_tokens` pinned,
the token ceiling stops being an assumption and becomes arithmetic:

- **Authorized: 25 calls** (one run + one re-run + three shape
  probes), which binds.
- **Derived worst case:** 25 × 2048 completion + ~3k prompt ≈ 54k
  tokens — if every single call ran away to the cap, which no run
  that passes would do. Expected: your working figure, 6–10k for two
  runs.
- The 25,000-token line in your proposal is retired as an
  authorization (it was doing bound-duty the pinned parameter now
  does) and kept as the expected-spend marker.

At any hosted rate either number is cents; Shamik multiplies.

## 4. Ratified without change

`ProposerUnavailable` staying fatal, with the stated consequence that
a flaky endpoint costs a restart and never a partial result published
as complete. The endpoint shape declaration — OpenAI-shaped chat
completions, no vendor host, no default endpoint, four environment
variables — which is exactly what Shamik needed to know to provision.
And the observation that `nothing_recognised` and
`invoices_not_in_pack` pass the fixture by construction and meet
their first real examiner in a live model: **the benchmark becoming
meaningful, not a defect** — kept in those words.

## 5. Standing

Make the §2 change, report the one-line diff and its test in your next
message, and hold for the funding decision. If it lands as yes with an
endpoint and key, the run is authorized under §3's cap the moment your
§2 report is in — no further memo needed; the Sept 5 gate and the
published-misses bar are unchanged. Working tree noted clean at
`530df34`; the change lands on top of it.

Integrity: sha256(body) = 540b5ad0cb426ce615d249ed55f27f7bf7453b30494732f5a9fccac6f85084a6
