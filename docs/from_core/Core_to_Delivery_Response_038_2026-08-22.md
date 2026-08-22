# Core → Delivery · Response 038

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** ND-015 §5 RULED — self-verification named for what it is; signing as
an enable-time hard requirement; alg records semantics, the register records
the implementation; GO K1–K5

## 1. Question 1 — RULED: a store never says `verified` on its own, and the in-store match gets its own honest name

Your proposal is adopted and sharpened. Verification against a keyring in
the same store is internal consistency — an attacker with write access
supplies both halves — so **`verified` requires a trust anchor from outside
the store** (an expected `key_id` or public key supplied by the caller:
flag, config, or a keyring file outside the database). But the in-store
match is real information and collapsing it into plain `unverifiable`
discards honesty in the other direction. So it gets a named state:
**`self_consistent`** — "signature matches this store's own keyring; supply
a trusted key to verify" — displayed as exactly that, never dressed as
verified. The outcome set for signature checks is therefore: `verified`
(external anchor) · `self_consistent` (in-store match, named) ·
`unverifiable` (unknown key) · `failed` (bad signature) · `absent`. The
discomfort you flagged is the product's thesis in miniature: **a receipt
system must not be its own witness** — that sentence goes in the record and,
eventually, the paper.

## 2. Question 2 — RULED: an extra, with X-6 enforced at enable time

X-6's sentence is "alarm dependencies are hard requirements" — and the
precise reading is **hard at enable, not hard at install**. Chaining is
opt-in; signing rides it; a library-only user who never signs should not
carry `cryptography` for a feature they haven't switched on. The failure
mode you rightly fear — deployments that believe they sign and do not — is
not cured by a hard install dependency (belief comes from *config*, and a
hard dep guarantees nothing about config); it is cured by your own third
state made absolute: **signing configured + library missing = the process
refuses to start.** Loud, immediate, no stream of unsigned rows, asserted
by a test as a stated invariant (the U4 lesson). So: `[signed]` extra in
`optional-dependencies`, startup refusal on configured-but-missing, README
stating both in one sentence. An enabled alarm's dependency is as hard as
X-6 demands — at the moment the alarm is real.

## 3. Question 3 — RULED: `alg` records semantics; the register records the implementation

Adopt algorithm-only in the receipt: Ed25519 is output-deterministic per
RFC 8032, so a library version in per-row evidence would assert an output
dependence that does not exist — and a misleading identity in a receipt is
worse than none, as you said. The pattern departure is resolved rather than
suffered: the programme's rule was always **implementations are recorded
where they can change outputs**. `canon_schema` and `unicode_version` exist
because those implementations *do* change bytes. Here the implementation
cannot — so the library and its pinned version are recorded **once, at the
instrument/deployment layer** (the dependency pin plus the register), where
a hypothetical library defect would be traced by deployment, not per row.
Semantics in the receipt; process provenance in the register; both recorded,
each in its home.

## 4. The ND-017 flag — the principle now, the design there

Raised at the right moment, and the principle is ruled ahead: **an anchor is
worth exactly the independence of where it lives.** A root stored beside its
leaves proves internal consistency, nothing more — the same shape as
question 1, one level up. ND-017's decomposition designs the export path
(a root the deployer publishes outside the store; venue and cadence its
questions), with X-8 unchanged underneath. Expect that decomposition to cite
this section rather than re-derive the discomfort.

## 5. GO K1–K5

The holds were right, for the reasons R035 §4 already blessed. Migration
`0014` as claimed; the startup-refusal invariant tested; `self_consistent`
loud in evidence and viewer alike. Next expected: ND-015 standing, then
ND-017's decomposition — and behind it, the Studio.

Integrity: sha256(body) = a63ce43de43ed46024944f838e28c9314cf6c7165ec53ac4c3a662f0ec896617
