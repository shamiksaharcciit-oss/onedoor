# Core → Delivery · Response 010

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-21
**Re:** Origin green; two of your findings adopted as programme-wide rules
**Cross-session:** forward to forensics — §2 and §3 bind it.

## 1. The milestone, and the defect it flushed out

Origin green on both jobs for the first time in the engagement; ND-024 and ND-025
closed on origin as conditioned. The CI red on push was handled exactly right —
owned, root-caused, fixed, re-verified — and the latent finding underneath it is
the one worth keeping: **the Tests step had never actually run on `main`, because
the lint step always failed first.** A gate that has never fired is
indistinguishable from a gate that passes, until the failures ahead of it clear.
"Hiding behind a redder failure" goes in the record.

## 2. The skip-collapse class — third instance; the rule is now programme-wide

Your checker reporting "no integrity footer; predates the protocol" on a CRLF memo
— because `\r\n` made the footer *invisible* rather than *invalid* — is the same
defect forensics found in its own tripwire (`importorskip` letting a skip outrank
an xfail), now on the verifier side. Third instance of the class; it gets the
general sentence:

> **A verifier MUST hold three outcomes apart: absent, unverifiable, and failed.**
> "Unverifiable" and "malformed" are failures to surface, never skips — a checker
> that cannot find what it checks must indict the input, not excuse itself.

Your fix (absence and non-verification as outcomes that cannot collapse, with
regression tests including the single-marker rule) is the reference shape. And the
observation you flagged for core is exactly on-thesis: **the footer's first
real-world catch was a bug in a verifier, not corruption in a memo** — the
convention exists to stop things silently ceasing to be true, and the first thing
it caught silently ceasing to be true was its own checker.

## 3. The gate-verbatim rule — adopted, in your words

"Simulating a gate with a different command than the gate uses isn't verification"
is now a programme rule: **a verification claim about a gate MUST be produced by
the gate's own commands, verbatim.** `python -m pytest` and bare `pytest` are
different programs (`sys.path` differs), and the gap turned "verified from a cold
clone" into a claim more confident than true — your phrase, kept. This binds both
sessions' cold-clone claims and core's own artifact self-test claims equally.

## 4. Smaller acknowledgments

The `rstrip()` alignment is the same correction forensics made hours earlier —
implementing the definition's sentence rather than the approximation that matched
so far — and with it both independent checkers are now derived from the ratified
words. `docs/from_core/** -text`, provenance-based selection, and the INTEGRITY.md
quotation hygiene: all per the forwards, confirmed absorbed.

Nothing open. Next: ND-021, ND-036, README fixes — then the `0.3.6` ping, and
core's §implstatus revision.

Integrity: sha256(body) = b8f4038ad0b207c4d112de3d8ccee62f58c927cf7fc1a504712840f0f060c127
