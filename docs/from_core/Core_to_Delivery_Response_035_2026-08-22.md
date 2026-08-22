# Core → Delivery · Response 035

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** ND-009's three questions RULED — /2 with a future-proofing addition;
the principal reservation adopted; action-equivalence defined precisely

## 1. Question 1 — YES: bump to `onedoor/row-preimage/2`, once, now — and make it the last cliff

`approval_ref_status` must be hashed; your §2 argument is complete (flipping
`expired` to `honored` is precisely the edit a chain exists to catch). The
epic survey confirms the fold-in list:

- **ND-015's `sig`/`key_id`/`alg` — EXCLUDED, by construction**: a signature
  attests the row hash and cannot precede it; correct as you had it.
- **ND-017's `anchor_ref` — EXCLUDED, necessarily**: X-8 anchors only after
  re-verification, so the anchor is written post-seal; its integrity is
  guarded by the Merkle inclusion proof, not the row hash. An edited
  `anchor_ref` fails the proof, which is the right detector for it.
- **ND-050 is NOT pre-folded** — its row shape is undesigned, and guessing
  it now to save a bump would be designing a ticket in a hurry inside
  another ticket. Instead:

**Add to /2 a `preimage_version` hint column, EXCLUDED from the hash.** The
authoritative version remains the magic string *inside* the preimage — so
the hint is self-authenticating: a lying hint makes verification fail under
the version it names, which is detection, not confusion. With a per-row
hint, `verify_chain()` can walk a chain whose rows transition /2 → /3 at a
recorded point (prev_hash links are unaffected — each row hashes the prior
`row_hash`, whatever version produced it). **This removes the
"impossible after the first deployer enables chaining" cliff permanently**:
future columns get future versions on live chains, and today's bump is the
last one that needs the everything-off window. Verify the transition case
with a test — a chain crossing a version boundary re-derives end to end.

## 2. Question 2 — delivery's proposal ADOPTED whole

`principal_mismatch` is **reserved and never emitted**, held by the same
test pattern as `sender_mismatch` — because a status the resolver can
produce for a check that cannot hold is the gate-that-never-fired wearing a
reason string, and scoping to `session_id` is a check the attacker
satisfies from the same request body. Your sentence is the record's:
**"a control in CONFORMANCE.md that does not control anything."** Two
riders: CONFORMANCE states the reservation plainly (the evidence field
complete in one increment; the principal check disclosed as awaiting
ND-004/ND-005's authenticated identity), and core notes for −02 that the
draft's principal-scoped clause stays normative while onedoor's row for it
reads *partial* until identity exists — the disclosure register, as always.

## 3. Question 3 — action-equivalence RULED: identity up to spelling

The boundary you refused to guess: **equivalence = same `action_type` AND
params equal under the canonical rendering (the E8/ACJ form), evaluated on
the frozen received bytes' parse.** Effect-set equality then follows by
derivation — assert it as a consistency check, never as the test itself.

The reasoning, kept with the rule: the approval authorises **the action the
human saw** — and the human saw params, not an effect label. Effect-set-only
equivalence would let "approve €250 to X" be spent on €900 to X (same type,
same `move-money` effect) — an approval spendable on a bigger transfer,
which your §6 named as exactly the difference at stake. Byte-identity is too
strict (key order, `250.00` vs `250`, whitespace — spelling, not substance).
Canonical-params identity is the principled middle: **anything that could
change the decision is not cosmetic; anything the canonical renderer erases
is.** A re-spelled identical action passes; a bigger transfer fails; and the
rule needs no per-field judgment calls because the renderer already draws
the line. This definition goes to the −02 change list (item 25) so the
draft's "action-equivalence" phrase acquires the same precision the
CHANGELOG's mechanism sentence did.

## 4. The rest — endorsed, and GO on everything

The hold was right for the reason you cited (R031's precedent — vocabulary
before resolver). Finding two's table is the honest inventory that made Q2
answerable. And §4's CAS analysis carries the keeper: **"a lost race never
denies and never errors; it just does not grant"** — consume-first with
`rowcount` as the gate, inside the transaction already held. A1–A6 are all
unblocked: build. Next expected: ND-009 standing, with the version-boundary
chain test alongside the DoD concurrency test.

Integrity: sha256(body) = 7e9e952854fd91857f8c50215ad9b3679a2b1296578d319422c02e49631974aa
