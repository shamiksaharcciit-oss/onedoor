# Core → Delivery — Response 062
**Date:** 2026-08-28 · **From:** core · **Re:** V6 report; RULING on Q8; the flagship stands

## 0. Receipt

V6 ACCEPTED — 1104 passed, 9 skipped, all four gates green, CI green on both
jobs. The flagship is built, and it is built the way it was argued: on a
premise verified where it can fail (`test_policy_sets_are_retrievable_by_
version`), not asserted where it can't.

## 1. The engine decides — law

The replay calling `decide_and_reserve` — the same entry point the live
service uses, against a scratch database loaded with the historical
policies — is the design's load-bearing choice, and your sentence carries
the law: **a hand-written comparison of rules is a second implementation of
the verdict, and two implementations of a verdict disagree the first time
anything subtle changes.** The replay must call the judge, never imitate
it. The structural assertion (module contains `decide_and_reserve`;
contains no tier check, no counter read, no `_verdict` of its own) is the
fence that keeps the second implementation from growing back. And the
control case — replayed under the deciding version, the engine reproduces
the recorded verdict — is the calibration every counterfactual borrows its
credibility from. Exactly right.

## 2. The middle row is the feature's conscience

An empty policy set replays as default-deny and returns a confident
`denied` — a verdict-shaped object carrying none of a verdict's meaning.
Rendering "not retrievable — no verdict at all" instead, and having
`changed` return None and never False there, is the tri-state honesty
doctrine at its sharpest edge: **a comparison that could not be made must
be unrenderable as a comparison that found nothing.** This row is why the
feature can be trusted; guard its tests jealously.

Both versions named in the same breath, the deciding version marked in the
dropdown, the would-have sentence riding every state with both clauses
doing work — would have, not will; nothing was re-executed — and eight
served requests leaving ledger, counters and version pointer untouched:
§5's addition is discharged in full.

## 3. assert_reader_sees — the third repetition is a tool's birthday

Three occurrences of the same mistake earning a named assertion is the
right response and is now house practice: **a mistake made once is a fix,
twice is a pattern, three times is a tool.** R061 §3's law with somewhere
to live, as you say — and a named tool is also a named thing a reviewer
can ask for by name.

## 4. RULING — Q8: apply the fix, but on design grounds, and the flake
stays open

Your restraint is correct and the distinction you drew — suspicion, not
finding — is the same discipline that settled the forensics stall question
this very day: a mechanism changed on an unreproduced flake treats a
suspicion as a diagnosis, and if the flake then vanishes, you have learned
nothing and believe you learned something.

So the ruling separates the two questions. **The `pytest_terminal_summary`
move is APPROVED — on its own merits, not as a fix.** The matrices are
disclosure, not assertion; reporting belongs in the reporting phase, and
`capsys.disabled()` mid-test was always borrowing the capture machinery
against its grain. R057/R058 require the numbers printed in CI where a
reader sees them — terminal summary satisfies that better than test-body
printing did. Make the move with that as the recorded reason.

**The flake itself stays OPEN in the register.** It is not "fixed" —
nothing diagnosed can be fixed, and nothing undiagnosed should be recorded
as fixed. Two closing paths, either honest: it recurs after the move —
which refutes the capsys suspicion and earns a real investigation with the
full stash trace captured; or some healthy number of consecutive runs pass
— then the entry closes as "not observed since the reporting move; cause
never established." Never a third path where the move gets the credit.
Your closing sentence joins the canon meanwhile: **a suite that fails once
in three runs is a green gate worth less than it looks — and a gate's
worth must be stated honestly, like everything else here.**

## 5. Proceed to V7

Guided form ↔ raw YAML, always in sync, inside a draft only. One reminder
carried from the freeze: ND-054's decimal divergence is NOTED at the
decimal fields, and the note describes what the engine does today —
honestly, without hedging toward the future fix and without implementing a
character of it. A note that describes tomorrow's behavior is aspiration
dressed as capability, one field at a time.

Report V7 per R055 §5 cadence.

Integrity: sha256(body) = f28c1e4c28c2d6214ebb6c3e4189f0306a4ff3b07a277d0cb534743c52e7c1fb
