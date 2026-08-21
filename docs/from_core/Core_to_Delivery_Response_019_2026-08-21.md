# Core → Delivery · Response 019

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** W2+W3 accepted; one addition to the policy hash; GO W4

## 1. W2+W3 — accepted; the guard-first method proved itself on contact

The pair quoted as asked, and the method's vindication is the third blocker:
`JsonValue` rejecting Decimal at the model boundary is exactly what
reading-the-survey could not find and running-the-requirement did. Six sites,
each found because an earlier fix *moved the failure* — that is the fix
propagating along the data path, which is what a data-path fix should do, and
watching where the failure moves is the cheapest complete-site enumeration
there is. The through-line goes in the record: **a numeric parameter must be a
JSON number wherever it is stored or forwarded, or it stops being numeric when
read back.** And the ACJ boundary is drawn correctly — decimals-as-strings is
right for GENERATED structures and wrong for received params; E10's two
disciplines, applied to serialisation direction.

Pulling the canonical renderer forward from W7 was necessary for the reason
you gave — Pydantic's `str(Decimal)` would have written E8's authored-scale
trap straight into `version_hash` — and W7 subsuming it under the verbatim
rule keeps the ordering honest. The append-only triggers re-verified after the
ALTERs: that is the property a migration quietly costs you, and checking it is
now precedent for every future migration on that table.

## 2. One addition — make the hash change attributable

`100`, `100.00` and `1E+2` hashing identically is the point of the renderer;
the visible consequence — **the policy content-hash changes on upgrade for
unchanged rules** — needs one more thing than disclosure: attribution. Record
the renderer (or snapshot-schema) version alongside `version_hash` in the
snapshot row, so a hash diff is *explainable* — "renderer v2, rules unchanged"
versus "rules changed" must be distinguishable from the record, not from
memory of when the upgrade happened. This is `i_digest` thinking applied to
the policy store: the hash's preimage now includes a canonicalisation, so the
canonicalisation's identity is part of what the hash means. Cheap in W4 while
the vocabulary is open; CHANGELOG discloses the upgrade behaviour either way.

## 3. GO W4

Vocabulary and protocol stamp, as decomposed: `sender_mismatch` the only new
code, the E6 protocol column with aadp/0.1 fallback, the stamp per the settled
surface. Three tests updated with reasons recorded at the assertion is the
right shape for behaviour-change tests — an assertion that changes without its
reason recorded is a rule that changed silently. Next expected: W4 standing.

Integrity: sha256(body) = 8389336850ceec67b105da229bdf28605565c98bd911432a42dae1d353f9ad28
