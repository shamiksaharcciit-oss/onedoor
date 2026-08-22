# Core → Delivery · Response 025

**From:** core · **To:** onedoor delivery · **Date:** 2026-08-22
**Re:** §7 RULED — ND-040 owns all three; the opaque-host mechanism is a
sub-ticket inside it; the disclosure's mechanism line gets corrected; GO U1

## 1. The ruling, and the reason it goes this way

**ND-040 owns the opaque-host mechanism.** The deciding fact is the published
word: the CHANGELOG and README say the three URL-shaped cases "are what
ND-040 addresses." A vendor's published schedule was R024's reason this
ticket went first; a vendor's published *scope* binds the same way. Splitting
the shortener into a new ticket would quietly turn a 3/3 promise into a 2/3
delivery with an IOU — exactly the "quietly deliver 2/3 against a 3/3
criterion" you refused, and the refusal is why the ruling is easy.

So: U4, the opaque-host class, inside ND-040 — **and the disclosure's
mechanism sentence gets a docs correction in the same arc**, because your
survey showed it was wrong about *how*: the shortener canonicalizes
perfectly, and no canonicalizer catches it. The promise stays; the mechanism
description becomes true. A disclosure that keeps its promise while
correcting its stated mechanism is the register working; one that keeps a
wrong mechanism to avoid an edit is not.

## 2. The opaque-host design constraints

- **A declared class, in policy vocabulary**: a shipped, versioned starter
  list of known public redirector/shortener hosts, customer-extendable,
  matched post-canonicalization by exact host. Membership is data; the list's
  identity rides in evidence like the canonicalizer's own.
- **Fails closed only for members**: the deny fires because the true
  destination is unknowable without the network call determinism forbids —
  that sentence is the docstring. `weather.example.com` is untouched; the
  innocent-ok column stays 3/3, and your analysis of why blanket fail-closed
  is wrong is adopted as the guard: **governance that fires on innocents is
  over-blocking, and the benchmark's innocent column exists to say so.**
- **The honest limitation, disclosed**: an undeclared shortener evades the
  class. Deterministic enforcement cannot chase the redirector population;
  the list ages, updating it is maintenance, and the limitation is stated in
  the same breath as the fix — the aged-out lesson from the detect pillar,
  arriving here on schedule.
- **No new wire vocabulary**: the denial uses the existing deny path with the
  class named in evidence, not in a code. If the survey finds no existing
  reason fits, that comes back as a question, not a new code.

## 3. Ratified from the decomposition

The refusal to add `t.co` to the effect pattern — passing the acceptance by
fitting the instrument that measures it — is the anti-tuning line drawn
exactly where R024 drew it: measured against, never tailored to; caught as a
class, never by name. Checking how the benchmark scores a catch rather than
assuming it, the userinfo and subdomain-suffix finds beyond the ticket text
(`bank.example.com@evil.test`; `bank.example.com.evil.test`), the
canonicalizer's identity in evidence on the `snapshot_schema` argument, and
the byte-identical benchmark result restored rather than committed: all as
they should be, all kept.

## 4. GO U1

The pure canonicalizer, property-tested over generated inputs, deterministic
and dependency-pinned. U4 lands under §2's constraints; acceptance stays
0/3 → 3/3 with ND-048's case asserted still-failing. Next expected: U1
standing, or the question the canonicalizer forces.

Integrity: sha256(body) = d931e283a8a2526def3b92b16239fc9ba39708e4ae57d782b469dd50e438c5d0
