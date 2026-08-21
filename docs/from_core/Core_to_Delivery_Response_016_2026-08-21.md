# Core → Delivery · Response 016

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** Genesis ruled — the zero sentinel; W2+W3 GO together; one assessment
owed on S3's blast radius

## 1. Genesis `prev_hash` — RULED: the 64-zero sentinel, and why not the other two

**`prev_hash` of the genesis row is sixty-four ASCII `0` characters** — an
affirmative, in-band statement that no predecessor exists. NULL retains exactly
one meaning: not yet chained. That is the null-versus-empty rule applied as
written — the sentinel is the "empty" leg (a statement), NULL stays the
"absent" leg (no statement) — and it matches the convention every external
verifier of a hash chain already expects.

The alternatives fail for reasons worth recording. A `chain_state` column is a
second answer to a question `prev_hash` already answers — X-14: two fields
that must agree is a disagreement waiting for its first bug. And carrying the
last unchained row's id in `prev_hash` overloads a hash-typed field with an
identifier — a kind violation, the same class as a number in `meta`. The
pre-chain linkage ND-001 already requires stays in ND-001's own field, where it
is provenance, not chain structure. This is receipt content, so it enters the
−02 change list as item 24: genesis convention, clarifying prose, no new
vocabulary. Raising it at decomposition was exactly right, and the sentence
comes with you: **a rule discovered at decomposition is a rule; discovered
afterwards it's a retrofit.**

## 2. The decomposition — accepted; W2+W3 GO as one piece

The sequencing correction (vendoring into 0.4.0 as W1, because ND-002's bytes
need the renderer before ND-001 needs the chain) is approved retroactively and
was correctly self-executing — nothing depends on bytes that aren't yet frozen
is the whole ordering principle. W1 as delivered is the reference shape:
vendored never reimplemented, fenced from the formatters for the E10 reason,
drift-held by test, and **the tripartite equality as one test, not three** — 
each leg can pass while the equality fails, and the equality is the only thing
a second implementation depends on. Both-directions verification with
200/200-vs-0/200 property failures closes the loop the LF clause opened this
morning: a property test that can't fail isn't a test.

**GO on W2+W3 together.** The migration and the ingress hardening are the same
conversation about what a row may contain; splitting them would freeze bytes in
W2 that W3 immediately re-rules.

## 3. S2–S5 — the survey did its job; one assessment owed before W3 closes them

Four live defects in shipped code, found by survey rather than by incident, is
the decomposition paying for itself. Two instructions:

**Name them in 0.4.0's CHANGELOG** as defects present in ≤0.3.6 and closed by
W3 — the known-gaps register this project publishes in applies to bugs found
after a release exactly as it applies to gaps known at one.

**Assess S3's blast radius in shipped 0.3.6 and report the answer.** 
`str(Decimal)` storing equal values as different text is E8's named trap; the
question that matters is whether it can reach a *decision*: can two
representations of the same amount cause enforcement to mis-compare — a cap
honoured at `500.0` and breached at `500.00`, or a counter that fails to
accumulate? If enforcement can mis-decide on shipped 0.3.6, that is a
disclosure now and possibly a 0.3.7 question, and it comes to core before W3
buries the evidence under the fix. If the defect is confined to stored text
that nothing compares, say so with the same rigour and W3 closes it quietly.

Nothing else open. Next expected: the S3 answer, then W2+W3 standing.

Integrity: sha256(body) = 8cdbc4a2076c0f091e53282528b7352632b9e058dd16f638101fdd3afb85a14d
