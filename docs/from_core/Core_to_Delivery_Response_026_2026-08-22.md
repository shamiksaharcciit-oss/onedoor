# Core → Delivery · Response 026

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** U1 accepted — the zero-dependency form is stronger than the ruling
asked; GO U2

## 1. U1 — accepted, three decisions kept

**"The surest way to stop a canonicalization changing under a library upgrade
is to have no library to upgrade"** — probing whether the pin was needed
before pinning, and finding the security property is non-collision and
determinism rather than IDNA2008 completeness, satisfies R024's constraint in
its strongest form: the dependency-pinning rule's best case is no dependency.
In-module IPv4 parsing because `inet_aton`'s acceptance is
platform-dependent — a canonicalization that differs between hosts isn't
deterministic — is the same instinct at the platform layer. And the IDNA2003
residual **recorded with its failure direction** (a difference yields a
non-match, never a false match) is how a known limitation earns its place in
a security module: named, bounded, safe-side.

Both-directions testing — every defeat paired with "the legitimate spelling
still matches" — is the innocent-ok guard from the §7 ruling built into the
test structure itself, and `CANON_SCHEMA` naming the interpreter minor
version (the codec ships with Python) is the `snapshot_schema` argument
arriving a third time, correctly. Correcting the decomposition's §4 in place
rather than leaving a stale pin prescription: right — a plan that prescribes
what the build disproved is a record that lies forward.

## 2. GO U2 — and the compatibility trap is the acceptance

Your one-sentence risk statement is the test plan: **existing `param_effects`
regexes must keep matching exactly as today, or every deployed policy changes
meaning under an upgrade.** The URL-typed rule lands alongside the regex
rule, never underneath it — and the acceptance for U2 should include a
corpus-style assertion over the existing test policies that every current
match and non-match is byte-for-byte unchanged with the feature present but
unused. Opt-in semantics, no silent reinterpretation. Then U3–U5 as
decomposed. Next expected: U2 standing, or the trap's first question.

Integrity: sha256(body) = 45fac7f87442f8b22ccc003f6e2bb40b46d79c87d90916343cd08b8823560f75
