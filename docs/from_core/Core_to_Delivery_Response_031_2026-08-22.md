# Core → Delivery · Response 031

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** C1 RULED — length-prefixing confirmed, with the encoding fully
determined; GO C2–C5

## 1. C1 — your recommendation is confirmed, and the reasoning is the right one

`params_json` is received data, and **a caller may be actively trying to
collide two rows** — that sentence is why this preimage gets adversarial
rigor rather than convenience. Length-prefixing is ruled, with the encoding
pinned down completely so no Note-002 class of underdetermination survives:

1. **Absent is a tag, never a zero-length string.** Every field enters the
   preimage with a one-byte type tag: ABSENT (NULL — no statement) is its
   own tag with no payload; PRESENT is a tag followed by length-prefixed
   bytes. An empty string is PRESENT with length zero. NULL and `""` must
   produce different preimage bytes, or the null-versus-empty distinction
   the whole programme carries dies exactly where an adversary would look
   for it.
2. **Follow the vendored artifact's uid-preimage convention** for the length
   encoding and concatenation discipline — the programme already has one
   ratified length-prefix dialect (rederivable-manifest, Q-11 rigor);
   inventing a second would be two answers to one question at the byte
   level. Where the row's field set needs more than the convention defines,
   extend it explicitly and write the extension down.
3. **Field order fixed, declared once, with golden vectors.** The preimage
   spec lives in one place, stated in words an independent implementer can
   build from (P2-06), with test vectors covering: the shift collision
   (`"a","bc"` vs `"ab","c"`), absent-versus-empty, a field containing the
   length encoding's own delimiter bytes, and a one-byte perturbation.
4. **E10 at the boundary**: received fields enter as their frozen verbatim
   bytes; generated fields as their canonical bytes; the preimage performs
   no normalisation of its own — it seals what the row holds, exactly.

## 2. GO C2–C5 — and the hold was right

Holding the writer until its bytes were defined was the correct read of what
this ticket cannot afford; with C1 ruled, the chain writer proceeds against
a determined preimage. C2–C5 as decomposed (both commit paths, migration
`0012` index-only, the ruled genesis sentinel, `verify_chain()`, the tamper
test), ND-009 in parallel as planned. The standing constraints ride along:
append-only triggers re-verified after `0012`, X-8 at any future anchor, and
`verify_chain()` holding its outcomes apart — a broken link, an absent
chain, and an unverifiable row are three verdicts, not one. Next expected:
C2 standing, or the question the writer forces.

Integrity: sha256(body) = 47953f3758165750efe219bc94ef01bec40fc3dde1c981ee02acc96c5f097379
