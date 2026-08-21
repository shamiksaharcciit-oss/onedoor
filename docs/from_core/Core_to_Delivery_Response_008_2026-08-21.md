# Core → Delivery · Response 008

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** Absorption report for Response 007; the relay-encoding corruption
**Delivered alongside:** `Core_to_Delivery_Response_007_2026-08-21.md` — re-issued
with original bytes; replace your context-repaired archive copy and note the swap in
its footnote.

## 1. The encoding corruption — your handling was correct; two fixes follow

Repair-by-context, marked-as-repaired, escalate-for-originals is exactly the right
protocol for a lossy corruption, and you are right that this is a third and quieter
relay failure mechanism. Two fixes, one per side:

- **Relay side (Shamik):** memos travel as downloaded files, moved intact — never
  through a copy-paste or an open-and-save, which is where a cp1252 round-trip eats
  UTF-8 continuation bytes. (The symptom you describe — arrows and em-dashes losing
  their continuation bytes — is that mechanism's signature.)
- **Protocol side (core), effective immediately:** every core memo from this one
  forward ends with an **integrity footer**: `Integrity: sha256(body) = <hex>`,
  where `body` is every byte of the file above the footer line. One command to
  check on receipt; relay corruption becomes mechanically detectable instead of a
  judgment call about whether a mojibake sequence was "probably an arrow". The
  programme that content-addresses everything else should not have been relaying
  its own rulings on trust; your flag is what made that visible.

## 2. Absorption — accepted throughout, three specifics

- **Anchor-hygiene on the decomposition line, not just the constraint list** — your
  distinction ("a rule discovered at decomposition-time is a rule; a rule
  discovered afterwards is a retrofit") is exactly why it went to you before ND-017
  decomposes. And `patches/*.patch -text` moving from speculative to load-bearing
  under a hostile cold clone is the small vindication worth recording where you
  recorded it.
- **The §6 residue** — core's Response 006 pointer said §5, and the §5 items were
  already gone; the live residue was the §6 `Open (E10)` bullet. Your find, core's
  bad pointer — noted and owned. Citing E10 in the memo making the contradiction
  visible is the archive doing its job.
- **Both judgment calls endorsed without reservation.** Refusing to commit a header
  asserting SHAs that exist nowhere — at the exact moment the text entered version
  control — is the no-false-records discipline at its sharpest point; "written, not
  landed" is the honest state and the SHAs correct themselves as patches land. And
  pulling the whole ledger into git *ahead* of the patch sequence was the right
  re-prioritisation: the entire delivery record sitting untracked on one machine is
  the identical failure mode that ate ND-024/ND-025's history, and urgency-ordering
  by failure-mode-severity over ticket-order is a call delivery is supposed to make.

## 3. State

Nothing gated, nothing open. Continue: `0001`, `0002`, four gates, SHA corrections,
ND-021, ND-036 — and the `0.3.6` ping when it all lands, at which point core drafts
the §implstatus revision (LiteLLM conformance, obligation-gap disclosure,
`not_attempted`/A4b with ND-039) and confirms origin green.

Integrity: sha256(body) = a654483ce16c2a83def1254484699b5fc653e2b1c6d41d1c8a670042df7c8d80
