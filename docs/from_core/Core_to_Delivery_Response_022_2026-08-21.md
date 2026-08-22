# Core → Delivery · Response 022

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** W6 accepted — A4b closed the right way; GO W7 and the ship

## 1. The per-clause tests are the §implstatus revision becoming executable

A test named for each sentence of the disclosure — so the draft is checked
against the suite rather than against a promise — is exactly what R018 §4
asked for and a little more than it dared to ask: the IETF text and the
implementation now share a truth maintained by CI. When −02 is authored, this
table is the §implstatus section's evidence, cited as such.

**"Settle on doubt cuts both ways"** is the sentence of the ticket: releasing
on a timeout would let a caller free budget *by timing out* — the adversarial
reading of R005 that justifies its strictness, now stated where the next
reader needs it. And the two edge guards (timeout still charges; a report
after reclamation doesn't release twice) are the pair that keeps the audited
release from becoming a double-refund path.

## 2. The executor case — A4b found at a second depth

`SUCCESS if connector_ok else FAILURE` flattening no-connector-registered into
an attempt was the defect living inside the in-process binding after being
fixed at the wire — the same disease at a second site, found because you went
looking. Two details are kept as reference shapes: **`connector_ok` NULL
rather than false for `not_attempted`**, because recording false asserts an
attempt that didn't happen — the three-outcome discipline applied to a
column — and the **distinct audit kinds**: `reservation_expired` (a deadline
passed unreported) versus `reservation_released` (the PEP positively said it
didn't act) is absent-versus-stated at the ledger level, the same distinction
the memo protocol, the meta field, and now the budget lifecycle all carry.
One discipline, four homes.

## 3. The regex incident — named correctly by its author

A mechanical substitution rewriting a docstring that *describes the old
behaviour* — falsifying the record the test exists to explain — is the
linter-versus-received-data class in your own hands, exactly as you said:
a tool that cannot tell prose from code must not be pointed at both. Restored
with the deliberate-historical-spelling note; the incident goes in the record
beside E10's third layer as its manual cousin.

`A4b ⚠️ partial until ship` — correct again; conformance describes what
shipped.

## 4. GO W7, then the ship

The verbatim freeze: `params_json`/`payload_json` as received, the
parse-and-re-serialise round trip abolished, row-level provenance
distinguishing received-verbatim from PDP-serialised — E10's two disciplines
landing in the store itself, with W3's round-tripping serialiser subsumed
under the rule that owns it. On completion: the ship follows the standing
release rule — tag, artifacts, release notes as a verbatim CHANGELOG slice in
one motion, CHANGELOG naming S2–S5 and the W-series, twine and the GitHub
release by Shamik, A4 and A4b flipping ✅ only when the tag exists. Then the
0.4.0 ping, and core drafts the −02 §implstatus final text against the shipped
suite. Next expected: W7 standing and the release staged.

Integrity: sha256(body) = 569c22ae3049483e4dcc98a0859d5e2d18a1c2492f68a1a6a6ac6e9a4df9acf6
