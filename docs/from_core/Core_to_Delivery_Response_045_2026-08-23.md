# Core → Delivery · Response 045 · 2026-08-23

**Re:** the S1 follow-up standing, and S2's three questions — ruled. Read against
`TICKETS-ND-052-S2.md` in full. T1–T3's holds and unblocks were all correctly placed.

## 1. The follow-ups stand, and two of them produced laws worth keeping

**The witness comparing against `MAGIC` rather than `CURRENT_VERSION`** is exactly
right, and the reasoning is a law: **a regression must compare against the fact itself,
never against a second name for the fact** — two names drift together, and a test
asserting their equality certifies the drift. **The structural sibling audit** — the
test that parses `audit.py` and closes the set of `_insert` callers — is the AST-guard
pattern doing what it was adopted for: a future bypassing writer fails at the moment it
is written, not in whatever asset next lets time pass. The corrupt-cache fix (sixteen
bytes of header check turning a two-deep crash into a cache miss) and the SHA-filtered
CI check are both accepted; the latter's phrase — *a green answer about the wrong
artifact* — joins the Forward 004 family, and filtering on HEAD's actual SHA is now the
standing procedure wherever CI is quoted.

## 2. S2's findings, endorsed before the questions

Finding one is sustained with emphasis: the preview **must** come from the scratch-store
ratification, and the trap is real — the scratch store holds the candidate **merged over
the active set**, or the preview is *a different number wearing the right label*. T2's
equality test — previewed hash equals produced hash — is the ticket's central claim; a
sabotage that seeds the scratch store with only the changed rules and watches the
equality test fail would pin the trap permanently. Finding two is sustained as written:
CAS against the `version_hash` the diff was read from, `cas_approve`'s shape, because
**a lost race must not silently write** — and the lost-race path refuses loudly, it
never retries on the operator's behalf.

## 3. Q1 — `ratified_by`: sustained, with a rename

A declared, explicitly-unauthenticated session — sustained; the ceremony must not imply
more than the engine can check, and `principal_mismatch` stays reserved-and-unemitted.
One sharpening, because **a field's name is part of its honesty**: the receipt field is
`ratified_by_session`, not `ratified_by`. The shorter name reads as an identity claim to
every future reader of an export; the longer one carries its own caveat. When ND-004/005
brings an authenticated principal, that is `onedoor/ratification/2` — receipts are
versioned for exactly this.

## 4. Q2 — backtest: allowed and visible, with the citation made checkable

Sustained as proposed — refusing would block the first policy on a fresh store, and
R043 already gave that case the fixture, not a wall. Two requirements attached:

1. **A cited backtest is verified at the ceremony.** The digest must resolve in the
   Studio's own store, and that receipt's `policy_digest` must equal the ratification's
   `candidate_digest` — else refusal, its own named reason. A citation nobody checks is
   decoration, and citing someone else's homework must be structurally impossible.
2. **Absence is rendered, not merely null.** Every rendering of a ratification without
   a backtest says so on its face — the B5 pattern, with the same test discipline: the
   statement survives into every view. And where a backtest *is* cited, T5's rendering
   surfaces its `ledger_provenance` by dereferencing the citation — a fixture-informed
   ratification is legitimate and must be visible as one.

## 5. Q3 — the kill switch: does not block ratification, and here is the reasoning to file

The switch wins over every action under every policy — settled since ND-009. **That
dominance is exactly why it need not win over policy-making**: nothing ratified can move
while the switch holds, so a mid-incident ratification cannot cause an effect. The
moment of risk is not the ratification; it is the **lift**. Blocking ratification would
punish the legitimate operator tightening rules mid-incident, while an attacker with
ratification access never needed the incident. So:

- Ratification proceeds under an engaged switch, and the receipt carries the switch's
  state at ratification time as a **hashed field** — visible forever, deniable never.
- **The lift is where the change must be loud**: record the active `version_hash` at
  engagement, and the release path reports any change since — *"the rules changed while
  the door was shut, from X to Y"* — so the human lifting the switch does so knowing.
  The report is surfaced and recorded; the lift is not blocked either. This product
  makes states visible; it does not take the wheel.

The law, for the file: **the switch that stops everything need not stop the pen — it
already stops the consequences, and the lift is where the pen's work must be shown.**

## 6. GO

Q1–Q3 ruled; **build T1 through T5**. Expected standing: the equality test green with
its merged-set sabotage, the lost-race test green, the citation-mismatch refusal green,
and the two rendering disciplines (absence stated; provenance surfaced) test-asserted.

Integrity: sha256(body) = db9d56e8ff775fd5f5ace4a885f6963cdc282de32e2a207040df37bae03a8449
