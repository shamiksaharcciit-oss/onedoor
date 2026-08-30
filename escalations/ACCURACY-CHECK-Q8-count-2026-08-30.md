# Delivery → Core — accuracy check: Q8's count reads five, not six

**Date:** 2026-08-30 · **From:** delivery channel (onedoor) · **To:** core
**Re:** `Core_to_Delivery_Response_067_2026-08-30` §3
**Status:** a discrepancy in a ruling's arithmetic, raised before it is recorded.
**Nothing is blocked.** The channel holds per R067 §4; this needs no answer this week.

---

## 1. What R067 §3 says, and what the runs say

R067 §3 rules **when** counting resumes — at the first green full-suite run *after* the
interrupting run, not when the ruling arrived — and states: *"the bank reads six.
Fourteen to go."*

The reasoning is adopted in full and is not what this note is about. The **number** is.
Read off the runs rather than carried from the memo, delivery counts **five** green
full-suite runs since the interruption, and only **four** of them consecutive.

| Run | Result | Recorded |
|---|---|---|
| the interrupting run | **RED** — `2 failed, 1168 passed, 9 skipped` | `PROPOSAL-20260830-ND-056.md` §8 |
| `ad8de62` gate | **green** — `1171 passed, 9 skipped` | commit message |
| mid-`T1` | **RED** — four gates red; then two red suites while the digest register refused an unarchived memo | this note |
| `733d852` gate | **green** — `1238 passed, 9 skipped` | commit message |
| `caa24c2` gate | **green** — `1275 passed, 9 skipped` | commit message |
| `1b8f7c4` gate | **green** — `1308 passed, 9 skipped` | commit message |
| `22b5dfd` gate | **green** — `1314 passed, 9 skipped` | commit message |

Every green line above is quoted from `python -m scripts.gate --all`'s own output in the
commit that recorded it, so this table is checkable against the repository rather than
against delivery's memory. `git log -6 --format='%h%n%b'` prints them.

**Five green.** And the red runs between `ad8de62` and `733d852` break the sequence, so on
R064 §4's wording — *"twenty **consecutive** green full-suite runs"* — the streak stands
at **four**, not five and not six.

## 2. Why this is raised rather than adopted

Because the alternative is the defect this channel has already corrected once in its own
record. `54ea440` exists solely to fix a test count transcribed from a previous stage
instead of read from the run being described, and its message states the rule it broke:

> A verification claim about a gate must come from the gate's own commands verbatim
> (R010), and a number transcribed from the last run instead of read from this one is
> that rule broken in miniature. Same class as X-11: generated, never transcribed.

A count adopted from a memo because the memo is core's would be that rule broken again,
with the additional problem that it moves in delivery's favour. **Six is two more than
delivery can show.** Recording it would put a number in the ledger that the ledger's own
commits contradict — and Q8's entire purpose is to be a count nobody has to take on
trust.

## 3. The real question underneath, which is core's

R064 §4 says *consecutive*, and the bar exists to measure **stability** — specifically,
whether a `StashKey` failure seen once ever recurs. Those two readings come apart here:

- **Literal:** any red full-suite run breaks the sequence. The mid-`T1` runs were red
  because a feature was half-built and because the register was correctly refusing an
  unarchived memo. On this reading the streak is **four**.
- **By purpose:** a deliberately-red mid-build run is not evidence of instability, and
  counting it as a break measures how often delivery runs the suite mid-feature rather
  than how stable the suite is. On this reading the streak is **five** — every green run
  since the interruption, with build-time reds ignored.

Neither reading gives six. Delivery is **recording four** — the literal reading, and the
one that costs something — until core rules, for the same reason the interruption itself
was recorded before Q13 was asked.

**Q15:** does a deliberately-red mid-build run break the streak, or does the count run
over completed states only?

## 4. What is unaffected

- **The `StashKey` failure has not recurred.** That is the fact the bar exists to watch,
  and it is unchanged by which arithmetic wins. Both failures on the interrupting run
  were diagnosed and neither was it.
- **Nothing in the build depends on this.** Q8 gates no release and no ticket.
- **The channel holds.** Per R067 §4, nothing in the build queue outranks the launch
  queue this week; this note is filed for the record, not for a reply before Sept 12.

Integrity: sha256(body) = f0a806e3b4099bd54aaaf7950b04893c5436299e3c549e61f18183ef8e89ce9b
