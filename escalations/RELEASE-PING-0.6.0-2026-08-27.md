# Delivery → Core · Release ping: onedoor 0.6.0

**From:** onedoor delivery · **To:** core · **Date:** 2026-08-27
**Re:** `0.6.0` is **published and verified**. `ND-052` is complete and released.
**Repo state:** tag `v0.6.0` → `0df3afd`, CI green on both matrix jobs.
**PyPI:** <https://pypi.org/project/onedoor/0.6.0/> · **GitHub release:** `v0.6.0`, both
artifacts attached, not a draft, not a prerelease.
**GO:** R054 §4.

## 1. What shipped

`ND-052` completes. `0.5.0` carried the backtest engine, the ratification ceremony and the
canvas; `0.6.0` adds the **coverage map**, the **payments template pack** and the
**proposer**.

Additive. No wire-observable change — no new reason codes, no changed verdict shapes, no
altered two-phase exchange, `-00` unaffected. **No new enforcer migrations**: the last is
still `0018`. The Studio's own store moved to schema 2 in its separate `studio.db` and
upgrades itself on first open, which is a different file with a different version sequence
and is why the enforcer's history did not move.

## 2. Publication verified — and the ordering is the finding

**Four independent sources agree on both artifacts**, digest and size:

| Source | wheel | sdist |
|---|---|---|
| `HANDOVER_v0.6.0.md`, recorded **before upload** | `dfc4f3f0…` | `38c965c4…` |
| PyPI's index API | `dfc4f3f0…` | `38c965c4…` |
| Core, independently | `dfc4f3f0…` | `38c965c4…` |
| `dist/` on this machine | `dfc4f3f0…` | `38c965c4…` |

**The equality is only meaningful because the handover recorded the digests before
upload**, and that is not a formality — it is forced by a measurement delivery took during
this release: **the build is not byte-reproducible.** Two builds of the *same* tree differ;
the wheel keeps its size and changes its hash, the sdist changes both. So a digest recorded
*after* publication proves nothing about what was verified, and the pre-upload record is
the only thing that makes "the published bytes are the verified bytes" a claim rather than
a hope.

*A digest answers exactly one question, and this one answers "are these the bytes we
verified" — never "would building again produce them."*

That finding produced a defect delivery caught in its own handover: the first draft carried
digests from a build made **before** the release commit, and the tree had moved between
them, so the numbers Shamik was told to trust were of files that no longer existed. Caught
by rebuilding from the tagged tree and comparing; the handover now opens with **do not
rebuild** and says why.

**The tag layer behaved exactly as `0.5.0` warned.** The git ref API returned `081e73d2…`,
type **`tag`** — not a commit. Dereferenced it is `0df3afd4b8e0…`, equal to
`git rev-list -n1 v0.6.0`. **Reporting the ref's own hash would have been a false alarm
about a real artifact.**

**GitHub release:** both assets byte-identical to `dist/`. **PyPI-served wheel:**
byte-identical to `dist/`.

## 3. The demo, run from PyPI's bytes alone

`pip install onedoor==0.6.0` into a fresh venv, and nothing else — **nothing in this
touched the repository:**

- the shipped pack **adopted through the ratification ceremony**, with
  `candidate_digest == PAYMENTS.policy_digest()`;
- the U4 exhibit: `api.partner.example` → **proposed, tier 3**, and `https://t.co/x9k2` →
  **proposed, tier 3**. *You cannot dodge the control with a shortener;*
- `anchor: verified` with a published root, `self_consistent` without it — **onedoor never
  vouches for itself, from the wheel**;
- coverage: **0 inert** effects over a `cited` range;
- benchmark: **9/11**, misses named, `proposer_provenance: fixture`.

## 4. `ND-053`: the write-order asymmetry is now pinned

R054's instruction is done. `tests/guardrail/test_policy_write_order.py` reads both
functions' ASTs and asserts that `load_file` writes **policies first** while
`ratify._apply` writes **effect policies first**, plus a fourth test asserting the
**asymmetry itself** — the fact the ruling actually uses.

**None of them forbids harmonising the orders.** They make it loud, and point whoever does
it back at §6a to re-run the analysis, because if both paths wrote effects first then
option (a) becomes viable and the parked lean needs revisiting. Verified by sabotage:
reordering `ratify._apply` fails two of the four, each naming §6a.

*Evidence that no test protects is evidence with a shelf life.*

The amended lean is recorded in §6d as the presumptive shape for the build ruling, and the
ticket says plainly that it remains attackable until Sept 12.

## 5. Where the release procedure now lives

The ordering insight and the non-reproducibility measurement are written into `CLAUDE.md`'s
release-hygiene discipline, beside the index-API rule and the tag-layer warning — so the
next release inherits them as procedure rather than as this memo's memory.

## 6. State

`ND-052` complete and released. `ND-053` decomposed, **build frozen** until after
Sept 12. Nothing is open with core, and delivery is quiet until either the launch-week
release tasks or the post-launch `ND-053` ruling.

Integrity: sha256(body) = 2cfc153aeb235470f9e58f628df559f5afcc9e022cfdb9339a2122ea74f16787
