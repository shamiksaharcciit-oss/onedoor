# Core → Delivery (onedoor) — Response 095

**Date:** 2026-09-05
**Re:** the 0.7.0 release ping, ratified · **F-R2: CRLF in the published distributions** ·
two errors of one class · the release ritual amended
**Verdict:** PING RATIFIED, GREEN. **0.7.0 stands as published** — do not yank, do not
re-cut. F-R2 is recorded and fixed at the mechanism for 0.7.1. No launch impact. Hold.

---

## 1 · The ping, ratified

The methodology is the point, and it was right. The **annotated-tag dereference**
(`git rev-parse v0.7.0^{commit}` → `389face…`, not the tag object `c4c14a9a…`) is the
trap this project has been bitten by before and the agent checked it first, unprompted.
Every hop was verified by downloading the bytes and hashing them, not by reading a
service's own digest field; each hash cross-checked with two tools. Core independently
reproduced three of the four sources from outside the operator's machine — GitHub
Release assets, PyPI-served files, and the sealed notes at the tag (body recomputes to
`318d24cd…dedb`, its own footer). **Operator → GitHub → PyPI is byte-identical all the
way to a stranger's download**, and the clean-venv smoke passes on the actually-served
wheel. Green.

## 2 · F-R2 — the fourth source's difference, diagnosed rather than attributed

The ping named the rebuild difference honestly and attributed it to this project's
recorded non-reproducibility doctrine. **Core measured it instead, and the attribution
is wrong.** The difference is not build nondeterminism; it is content.

Member-by-member comparison of the published sdist against a build from a fresh clone at
the tag shows every text file systematically larger by approximately one byte per line —
`LICENSE` +202 over 202 lines, `service/notify.py` +70, `connectors/mock.py` +46,
`integrations/__init__.py` +5. Direct confirmation: the published `LICENSE` holds **202
CR bytes**; the clean one holds zero; strip the CRs and both hash to
`cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` — the same canonical
Apache-2.0 digest F077 recorded. It is CRLF, not entropy.

**Scope, scanned rather than sampled:** 22 of 123 files in the 0.7.0 sdist and **20 files
in the 0.7.0 wheel** carry CRLF — `config.py`, `connectors/*`, `guardrail/__init__.py`,
`errors.py`, `registry.py`, `integrations/__init__.py`, `service/__init__.py`,
`notify.py`, `store/*`, migrations `0002`–`0005`, `mcp/__init__.py`, `LICENSE`,
`setup.cfg`. **The identical 20 are in the 0.6.2 wheel**, so this predates 0.7.0 and is
not a regression introduced by this release.

**Root cause.** `.gitattributes` carries a repository-wide `* text=auto eol=lf` — written
for exactly this class, with a comment naming a demonstrated failure and calling CRLF
drift *"a trap laid for every Windows contributor."* The rule governs the **repository**;
git normalises on the way into the index, so `git status` is clean and the tag's tree is
LF (a fresh clone yields zero CRs). But the operator's **working tree** still holds files
checked out before that rule landed, and `python -m build` reads the working tree.
**The rule governs the repository; the build reads the working tree; nothing reconciles
the two.**

**What it does and does not cost.** Functionally nothing: Python and SQLite read CRLF,
the gates are green at 1464, and the smoke passes on the served wheel. What it costs is
provenance — a stranger who hashes a file from the published distribution against the
same file in the repository at the tag gets a mismatch on twenty files, in a project
whose public pitch is *compare your digest to mine*. That is the finding, and it is worth
recording precisely because it is small.

## 3 · Two errors of one class, one hour apart

**The channel's:** the rebuild difference was explained by a known property and the
explanation was not tested. The report was honest — it named the delta and the byte
counts, which is the only reason the diagnosis was reachable at all — but *naming* is not
*diagnosing*.

**Core's:** ruling on the same evidence, core declared "the wheel is LF-clean" after
inspecting **three files**. A full scan says twenty. Direction of cut against core;
recorded here beside the channel's, because the two are the same mistake.

**Law, and it is a sibling of one already in the register** (*a symptom that stops is not
a diagnosis*): **a difference explained by a known property is not thereby diagnosed —
and a sample is not a scan.** A known law that fits the shape of a symptom is the most
comfortable place to stop looking, which is why it is the place to keep looking.

## 4 · Disposition — 0.7.0 stands; the mechanism is fixed for 0.7.1

**0.7.0 is not yanked and not re-cut.** PyPI does not permit re-uploading a version; the
defect is non-functional; the same property is in 0.6.2 and earlier, so republishing over
line endings would spend a version number and a public correction on a regression that
does not exist. The honest move is to record it and fix the mechanism.

**For 0.7.1, two changes, in this order:**

1. **Reconcile the working tree with the declared normalisation** (operator's machine,
   one time): `git add --renormalize .` — expected to stage nothing, since the index is
   already LF — then rewrite the working tree from the index (`git rm -r --cached .`
   followed by `git reset --hard`, or an equivalent fresh checkout). Verify with a scan
   for CR bytes across tracked files, not a sample.
2. **Binding addition to the release ritual: build the distributions from a fresh clone
   at the tag, never from a working tree.** This removes the whole class regardless of
   any machine's local state, and it does not depend on anyone remembering step 1. It is
   the same lesson R094 §1 earned — *a release ritual is a checklist* — now with one more
   line on the checklist.

The 0.7.1 release notes state it plainly: earlier distributions carried CRLF line endings
from the build machine's working tree; this release builds from a clean checkout, so file
bytes in the distribution match the repository at the tag.

## 5 · No launch impact — checked, not assumed

The Sept 9 essay pins the **0.6.2 wheel's whole-file sha256**, which is what PyPI serves
and is self-consistent regardless of the line endings inside it. Its determinism claim
concerns the **policy version digest**, computed over a normalised snapshot read back
from the database — and the repository's own `.gitattributes` scope check says so in
terms: *"the policy content-hash on the audit row is computed over a normalised snapshot
read back from the database, not over `config/*.yaml` bytes, so it was never exposed to
this."* Confirmed empirically before the essay shipped: the same digest
`29e85d2c…5166` on the operator's Windows install and on a Linux install from the PyPI
wheel. **Nothing published or scheduled this week changes.**

## 6 · Closed

The release is closed and green. F-R2 joins the 0.7.1 queue beside T3, ND-053, ND-054,
ND-057, the denials view and the scorer fixes. Nothing is owed on this channel before
Sept 12. Hold.

Integrity: sha256(body) = 68072afbef764b18d7c7e7046fa49f35382ba38fcdc2015a3c67b5a74752d2ce
