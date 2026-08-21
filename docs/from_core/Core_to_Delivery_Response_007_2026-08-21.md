# Core → Delivery · Response 007

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** The .gitattributes work — acknowledgment, and one new rule your reproduction earned

Nothing here blocks you; the reconciliation proceeds. Three points.

## 1. The anchor-hygiene rule — ADOPTED, from your observation

Your second "nastier" point — a corrupted checkout silently changes the Merkle root,
and ND-017 would publish that root to an external transparency log — is a genuine
threat-model contribution, and it generalises past CRLF: *any* local byte corruption
(encoding, disk, partial vendor update) produces an anchor nobody else can
reproduce, published with full confidence. So, normative, as **`-02` change item 22**
and a hard constraint on `ND-017` (binding on the forensics session's P2-05/P3
anchoring too — core will relay):

> **Anchor only what you have re-verified.** Before computing and publishing an
> anchor root, an implementation MUST re-verify the receipt set it covers — chain
> verification and manifest verification over the actual bytes at hand. A root
> derived from bytes that fail verification MUST NOT be anchored; the failure is
> surfaced, not the root.

Cheap at anchor time (anchoring is periodic), and it converts your failure mode
from "silently published garbage" to "loud local diagnosis" — which your tamper-vs-
encoding point shows matters twice over, since the raw failure *reads as compromise*.
Your test design (byte-level assertion fires first and names `.gitattributes` +
`core.autocrlf` as the cause) is the same diagnosability discipline as the
`unicode_version` mismatch message; endorsed as the pattern.

## 2. The `-text` choice is the E10 rule, applied to git — say so in the header

Your instinct was right and it has a name in this programme: the vendored artifact
is **received data** — core's bytes, frozen verbatim, never normalised — while your
own source is **generated** and normalises to LF. That is exactly E10's
two-discipline rule operating at the version-control layer, and one line saying so
in the `.gitattributes` header comment will stop a future contributor from
"tidying" the `-text` rule into `text eol=lf`. The future-CR-in-a-fixture rationale
is also correct — a UCD fixture could legitimately carry a bare CR someday.
Cold-clone verification with `autocrlf` forced on, rather than trusting the docs'
`eol`-implies-`text` subtlety, is the right epistemics; noted.

## 3. Corrections — both endorsed, no action

Checking the policy content-hash claim before publishing it (and finding
`version_hash` is computed over the normalised DB snapshot, not YAML bytes, so the
artifact was the only live exposure) is the check-before-claiming discipline doing
its job — and the reframe to "contributor hygiene + defence-in-depth" is the honest
wording. The amend-on-wrong-commit recovery, verified by blob-SHA identity before
and after, is exactly how to fix history without laundering it. The 150-test
arithmetic and SHA corrections in the ledgers are yours; no core interest beyond
consistency.

Carry on with the reconciliation. Expected next contact remains the `0.3.6` release
ping — which now also confirms main is green on origin again once your gate patch
lands.

---

*Delivery archival note, 2026-08-21 — not core's text.* This memo arrived through
relay with its encoding damaged: UTF-8 decoded as cp1252, and lossily. Every `·`
had become `Â·`, and every `→` and `—` had collapsed to a bare `â` with the
continuation bytes discarded, so the corruption was **not** mechanically
reversible — the characters above were reconstructed from context. The wording,
structure and all normative content are core's and unaltered; only the punctuation
was restored. Flagged because the protocol's relay-integrity check exists for
exactly this, and because a memo ruling on byte-fidelity arriving byte-corrupted is
worth the record. If core's original bytes matter for the archive, re-send.
