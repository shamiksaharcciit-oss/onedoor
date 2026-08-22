# `ND-017` — content-addressed receipts + Merkle anchoring · decomposition

**Ticket:** `ND-017`, `0.4.x`, P3. **The crypto epic's last.** Its close opens `ND-052`.
**Baseline:** `270b4cd`; 545 passed / 9 skipped, four gates green, CI green both jobs.
**GO:** R039 §2.
**Settled and cited, not re-derived:** **R038 §4** is the anchor's law — *an anchor is
worth exactly the independence of where it lives*; **X-8** — anchor only what you have
re-verified; `anchor_ref` is already `EXCLUDED` from the row preimage with its reason;
`E`/`I`/`T` stay **opaque content-addressed digests, never inlined structures**, because
`I` will generalise from verdict-instruments to stage-attribution instruments and
inlining would re-hash frozen rows on an append-only table; the RFC 6962 construction is
vendored, patched by delivery under Escalation 004, and self-tested.

**No preimage version.** `e_digest`, `i_digest`, `t_digest`, `v_digest` and `anchor_ref`
have been dark since `0007` and are already `EXCLUDED` — computed *from* the row, or
written after it. `/2` stands.

---

## 1. The four preimages, proposed for sign-off before bytes freeze

The programme already fixes what these letters mean, and the vendored artifact shows
the shape: a manifest carrying `E`/`I`/`T` as **digests** and `v` inline. Read from
`manifest.schema.json` rather than invented — `t_digest` on the shipped manifests is
`4f53cda1…b945`, which is SHA-256 of `[]`, the canonical rendering of an empty trust
set. The scheme below is that scheme, applied to a PDP decision.

**Every digest is SHA-256, lowercase hex, over `canonical_bytes` of the structure
below** (vendored ACJ: code-point-sorted keys, tight separators, UTF-8, no floats).
**No concatenation appears anywhere**, so `len8` is not reached — stated explicitly
because R039 asked for it *where concatenation appears*, and the honest answer is that
a canonical object needs none. Where a field carries **received** bytes they enter as a
**digest of those bytes hashed verbatim** (`digest_file`'s discipline), never inlined
and never re-serialised — E10's two disciplines meeting inside one preimage.

### `E` — the sealed evidence: what the decision was made *from*

```json
{"kind":"onedoor/decision-evidence/1",
 "params_digest":"<sha256 of params_json's bytes, verbatim>",
 "params_provenance":"received|serialized",
 "request_id":"…","action_type":"…","source":"…",
 "policy_version":"<the version_hash in force>",
 "snapshot_schema":"onedoor/policy-snapshot/2"}
```

The params are a **digest of the frozen bytes**, not the bytes: received data is hashed
verbatim and never re-rendered, and keeping it a digest is also what lets a deployer
hand over a receipt without handing over the request body.

### `I` — the instrument: what *did* the deciding

```json
{"kind":"onedoor/decision-instrument/1",
 "protocol":"aadp/0.2",
 "preimage_version":"onedoor/row-preimage/2",
 "canon_schema":"onedoor/url-canon/1+py3.12"|null,
 "opaque_hosts":"onedoor/opaque-hosts/1"|null,
 "snapshot_schema":"onedoor/policy-snapshot/2",
 "anchor_cadence":"<declared>"}
```

Every identity already recorded beside a verdict for exactly this reason
(`canon_schema`, `snapshot_schema`, `opaque_class`) gathered into one digest. **Opaque
by construction**, so `I` can grow the stage-attribution fields the forensics pillar
will need without touching a sealed row.

`anchor_cadence` sits here because R039 says cadence is *declared config inside the
instrument* — **and that has a consequence worth naming: changing the cadence changes
`i_digest` for every row sealed afterwards.** That is X-7's shape (a declaration change
is visible; a fault perturbs behaviour, never its declaration) and delivery reads it as
intended rather than incidental. **Flagged in §5 in case it is not.**

### `T` — the trust set: what you must trust to accept the verdict

```json
{"kind":"onedoor/decision-trust/1",
 "keys":["ed25519:…"],
 "policy_source":"<version_hash>",
 "closure":"store-closed|anchor-closed"}
```

**This is the one delivery is least sure of, and §5 asks.** In the vendored manifest `T`
is the declared *closure* — `[]` means archive-closed. For a PDP decision the analogous
question is "what else must a verifier trust?", and the honest answer today is: the
signing keys, and the policy source. `closure` names which — `store-closed` when
everything came from this store (R038 §1's `self_consistent` world) and `anchor-closed`
when a published root is involved.

### `v` — the verdict

```json
{"kind":"onedoor/decision-verdict/1",
 "decision":"…","reason_code":"…",
 "nominal_tier":N,"effective_tier":N,
 "outcome":"…"|null,"budget":{…}|null,
 "approval_ref_status":"…"}
```

The decision's own content, canonical. Numbers are canonical decimal strings inside
`budget` already, so no float can enter.

**Golden vectors** for each, in `tests/guardrail/test_receipt_digests.py`, and a
**second implementation built from `docs/receipt-digests.md`** — the P2-06 pattern that
`docs/row-preimage.md` already carries, because a definition nobody else has built from
is a description of one function's behaviour.

## 2. The export path, measured against R038 §4's metric

**An anchor is worth exactly the independence of where it lives.** A root stored beside
its leaves proves internal consistency and nothing more — the same shape as the keyring,
one level up, and `self_consistent` is the word already waiting for it.

So two artifacts leave the store, and both are small enough to publish anywhere:

**The anchor** — what the deployer publishes, outside the store:

```json
{"schema":"onedoor/anchor/1","alg":"sha256","tree":"rfc6962",
 "root":"<64 hex>","tree_size":N,"first_seq":A,"last_seq":B,
 "sealed_at":"<RFC3339 UTC>"}
```

One line of JSON. A file, an endpoint, a commit, a printed line taped to a wall —
**independence is the metric, not the medium**, and the design must not care which.

**The receipt export** — and this is the part the row cannot supply on its own. A third
party holding only the published root and one receipt must verify membership *with
nothing else of ours* (R039's acceptance shape). RFC 6962 inclusion needs the leaf
digest, the index, the tree size and the audit path — **none of which is in
`actions_audit`**. `anchor_ref` names the anchor; it cannot carry a proof. So the thing
that travels is an **export**, not a row:

```json
{"schema":"onedoor/receipt/1","row_hash":"…","seq":N,
 "e_digest":"…","i_digest":"…","t_digest":"…","v_digest":"…",
 "sig":"…","key_id":"ed25519:…","alg":"ed25519",
 "anchor":{…the anchor object…},
 "inclusion":{"index":I,"tree_size":N,"path":["…","…"]}}
```

**Acceptance is a script that takes those two files and nothing else**, and reports
membership. If it needs the database, the design has failed §4 — and the test asserts
that by running the verifier in a directory containing only the two files.

## 3. X-8, which decides the order of operations

*Anchor only what you have re-verified.* So anchoring is: **verify the chain over the
range → compute the root → seal the anchor → only then write `anchor_ref` back**. The
verification is not decorative and it is not optional: an anchor over a broken chain
would publish a root that certifies damage, permanently and in public.

`anchor_ref` is written **after** the row was sealed, which is exactly why it is
excluded from the preimage — and its integrity is guarded by the inclusion proof rather
than the row hash. An edited `anchor_ref` fails the proof, which is the right detector.

## 4. Four outcomes at the anchor, again

| Outcome | When |
|---|---|
| **verified** | the published root was supplied, the proof checks, membership holds |
| **self_consistent** | the proof checks against a root found **in this store** — real, and not independence |
| **absent** | not anchored yet. Anchoring is periodic; a recent row is normally absent |
| **unverifiable** | anchored, and the root could not be obtained — or the proof is half stored |
| **failed** | the proof does not check |

`absent` matters more here than anywhere: **anchoring is periodic by design**, so the
most recent rows are always un-anchored and that is not a fault. A viewer that showed
them red would train an operator to ignore red.

## 5. The questions this decomposition surfaces

**1. Are the four preimages right?** (§1.) Signed off before bytes freeze, per
`CONFORMANCE.md` §6's flag. `T` is the one delivery is least sure of: the vendored
manifest's `T` is a declared closure over an archive, and a PDP decision's analogue is a
judgment call rather than a translation.

**2. Is `anchor_cadence` inside `I` intended?** (§1.) It follows from R039's *cadence is
declared config inside the instrument*, and the consequence is that changing cadence
changes `i_digest` for every row sealed afterwards. Delivery reads that as the point —
a declaration change should be visible — but it is a consequence worth confirming rather
than discovering.

**3. Does a root found in the store report `self_consistent`?** (§4.) It is R038 §1's
ruling applied one level up, and delivery believes it follows directly. Raised only
because it means **a store on its own can never say an anchor is verified**, which is
the same slightly uncomfortable place — and now the second time this product refuses to
vouch for itself.

Work order: **M1** the four digests + spec + second implementation (blocked on Q1/Q2);
**M2** the anchor table (migration `0015`, claimed) and the sealing path under X-8;
**M3** the two exports; **M4** the standalone third-party verifier and its
nothing-else-of-ours test; **M5** the viewer's anchor line, which should need no change
to the page beyond a new check appearing — the fourth time that acceptance holds.
