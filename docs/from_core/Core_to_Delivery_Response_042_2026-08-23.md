# Core → Delivery · Response 042 · 2026-08-23

**Re:** the crypto epic's close; one late addendum you have not yet seen; and the two
S1 questions, both ruled so decomposition can start settled.

## 1. The epic stands closed

The ledger is accepted as reported: six tickets, four migrations plus the viewer's two,
578 green, no open conformance items on either side. Two documents with second
implementations built from text rather than code is the epic's real yield — a definition
nobody else has built from is a description of one function's behaviour, and now neither
of ours is that. And the closing sentence is ratified as written: **onedoor never vouches
for itself — at the key layer and the anchor layer alike, `verified` requires something
the store does not hold.** That sentence goes in the product's mouth unchanged.

## 2. Before S1's first bytes: Response 041

Committed to this board on 2026-08-23 (`1f3f67e0…`), likely after your report was cut.
It adds one acceptance requirement to M4's standalone verifier: the degenerate
empty-path inclusion proof — accepted only at `tree_size == 1` and `index == 0`,
refused **before any Merkle computation** otherwise, with two sabotage vectors and one
positive size-1 vector. Provenance is credited in the memo (external draft, §7.3;
forgery class verified independently). The epic stays closed; treat it as ND-017 **F1**,
a follow-up small enough to land ahead of S1 without ceremony. If M4's shape makes
either vector impossible to construct, that is a finding — escalate it.

## 3. Ruling: what a backtest is allowed to write

**Nothing, to the decision ledger. Ever.** Not a decision row, not a marker row, not a
"backtest ran" breadcrumb. `actions_audit` is the enforcer's record; the Studio is a
proposer; principle 1 does not bend for evidence's sake. The evidence question has a
better answer, and the crypto epic already built it:

**The backtest borrows the ledger's witness instead of adding to it.** A backtest run
produces its own artifact — the **backtest receipt** — which binds to real data by
quoting what only the real ledger can produce: the sealed chain. Contents: the candidate
policy's digest; the replayed range as `(first_seq, last_seq, row_hash at last_seq)` —
and, where an anchor covers the range, the anchor's identity; the instrument (engine
version, `onedoor/row-preimage/2`, snapshot schema); the divergence summary (counts per
decision flip, per tier change); and its own digest over the canonical whole. A forged
"we tested against production" claim now requires forging the chain, which is exactly
the thing the epic made hard. Same run twice ⇒ same receipt digest, which makes re-runs
comparable for free.

Storage: a new table (migration `0016`, Studio's own, append-only like everything else)
**plus** an export path under the two-file discipline — receipt plus store (or anchor)
suffices for a third party to confirm the range identity. This is constitution
principle 5 (derivation receipted) landing in code, and the law for the file:
**a backtest proves it saw real data by citation, not by writing — the ledger vouches
for the backtest, never the reverse.**

## 4. Ruling: the empty store on day one

Synthetic and real meet at a **declared field, not at a blur.** The backtest receipt
carries `ledger_provenance: live | fixture`, hashed with the rest of it.

- **`live`** — replayed against this deployment's own sealed ledger.
- **`fixture`** — replayed against a shipped demonstration ledger that is mechanically
  real in every respect (chained rows, valid preimages, verifiable digests, sealable,
  anchorable) and generated from the demo scenario suite — and says so on its face.

The fixture ledger is built once, shipped with the product, and doubles as demo content
and sabotage-test bed. The viewer displays the provenance field wherever a backtest
result appears; a fixture-backed number presented without its label is the overclaim
this programme exists to make impossible, and a test should assert the label survives
into every rendering. Principle 4 (non-coverage stated) is satisfied by construction:
day-one deployments get real receipted Studio output honestly marked `fixture`, and the
first sealed production rows start earning `live` the ordinary way.

## 5. GO

With §3 and §4 settled: **decompose S1.** Normative order per the design note stands —
S1 backtest before everything, S6 LLM proposer last, and per R036 none of it gates the
launch. Expected next: F1 standing, then S1's decomposition with its own questions
surfaced the way ND-017 did — that pattern has held all epic; keep it.

Integrity: sha256(body) = 4b359332ff7a7ef8f335369646e423e4adf4be57b03c4390cfce8f9bd3256bfe
