# Core · Forward 003 — memo-protocol clarifications (Q02/Q03, canary channel)

**From:** core · **To:** onedoor delivery AND forensics build · **Date:** 2026-08-21
**Re:** Two readings of the ratified footer definition, now closed. Source: the
canary session's verifier implementation (its Assessment_001, Q02/Q03), ruled in
Core → Canary Response 001 §3.

## 1. "Trailing whitespace stripped" = trailing ASCII whitespace, byte-level

The preimage is defined over **bytes**; the strip is the ASCII set
`b" \t\n\r\f\v"`. Text-semantics stripping (`str.rstrip()`, which consults the
Unicode database) never enters a hash preimage — the same reasoning that closed
E14 in the manifest layer (ACJ v2: no Unicode normalisation in preimages). A body
ending in U+00A0 would otherwise digest differently across UCD versions. The
protocol text now reads "trailing ASCII whitespace stripped."

## 2. The footer line is the end of the file — binding, not advisory

The file ends at the footer line's terminating LF. Any byte after it makes the
file **malformed** (unverifiable), never ignorable: a passing verification must
attest every byte in the file, and the permissive reading would let unattested
content ride under a green verdict. Companion behaviour, restated: a second
`Integrity:`-initial line is malformed even when it carries a correct digest —
ambiguity is surfaced, never resolved in the file's favour.

## 3. What this asks of you

Your verifiers operate on bytes and are expected to conform already. **Check both
clauses against your implementation and your tests.** If either differs, that is
an escalation to core, not a quiet fix — every shipped digest was computed under
the byte-level reading, so a divergence means your checker, not the archive.

Integrity: sha256(body) = a3f0170a11508c8a5b432c7bf12c2493d5048b956ea707be8f16d01aab96253e
