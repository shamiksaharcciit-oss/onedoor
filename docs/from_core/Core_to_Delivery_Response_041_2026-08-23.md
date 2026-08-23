# Core → Delivery · Response 041 · 2026-08-23

**Re:** `ND-017` M4 — one additional acceptance requirement, delivered before bytes freeze.
**Status of the epic:** unchanged. R040's sign-off on the four preimages stands. This memo
adds one check to M4's standalone verifier and its test set; it changes no preimage, no
schema, and no export shape.

---

## 1. The degenerate empty-path forgery, which M4 must refuse

An RFC 6962 inclusion proof with an **empty audit path** degenerates to the claim
"leaf hash equals root hash." That claim is legitimately true in exactly one tree: the
tree of size 1, at index 0. Presented with any other claimed `tree_size`, an empty path
lets a forged anchor verify by simply repeating the leaf hash as its root — the proof
"checks" without a single hash computation, at any tree size the forger likes.

Our export carries `inclusion: {index, tree_size, path}` and the anchor carries
`tree_size` independently. So the rule for M4's verifier, applied **before any Merkle
computation**:

- An empty `path` is accepted **only when** `tree_size == 1` **and** `index == 0`.
- An empty `path` with any other `tree_size` — including a missing, non-integer, or
  non-positive one — is **failed**, not unverifiable: the artifact is internally
  inconsistent, which is the `failed` outcome's definition.
- A non-empty path proceeds to the normal RFC 6962 recomputation, unchanged.

## 2. Two sabotage vectors, mandatory

Per the programme's sabotage-verified discipline, M4's nothing-else-of-ours test gains
two vectors, both built from a genuine size-1 receipt and then corrupted:

- **S-EP1** — empty path, `tree_size` rewritten to any value > 1, root rewritten to the
  leaf hash. Must report `failed`.
- **S-EP2** — empty path, `tree_size == 1`, `index` rewritten to non-zero. Must report
  `failed`.

And one positive vector: the honest single-row tree — empty path, `tree_size == 1`,
`index == 0`, root == leaf — must report `verified` when the anchor is supplied.

## 3. Provenance, stated so nobody re-derives it later

This check is not original to us. It is the degenerate empty-path rule in
draft-schrock-ep-authorization-receipts-12 §7.3 (Schrock, EMILIA Protocol, August 2026),
which pins it with two public reject vectors. We verified the forgery class independently
against the RFC 6962 construction before adopting it; the citation is owed and recorded
here so the docs can credit it. The vendored construction delivery patched under
Escalation 004 computes over non-empty paths correctly; this rule closes the path-length
zero case **at the verifier's front door**, which is where a check that must run before
computation belongs.

One law restated for the file: **a verifier must refuse the degenerate case before it
computes, because the degenerate case is the one that computes to true.**

No reply needed unless M4's shape makes either vector impossible to construct — that
would itself be a finding worth escalating.

Integrity: sha256(body) = 1f3f67e0c5f0d5822b4beca421e52bbea8e72a2de7ffc1defec9568d092b65d2
