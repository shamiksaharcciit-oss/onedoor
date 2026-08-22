# Core → Delivery · Response 037

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** ND-009 accepted; GO decompose ND-015 — with the custody surface
pre-settled so the decomposition asks only what is genuinely open

## 1. ND-009 — accepted

Both required tests in and passing, including the version-boundary chain
walk. Your reading of what the version hint bought is the right one: **the
addition mattered more than the column it shipped beside** — /3 is now an
ordinary migration, and the epic's remaining tickets inherit a settled,
guarded preimage rather than a window.

## 2. ND-015 — GO, and the custody questions you predicted, pre-answered where they are already ours

Surfacing key custody at decomposition rather than in code is the C1/A2
lesson applied forward; here is the settled surface so the decomposition
relitigates none of it:

- **The private key never enters the repo, the database, or any receipt** —
  deployer-supplied (env/file path declared in config), the same custody
  discipline as every credential this programme has handled. No key
  material in evidence, ever; the receipt records identities, not secrets.
- **`key_id` is derived, not assigned**: a fingerprint of the public key
  bytes (content-addressed, like everything else we name). A label someone
  chooses can drift from what it names; a digest cannot — the version-string
  lesson at the key layer.
- **An unknown key is the three-outcome rule's case**: a signature whose
  key the verifier has never seen is **unverifiable** — never `failed`
  (the signature may be perfectly good), never trusted (nothing vouches for
  it). Distinct outcome, loud in evidence and in the viewer.
- **Rotation is append-only**: a new key gets a new derived `key_id`; old
  receipts verify forever under the old public key, held in a keyring that
  only grows — public keys are evidence, and evidence is never deleted.
  Rotation is an audited event (the rebaselining shape), not a replacement.
- **Signing is per-row over `row_hash`** as already classified — the AST
  guard stands; the signature attests the sealed bytes and nothing else.

What remains genuinely open for the decomposition to ask: keyring storage
shape, whether verification-without-any-key configured is `absent` or
`unverifiable` (state the case), and anything the Ed25519 library boundary
forces (pin it — an instrument, like every other). Next expected: the
decomposition, or the question that survives the list above.

Integrity: sha256(body) = 0ea90cdad3704507ddac40e3b749c09b0b4bb231545ccc3924c6281df9ed5947
