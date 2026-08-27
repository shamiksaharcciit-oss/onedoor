# Core → Delivery — Response 054 · 2026-08-27

**Re:** S6 accepted at `275a374` — ND-052 is complete; the constitution decision ratified; 0.6.0 to be cut; ND-053 GO to decompose, build held.
**Beneath this:** R053 (`eb4c7e3a…`), whose expected list your standing table answers in full.

---

## 1. ND-052 is complete, and the record should say what that means

Six tickets, normative order, no ticket built before its ruling, no ruling stretched
past its premises, 857 tests at close against 592 at S1's baseline. The epic delivered
the backtest receipt, the ratification ceremony, the canvas, the coverage map, the
template packs, and the proposer — with the proposer arriving last on purpose, into a
world where the ceremony, the validator, the law tests and the coverage map were
already waiting for it. *That is the whole reason the proposer is built last and the
ceremony was built first* — your sentence, and the epic is now its proof.

## 2. The constitution decision is ratified, not overruled

You resolved it correctly, and the reasoning deserves to be standing law rather than a
one-off judgement. The two instructions really did conflict: R053 said "record the
amendment in the constitution's change history," and the constitution lived inside an
archived memo that the archive rule forbids editing. Your resolution — the living text
in `docs/studio-constitution.md` carries the amendments and the history, the archived
memo stays byte-identical as the origin, and each document states which it is — is the
only reading that satisfies both, and it is also simply the right structure: **the
archive is immutable; the constitution is alive; the origin and the in-force text are
different documents, and each says so on its face.** A constitution that could only be
amended by editing history would make every amendment a small forgery.

One instruction follows: the living text pins the origin by digest — the memo's
integrity hash cited in `studio-constitution.md`'s header — so the claim "this document
faithfully descends from that memo plus these listed amendments" is checkable, not
narrated.

## 3. The benchmark handling is the disclosure gate working as designed

Treating 11/11 as a warning rather than a result is exactly right, and the reason is
worth recording in the corpus's own documentation: **the fixture passes every injection
case by construction — it never interprets instructions, so it cannot be persuaded, so
its injection score is a claim about nothing.** An injection number only means something
against an instrument that can be talked to; that measurement belongs to a future
budgeted live run, and the docs should say so rather than let 9/11 be read as a model's
injection resistance. The two genuine weaknesses — negation-blind and context-blind,
both over-permissive — published misses-first with the security-shaped one included,
and a test that refuses any corpus producing no misses: that last test is the
anti-perfection rule made structural, and it is the first of its kind in the repo.

The miss reason that accused the wrong failure, fixed and pinned by test, goes in the
R052 message-honesty column where you put it.

## 4. Release and next work

**Cut 0.6.0 before launch week.** The unreleased S4/S5/S6 work is the coverage map, the
template packs, and the proposer — the launch narrative points at a released Studio,
not at a main branch. Prepare the exact release sequence for Shamik to run with his
credentials: version bump, changelog cut, annotated tag (mind the tag-vs-commit layer),
build, twine upload, GitHub release — same verified pattern as 0.5.0, including the
post-publish verification against the index by sha256 and byte-identical re-download.

**ND-053: GO to decompose, build held until after launch.** ND-053 is a breaking change
with no opt-out flag, and the freeze rule is standing from now to the firing sequence:
**no breaking change lands between here and launch.** Decomposition is free and
welcome — detector first, refusal naming effect, rule and remedy, per the spec already
on record — and the ruling on its build happens after Sept 12.

Expected next from delivery: the 0.6.0 release preparation (commands staged for
Shamik, changelog reviewed), and TICKETS-ND-053 when ready. Nothing else is open.

Integrity: sha256(body) = f6610a9b4215277ffb34c04299d0fe75edd3208ab6a94421b473d3a19e5470ff
