# The onedoor receipt digests — `E`, `I`, `T`, `v`

**Normative.** This document defines the exact bytes each of `e_digest`, `i_digest`,
`t_digest` and `v_digest` is computed over. It is written so an implementer with no
access to the source can reproduce every digest from this text alone (P2-06), and
`tests/guardrail/test_receipt_digests.py` holds a second implementation built from this
document rather than from the module.

**Signed off by R040 §1**, with two amendments recorded in §5. **Frozen from the first
sealed row.** These columns live on an append-only table: there is no migration that
fixes a defect here.

Companion to [`row-preimage.md`](row-preimage.md), which defines `row_hash`. The two are
separate on purpose: `row_hash` seals the row, and these four describe it.

---

## 1. Algorithm and encoding

Every digest is **SHA-256, lowercase hex, over `canonical_bytes` of the object below** —
the vendored `rederivable-manifest` v3 canonical JSON: keys sorted by code point,
separators `,` and `:`, UTF-8, no ASCII escaping, **floats forbidden**.

**No concatenation appears, so the `len8` dialect is not reached.** Stated rather than
implied: R039 asked for `len8` *where concatenation appears*, and a canonical object
needs no framing. Decorating this with an unused dialect would be worse than saying so.

**`E`, `I` and `T` are carried as opaque digests** in the receipt, never as inlined
structures — because `I` will generalise from verdict-instruments to stage-attribution
instruments, and inlining would re-hash frozen rows.

## 2. `E` — the sealed evidence: what the decision was made *from*

```json
{"kind": "onedoor/decision-evidence/1",
 "params_digest": "<sha256 hex of params_json's bytes, hashed verbatim>" | null,
 "params_provenance": "received" | "serialized" | null,
 "request_id": "<uuid text>",
 "action_type": "<text>",
 "source": "<text>",
 "policy_version": "<64 hex>" | null,
 "snapshot_schema": "<text>" | null}
```

`params_digest` is a digest of the **frozen bytes**, hashed verbatim — never inlined,
never re-serialised. E10's received-data discipline, and a privacy property in the same
move: **a receipt can be handed to a third party without handing over the request body.**

## 3. `I` — the instrument: what *did* the deciding

```json
{"kind": "onedoor/decision-instrument/1",
 "protocol": "aadp/0.2" | null,
 "preimage_version": "onedoor/row-preimage/2" | null,
 "canon_schema": "onedoor/url-canon/1+py3.12" | null,
 "opaque_class": "onedoor/opaque-hosts/1" | "policy" | null,
 "snapshot_schema": "onedoor/policy-snapshot/2" | null}
```

Every identity the engine already records beside a verdict, gathered. **The anchor
cadence is deliberately absent** — see §5.

## 4. `T` — the trust set: what you must **trust** to accept the verdict

```json
{"kind": "onedoor/decision-trust/1",
 "keys": ["ed25519:<64 hex>"],
 "closure": "store-closed" | "anchor-closed"}
```

A **statement about what else must be trusted**, never a second copy of facts `E`
already seals. `keys` is a list because a verifier crossing a key rotation needs more
than one. `closure` declares what the trust set closes over:

- `store-closed` — you are trusting **this store** for the resolution.
- `anchor-closed` — this deployment publishes Merkle roots, so the closure can rest on
  a root held **outside** the store.

`closure` is a property of the deployment, known when the row is sealed. It says what a
verifier *will be able to* rely on, not whether a particular anchor exists yet —
anchoring is periodic, and a freshly written row is normally not yet anchored.

## 5. `v` — the verdict

```json
{"kind": "onedoor/decision-verdict/1",
 "decision": "<text>", "reason_code": "<text>",
 "nominal_tier": N, "effective_tier": N,
 "outcome": "<text>" | null,
 "budget": "<the stored canonical JSON text>" | null,
 "approval_ref_status": "<text>" | null}
```

`budget` is carried as its **stored text**, not re-parsed and re-rendered: it was
canonicalised when written — decimals as canonical strings, never floats — and
re-rendering here would let the sealed bytes and the stored bytes diverge.

## 6. The two amendments, recorded with their reasons

**`T` does not carry `policy_source`.** It was proposed and R040 §1 removed it: the
policy hash already lives in `E` as `policy_version`, where it is an *input identity* —
what was in force. The same hash in two preimages is two answers to one question at the
exact layer where drift becomes undetectable — **X-14, inside the seal itself**. What
`T` owes a verifier is what must be *trusted*, and trusting that a version hash resolves
to real policy content is precisely what `closure` declares.

**`I` does not carry `anchor_cadence`.** It was proposed with the consequence flagged —
a cadence change would re-identify the deciding instrument for every row after it — and
R040 §2 ruled the consequence *was the defect*, not the point. Cadence schedules
**anchoring**, not **deciding**: an ops-schedule tweak must not split `i_digest` cohorts
for a reason no instrument comparison should have to care about. Cadence declares in the
anchoring configuration and is recorded on the **anchor object** (§7), where a change is
visible in exactly the artifact stream it governs.

## 7. Where cadence does live

The anchor object, published outside the store:

```json
{"schema": "onedoor/anchor/1", "alg": "sha256", "tree": "rfc6962",
 "root": "<64 hex>", "tree_size": N, "first_seq": A, "last_seq": B,
 "cadence": "<declared>", "sealed_at": "<RFC3339 UTC>"}
```

See [`TICKETS-ND-017.md`](../TICKETS-ND-017.md) for the export path and the third-party
membership check that this object is half of.

## 8. Golden vectors

Held in `tests/guardrail/test_receipt_digests.py`, each named for what it fixes:

1. **The empty trust set** — `sha256(canonical([])) = 4f53cda1…b945`, the value the
   vendored artifact's own manifests carry. This scheme is that scheme; the arithmetic
   proves the reading rather than the reading proving itself.
2. **Key order is erased** — two objects differing only in key order digest identically.
3. **Absent is not empty** — `null` and `""` produce different digests, in every field
   that can be either.
4. **One-byte perturbation** — changing a single character of any field moves the digest.
5. **`policy_version` is in `E` and not in `T`** — asserted directly, so the amendment
   cannot be quietly undone.
6. **No cadence in `I`** — likewise.
