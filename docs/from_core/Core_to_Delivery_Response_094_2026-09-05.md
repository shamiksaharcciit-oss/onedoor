# Core → Delivery (onedoor) — Response 094

**Date:** 2026-09-05
**Re:** F-R1 — the tag preceded the release cut; the cut, packaged; the release ritual
**Verdict:** BUILD NOTHING FROM `9a7bc65`. One release-cut commit is authorized below.
The tag question is the operator's call (§3) and is framed there, not decided here.

---

## 1 · F-R1 — what the vet found

Core vetted the release notes before the wheel build and found the tree under `v0.7.0`
is not cut:

- `pyproject.toml` still says `version = "0.6.2"`. A wheel built from the tag would be
  `onedoor-0.6.2-…`, which PyPI already holds. The tag names a release whose own
  metadata disagrees with it.
- `CHANGELOG.md` still opens `## Unreleased` under the "DRAFT for 0.7.0" banner; its
  last commit (`f3cbb76`) predates the entire dogfooding arc. **None of R086 → R092's
  fixes has a changelog entry** — the banner fix, the inbound rules link, upload
  refusals rendered, the store warning, the preview-refusal boundary and its fifth
  site, both bounds in the guided pane, `not recorded`/`unchained`, the download
  routes, the forecast notice on both branches, the empty-params sentence, three script
  rewrites.
- `docs/release-0.7.0/` holds the two pre-arc drafts; neither describes the release as
  shipped.

Nothing here is a product defect and nothing here is the agent's error alone: the tag
was cut by the operator on core's instruction, and core's instruction named the manual
commit as the last step without naming the cut. **Direction of cut: core.** The law it
earns is old and was already in the register — *a release ritual is a checklist, and a
checklist skipped from memory is a checklist skipped*; core wrote "add, commit, tag,
push" from memory. Caught before any artifact was built, which is the only reason it
costs a commit and not a yanked release.

## 2 · The release-cut commit — ONE commit, authorized

1. `pyproject.toml`: `version = "0.7.0"`.
2. `CHANGELOG.md`: `## Unreleased` → `## 0.7.0 — 2026-09-05`; drop the DRAFT banner;
   **add entries for the dogfooding-arc fixes**, in the changelog's own voice and
   sectioning (Fixed / Added / Changed), one entry per fix as the agent knows them —
   R086 (four Studio fixes, the doc correction, the script rewrite), R088–R090 (the
   preview boundary + `candidate_invalid_at_load`, F-E1, F-H1, F-V1 download routes,
   F-S1/2/3 + the Windows lock guard), R092 (F-D1, F-D2, G2 correction). R011 holds:
   the release notes are a slice of this section, so the section must contain what the
   notes say.
3. `docs/release-0.7.0/RELEASE_NOTES_v0.7.0.md` — **core-written, sealed, attached to
   this memo** (`318d24cdf1a80d0a8db062011a44269398db4cfb6e0dbbdd0807980fad87dedb`;
   supersedes draft B `c405e827…` carrying the prior digest in its header). Commit it
   as delivered; delete DRAFT-A (T3 slipped; a counterfactual is not history) and
   DRAFT-B (superseded in place). Verify with `scripts.verify_memo` before commit.
4. Gates green. Commit message states the footer digest of the notes **pasted from
   `verify_memo`'s output** (R093 §2).

Nothing else changes. No code.

## 3 · The tag — the operator's call, framed honestly

`v0.7.0` is already on GitHub, pointing at `9a7bc65`. Two honest options:

**(a) Re-point the tag to the cut commit, now, and record the move.** A pushed tag is
a public reference; moving it is a rewrite. Mitigation: it is under two hours old, no
release object, no wheel, no PyPI upload, no downstream consumer exists, and the move
is recorded in the CHANGELOG entry itself ("`v0.7.0` was first pushed at `9a7bc65`
with `pyproject` still at 0.6.2 and re-pointed to `<cut>` before any artifact was
built"). Core's recommendation, because the alternative leaves a permanent false
statement in the repository — a tag named 0.7.0 on a tree that declares 0.6.2.

**(b) Leave `v0.7.0` where it is and cut `v0.7.1` immediately** as the first
publishable version. Honest, no rewrite, but it burns a version number on a metadata
fix and makes the first PyPI release of the Studio 0.7.1, with a changelog entry
explaining why 0.7.0 was never built. Defensible; costlier to explain forever.

Core recommends (a). The operator holds the repo and decides. Either way the record
carries the reason.

## 4 · The release ritual, in order — after the cut lands

1. Operator: tag per §3; push.
2. Operator: `python -m build`; record `sha256` of wheel and sdist from `dist/`.
3. Operator: `scripts/release_smoke.py` in a clean venv against the built wheel.
4. Operator: PyPI upload (credentials are the operator's; core never sees them).
5. Operator: GitHub Release `v0.7.0` with the sealed notes as the body and both
   artifacts attached.
6. Agent: the release ping — four-source digest verification (`dist/`, GitHub Release
   assets, PyPI-served wheel, the operator's local build), byte-identical or the ping
   says which one differs. Nothing is announced until the ping is green.

The essays that publish next week pin `onedoor==0.6.2` by digest and are unaffected
by any of this; 0.7.0 on PyPI is the product track, not the campaign.

Integrity: sha256(body) = c435f49335e9f1917d94c4272c5a49a3cd314003b8552c4ac483ddfd33a548fa
