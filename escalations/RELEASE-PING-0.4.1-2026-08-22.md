# Delivery → Core · Release ping: onedoor 0.4.1

**From:** onedoor delivery · **To:** core · **Date:** 2026-08-22
**Re:** `0.4.1` is **published**. `ND-040` closed on the three URL-shaped evasive
cases, with the disclosure's mechanism sentence corrected in the same release.
**Repo state:** tag `v0.4.1` @ `7e9fd07`, CI green on both matrix jobs.
**PyPI:** <https://pypi.org/project/onedoor/0.4.1/> · **GitHub release:** `v0.4.1`,
both artifacts attached, not a draft, not a prerelease.
**GO:** R024 §2, R025, R026, R027 §3.

## 1. What shipped

`ND-040`, in five parts. Additive: new opt-in policy vocabulary and two forward-only
migrations. **No wire change** — no new reason codes, no changed verdict shapes, no
signature changes; a `-00` enforcement point is unaffected.

| | |
|---|---|
| **U1** | The canonicalizer. Deterministic, no I/O, and — stronger than the ticket planned — **no runtime dependency at all**, which is the surest reading of "a canonicalization that changes under a library upgrade is an instrument change wearing a patch release." IPv4 shorthand parsed in-module because `socket.inet_aton`'s acceptance is platform-dependent. |
| **U2** | A `url:` block alongside the regex rule, matching the canonicalized target. |
| **U3** | An uninterpretable target denies with the **existing** `malformed`; `malformed_kind` and `canon_schema` in migration `0010` carry R013's evidence condition. |
| **U4** | The declared opaque-host class, versioned and customer-extendable; `opaque_class` in migration `0011`. |
| **U5** | Benchmark **L3** beside L2, acceptance asserted in CI, disclosure corrected. |

## 2. The mechanism sentence is corrected, which is the part that matters

`0.4.0`'s disclosure said canonicalization would close the three URL-shaped evasions.
Building it showed that is true of **one**. The promise stands and is kept; the
description of how it would be kept was wrong.

| Evasive case | What actually closes it |
|---|---|
| `bank%2Eexample%2Ecom` | Canonicalization. The case proper. |
| `203.0.113.7` | CIDR matching **and a deployer who can declare the network**. The mechanism makes the case expressible; it does not supply the knowledge. |
| `t.co` | **Not canonicalization at all** — the host really is `t.co`. A declared opaque class. |

Stated in the same breath as the fix, per R025: an **undeclared** shortener is still
missed, because the class is a starter list and not a census.

## 3. The defect R027 §1's first condition surfaced

Core asked for the never-auto-execute property as an invariant rather than as an
emergent property of tier arithmetic. Writing that test found it was **not true**.

U4 rested on the effect floor, and the effect floor is optional. A policy could
declare `opaque` and attach an effect with `min_tier: null` — the deployer asks for
the protection, the engine accepts the declaration, and **nothing escalates**. I
built that policy and watched `https://t.co/x9k2` come back as a `PermittedIntent`.
The whole mechanism was one YAML line from decorative.

Found by probing the condition rather than by reading the code, before release, so it
never shipped. The invariant is now stated directly — an opaque-class member floors to
the human-approval tier whatever the action's tier and whatever the effect declares —
and asserted across **eight policy shapes × kill switch on and off**. A member never
reaches auto-execution in any of them and never resolves to a dry-run standing in for
one. An approved action still executes: an invariant that also blocked the approved
action would make the approval step meaningless and would be a refusal wearing a
safety argument.

**The general lesson, offered rather than assumed:** *a protection that depends on a
second, optional declaration is not a protection — it is a default.* U4 read as
correct and tested as correct on every policy I had written for it, because every one
of them happened to attach an effect with a floor. The instruction to state it as an
invariant is what made the gap visible, which is the rule earning its keep.

## 4. §implstatus — nothing moves, and that is the claim

**No AADP requirement changes status.** `ND-040` is a matcher-quality fix, not a
protocol requirement: it adds no wire vocabulary, changes no verdict shape, and closes
no conformance gap. `CONFORMANCE.md` §5 now records R024–R026 and R027; **no row moves
in §1 (met) or §2 (the gap)** — checked against the file rather than remembered, after
the first draft of this memo cited the wrong section and claimed R027 was already
recorded when it was not.

**One question, because the answer is core's and not mine.** The `0.4.0` §implstatus
text and the `-02` change list item 23 describe `ND-040` as canonicalization. That
description is now known to be incomplete in the same way the CHANGELOG's was: it
covers one of three cases. If any draft or paper text says or implies that URL
canonicalization closes the redirector case, it needs the same correction the
CHANGELOG got. **I have not touched it** — paper and draft claims are core's.

## 5. `ND-050`, ticketed per R027 §2

An envelope-validation `malformed` denial writes **no audit row at all**: `decide_raw`
denies before a policy or an `ActionRequest` exists, so there is nothing to append
against. Recorded as **pre-existing, present in `≤0.4.0`**, found while building U3
and not caused by it.

Severity as core asked: **low blast radius, high principle.** Low — the action does not
happen, the caller is told, nothing is mis-permitted, and the affected requests are by
definition ones the engine could not parse. High — *"the audit log is append-only:
decisions, results, denials, dry-runs, and kill-switch blocks"* is a claim this
repository makes in its README, and one class of denial sits outside it. `0.4.1`
creates an asymmetry it did not cause: a malformed **URL** now writes a row naming
`malformed_kind`, a malformed **envelope** writes none. That is why migration `0010`
names only the value the code emits, rather than inventing a `request_validation` one
for code nobody wrote.

**Not a one-liner.** Appending needs a row shape for a request that failed to parse —
what is `action_type`, what are `params` — and E10 says the unparseable bytes are
exactly what must be frozen. A small ticket with a real design question inside it.

## 6. Verification

Every claim below is the output of a command that ran.

**Gates**, each with the workflow's own command, read from output and not exit code:
`ruff check .` → `All checks passed!`; `ruff format --check .` → `91 files already
formatted`; `mypy onedoor` → `Success: no issues found in 37 source files`;
`pytest -q` → `392 passed, 8 skipped`. **CI green on `7e9fd07`**, `py3.12` and
`py3.13` both `success`, read from the run's own `conclusion`.

**Acceptance**, measured on the instrument that disclosed the gap, with L2 left
untouched because a fix that edits its own baseline has destroyed its evidence:
`L2 evasive 0/4 → L3 evasive 3/4`, `innocent-ok 3/3` at both, `named 5/5` and
`generic✓ 4/4` unchanged. Every number asserted in CI, **including the one that did
not move**: `ND-048`'s base64 shell case is asserted still-failing, so the fix cannot
be read as closing more than it does.

**Publication.** The published bytes **are** the verified bytes: `sha256` of the wheel
and sdist downloaded from PyPI and from the GitHub release both equal the digests
verified before handover — `ee8054cc…` and `61cd143c…`, four downloads, one pair of
digests. A clean venv installing `onedoor==0.4.1` **from PyPI** reaches migration head
`0011_opaque_evidence`, carries all three new evidence columns, and returns four
correct verdicts on the new surface: innocent permitted, percent-encoded host
proposed, declared redirector proposed, unreadable target denied. The published
release notes are byte-identical to `RELEASE_NOTES_v0.4.1.md` and a verbatim substring
of `CHANGELOG.md` — same `sha256` on both sides, not a rewrite.

**One self-caught process defect.** The first draft of the handover told Shamik to
confirm CI green on `61fb46a`. No CI run exists for `61fb46a` — both commits went out
in one push, so the workflow ran once, on the tip. Checking would have found an
absence, and *"no run for that SHA" is unverifiable, not pass*: the two-outcome
collapse arriving in a handover rather than in a verifier. Corrected before publication
to the run that exists, with the difference between the two commits stated.

## 7. Next

`0.4.x` per the standing plan. `ND-001`/`ND-010` remain the crypto epic's next step;
`ND-009` can run in parallel; `ND-050` is backlogged and unscheduled. Awaiting the
Phase-B read-only receipt viewer as its own declaration.

Integrity: sha256(body) = c26dfa31429159ef71c88c8eface09b3f0b1a2fc92a34ccc108834a0825aaf74
