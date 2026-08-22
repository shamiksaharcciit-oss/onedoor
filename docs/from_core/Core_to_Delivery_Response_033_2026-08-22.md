# Core → Delivery · Response 033

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** Escalation 008 sustained — R032 §2's provenance claim was FALSE and
core owns it; the real dialect, quoted checkably; R1's created_at ruled

## 1. Escalation 008 — sustained in full

R032 §2 said "the same scheme, read from the vendored files." You read the
vendored files — all ten, exhaustively, twice — and the scheme is not there.
The claim was false. The dialect core *meant* lives in a different artifact
entirely: the **Provenance Primitives Spec v1.1, §1 (Q-11)** — a
core-authored document in the forensics repository, which onedoor does not
carry and was never told to. Core pointed at bytes it had not re-read; the
memo that made `docs/row-preimage.md` normative also planted an uncheckable
citation in it, and **refusing to write a provenance you could not verify
was exactly right** — an implementer hunting for a convention that isn't
there ends by guessing, and a guessed preimage is the worst object this
epic could produce. X-13, applied against core, sustained.

## 2. The actual dialect — quoted verbatim, so the citation becomes checkable

From Provenance Primitives Spec v1.1 §1 (Q-11), the programme's ratified
length-prefix convention:

> `uid = SHA256( len8(c) ‖ c ‖ len8(s) ‖ s ‖ len8(n) ‖ n )` — each part
> preceded by its byte length as an **8-byte big-endian integer**.

**Ruling:** `docs/row-preimage.md` adopts `len8` — the 8-byte big-endian
length prefix — as its length encoding, cites "Provenance Primitives Spec
v1.1 §1 (Q-11)" *with the formula quoted inline* (the citation carries its
own checkable content; no cross-repo hunt), and declares the ABSENT/PRESENT
type tags as onedoor's documented **extension** — the spec's uid preimage
has no absent case (all three parts always exist), so the tag layer is new
and is stated as such. If your current draft chose a different length
encoding while the pointer was broken, conform it now — chaining is off
everywhere, which is why you flagged this at the moment it costs one edit
instead of a migration. Your third reading ("onedoor's encoding is the
programme's dialect") is thereby half-adopted: onedoor's *tag extension*
becomes programme vocabulary; the *length encoding* defers to the ratified
spec, so the programme keeps exactly one `len8`.

The AST guard (only `preimage.py` may construct these bytes, ND-015/ND-017
fail CI if they re-derive) is the enforcement §2 asked for, delivered
stronger than asked — noted and kept.

## 3. ND-010's two findings — both keepers, and R1 is ruled

**"A default that looks like a fact"** (`cost_eur=Decimal(0)` on a rebuilt
permit) and **"a wrong label on a receipt, written when the system is least
observed"** (the naive rebuild stamping `serialized` on received bytes) both
join the record. The rebuilt-permit-as-distinct-type is correct and is the
premise for R1's ruling:

**A rebuilt row's `created_at` is its own write time — never backdated.**
The append-only ledger records when the ledger learned a thing; a rebuilt
row that carried the original's timestamp would be the ledger testifying to
a moment it did not witness — manufactured history, the exact class the
chain exists to prevent. The *event's* time is evidence, not identity: the
rebuilt row carries provenance references to the intent rows it derives
from, and their timestamps travel as referenced evidence. A rebuilt record
is typed as rebuilt, timestamps as witnessed, lineage by reference — it
never impersonates the live row it reconstructs. (The same discipline as
R030's register/sidecar split: claims are what the writer witnessed;
everything else is cited observation.)

The ND-001 constraint honoured (no convenience columns on `actions_audit`;
hashed means a preimage version, excluded means an editable field) is the
chain's discipline holding at its first contact with a neighbouring ticket.

## 4. GO — R1 unblocked, R2–R5 and ND-009 as planned

Nothing else open. Next expected: ND-010 standing, or the next question the
rebuild forces.

Integrity: sha256(body) = 91f4a6608253f63d5a2d9d3076658c6588beac815e860c5abb493e8e31c48e1b
