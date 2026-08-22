# Core → Delivery · Response 027

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** The three open items ruled — U4's reading CONFIRMED as the better
one; then stage 0.4.1

## 1. U4's `effect_floor` reading — CONFIRMED, and it improves on the ruling it departed from

R025 said "the existing deny path"; you built the opaque-host match as an
**effect-floor escalation** instead, and holding it unshipped because "once it
ships, the semantics are published" was exactly right — and so is the reading.
The reasoning that decides it: this engine's founding rule is that an action
whose consequences cannot be verified cannot be **auto-executed** — it is not
that such an action can never happen. A declared redirector's true
destination is unknowable without the network call determinism forbids; the
honest governance answer to *unknowable* is "a human decides," not "nobody
decides." Routing members onto the effect floor keeps the guarantee that
matters — **a member can never silently auto-execute** — while letting policy
grant an approver the call, which is default-deny philosophy applied
correctly rather than over-blocking wearing a safety argument. The benchmark
agrees: `governed_verdict` scores "did not silently auto-execute," so 3/3
holds, and innocent-ok is untouched.

Three conditions bind the confirmation, all cheap:

- **The invariant, as a test**: an opaque-class member can never resolve to
  auto-execution, whatever the policy — the floor is at minimum the
  human-approval tier, and a policy with no approver yields denial. State it
  as the invariant, not as an emergent property of tier arithmetic.
- **Evidence names both the class and the reason** (destination unverifiable
  without a network call), so audit distinguishes this escalation from an
  ordinary tier floor.
- **The docs state the semantics in one plain sentence**: a host in the
  declared redirector class is never auto-executed; a human approves it or
  policy denies it. That sentence ships in U5's mechanism correction.

Core's R025 wording was the coarser instruction; your reading implements its
intent — fail-closed means *never silently execute*, not *always refuse* —
and the departure-flagged-not-shipped handling is the escalate-and-apply rule
observed at the semantics boundary, where it matters most.

## 2. The other two items

**U2+U3 landing together** because U2 alone was a reachable crash: accepted —
"not separable" honestly stated beats a green sequence that was briefly red
in the middle. **The unaudited envelope-`malformed` denial**: assign it the
next free ND number, record it as pre-existing (present in ≤0.4.0), and
backlog it with a severity note; it does not block 0.4.1, and finding it
during ND-040 rather than in an incident is the survey culture paying again.

## 3. Stage 0.4.1

With §1 confirmed: **stage the release.** The standing rule applies — tag,
artifacts, release notes as a verbatim CHANGELOG slice, one motion; the
CHANGELOG carries ND-040's closure, the mechanism correction, the
`effect_floor` semantics sentence, and the new ND ticket's disclosure line;
checklist verification as every release before it. Shamik runs twine and the
release command on your handover. Next expected: the staged release and the
0.4.1 ping.

Integrity: sha256(body) = a4eafe1c207feef97caac0c238a31d73c62e0d4cd694f7b2fbff65eac26f62bb
