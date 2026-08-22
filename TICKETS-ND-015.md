# `ND-015` — signed decision receipts (Ed25519) · decomposition

**Ticket:** `ND-015`, `0.4.x`, P2 / AADP A2, A10. Second leg of the crypto epic.
**Baseline:** `7651774`; 523 passed / 9 skipped, four gates green, CI green both jobs.
**GO:** R037 §2.
**Pre-settled by R037 and not reopened here:** the private key is deployer-supplied and
**never** enters the repo, the database or any receipt; **`key_id` is derived**, a
fingerprint of the public key bytes, never assigned; an **unknown key is
`unverifiable`** — never `failed`, never trusted; **rotation is append-only** with a
keyring that only grows, because public keys are evidence and evidence is not deleted;
signing is **per-row over `row_hash`**, under the standing AST guard.

**Already in place, checked not assumed:** `sig`, `key_id` and `alg` exist on
`actions_audit`, dark since migration `0007`, and are already classified `EXCLUDED` in
`docs/row-preimage.md` §4 with the reason — *a signature attests the row hash and cannot
precede it*. So this ticket adds **no hashed column** and needs **no preimage version**.
`/3` remains available and ordinary if a later ticket wants one; this one does not.

---

## 1. The finding that has to be settled before any code: where the keyring lives

R037 leaves "keyring storage shape" open. It is not a storage question. It is this:

**A signature verified against a public key found in the same store as the data it
signs proves internal consistency, not authenticity.** An attacker who can write the
database can add their own public key, re-sign the rows they altered, and hand you a
store that verifies perfectly against itself. That is R028's *"a digest checked against
a file's own bytes is a tautology dressed as a check"*, one layer up — and it is the
exact failure this whole product exists to refuse.

The append-only triggers do not close it: they stop `UPDATE` and `DELETE`, not
`INSERT`, and a keyring must accept inserts or rotation is impossible. The chain does
not close it either — a keyring row is not an `actions_audit` row and is not chained.

So the storage shape follows from a trust decision, and delivery proposes stating it in
three parts rather than choosing silently:

1. **The keyring lives in the store** (migration `0014`, append-only triggers matching
   `actions_audit`'s), because a verifier handed one file should be able to attempt
   verification at all. Convenience of verification, not the source of trust.
2. **The trust anchor is the deployer's own copy of the fingerprint**, held outside the
   store — published, pinned in a config, or simply written down. Verification takes an
   *expected* `key_id` and reports what it found.
3. **Verifying against the store's keyring alone is reported as a distinct, weaker
   outcome** — the signature is internally consistent and nothing vouches for the key.
   That is not `verified`. Delivery proposes it is `unverifiable`, the same word R037
   already assigns to an unknown key, because "I found a key that works, in the place
   an attacker would put one" and "I have never seen this key" are the same amount of
   assurance: none.

**This is the decomposition's first question (§5)** — specifically whether (3) is
right, because it means a store on its own can never say `verified` for a signature,
and that is a deliberate and slightly uncomfortable design choice.

## 2. The library boundary — and a distinction worth drawing precisely

**onedoor has no crypto dependency today.** Checked: the runtime requirements are
`pydantic`, `pydantic-settings`, `pyyaml` and `tzdata`. Neither `cryptography` nor
`PyNaCl` is installed, and the standard library has no Ed25519 — `hashlib` gives
SHA-512 and nothing on the curve. So this ticket adds the package's **first**
cryptographic dependency, and `ND-040`/U1 set a high bar for that.

**The bar is met differently here, and the difference matters.** U1 refused a
dependency because *IDNA output can change between library versions* — a
canonicalization that changes under an upgrade is an instrument change wearing a patch
release. **Ed25519 is not like that.** RFC 8032 fully specifies it and it is
deterministic: a correct implementation produces identical signature bytes for the same
key and message, forever. There is no version-sensitive output to defend against.

So pinning here is a **supply-chain and availability** concern, not a determinism one,
and the two want different treatments:

- **`alg` is the instrument identity**, and the column already exists. It records
  `ed25519` (RFC 8032) — the algorithm, which is what a third-party verifier needs.
  Recording a library *version* in evidence would imply the output depends on it, which
  would be false, and this programme does not put misleading identities in receipts.
- **Pin in CI and dev**, so the gates are reproducible. **Range in the package**
  (`>=x,<y`), because exact-pinning a runtime dependency of a *library* conflicts with
  every downstream that also depends on it — U1's own reasoning, applied where it still
  holds.

**Recommended:** `cryptography`, for Ed25519. It is the ecosystem default, ships wheels
on every platform CI runs, and its Ed25519 is a thin binding over a reviewed
implementation.

**X-6 forces a decision, and it is §5's second question.** *Alarm dependencies are hard
requirements, never optional extras.* Is signing an alarm dependency? If yes, the crypto
package becomes a **hard runtime requirement** for every install of onedoor, including
deployments that will never enable signing. If no, it is an extra — and then a
deployment that intended to sign but has no library installed must not silently write
unsigned rows.

## 3. The no-key cases, which are two cases and not one

R037 asks whether verification with no key configured is `absent` or `unverifiable`.
Stated apart, the answer is clean and both words get used:

| Case | Outcome | Why |
|---|---|---|
| The row has **no signature** (`sig` NULL) | **absent** | Signing was not in operation — the same fact, and the same word, as the chain before `ND-001` ran |
| The row **has** a signature and the verifier has **no keyring** | **unverifiable** | A claim was made and cannot be checked. Never a skip |
| The row has a signature and the keyring has **no matching `key_id`** | **unverifiable** | R037's ruled case: the signature may be perfectly good; nothing vouches for it |
| Signature present, key present, bytes do not verify | **failed** | The claim checked false |

The trap to avoid is the fourth row swallowing the second and third. A verifier that
reports "no signature to check" when it means "I cannot check this signature" is the
two-outcome collapse, and it would be reported in the direction of reassurance.

## 4. Work order

- **K1** — the keyring: migration `0014`, append-only, `key_id` derived as a
  fingerprint of the public-key bytes, rotation as an audited append. Waits on §5's
  first ruling only for the *reporting* semantics; the table shape is unaffected.
- **K2** — the signer: per-row over `row_hash`, inside the writer's existing
  transaction, `alg = ed25519`. No key configured means no signature and no error.
- **K3** — the verifier, landing where every other check does:
  `receipt.py::_check_signature`, four outcomes, and **the viewer changes not at all** —
  the same acceptance test `ND-001` passed.
- **K4** — rotation: a second key, old receipts verifying forever under the old public
  key, and the keyring proven to grow rather than replace.
- **K5** — the adversarial tests: a re-signed tampered row, a substituted public key, a
  signature lifted from one row onto another (`row_hash` is in the signed bytes, so this
  must fail), and a signature over a `/1` row verified after the store moved to `/2`.

## 5. The questions this decomposition surfaces

**1. Can a store ever say `verified` for a signature on its own?** (§1.) Delivery
proposes **no**: verification against a keyring found in the same store is internal
consistency, and an attacker with write access supplies both halves. The honest report
is `unverifiable` unless the caller supplies an expected `key_id` from outside. This is
uncomfortable — most systems would call it verified — which is exactly why it is core's
to rule rather than delivery's to assume.

**2. Is signing an X-6 alarm dependency?** (§2.) If yes, `cryptography` becomes a hard
runtime requirement for every onedoor install. If no, it is an extra — and the
decomposition then needs a third state for *"signing was configured and the library is
missing"*, which must be an error at startup rather than a stream of unsigned rows.
Delivery leans to **hard requirement**: a receipt product whose signatures are optional
at install time will have deployments that believe they are signing and are not.

**3. Does `alg` record the algorithm only, or the library too?** (§2.) Delivery
proposes **algorithm only** — Ed25519 is deterministic per RFC 8032, so a library
version in evidence would imply an output dependence that does not exist, and a
misleading identity in a receipt is worse than none. Raised because every other
instrument in this programme *does* record its implementation version
(`canon_schema`, `snapshot_schema`, `unicode_version`), and departing from that pattern
should be a decision rather than an oversight.

K1's table shape, K2 and K4 are unblocked. K3's reporting semantics wait on question 1;
the dependency declaration waits on question 2.
