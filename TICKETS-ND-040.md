# `ND-040` — URL-typed parameter canonicalization · decomposition

**Ticket:** `ND-040`, `0.4.x`, immediately after `0.4.0` per R011.
**Baseline:** `0.4.0` @ `5c50466`, published; 257 passed / 8 skipped, four gates green.
**GO:** R024 §2 — decompose before code.
**Why first:** the README and CHANGELOG promise this fix *"immediately after `0.4.0`"*.
A security vendor's published schedule is a commitment the way its disclosures are.

**Prior inputs, all settled — cite, do not rediscover:**

- **Reason code (R013):** canonicalization failure denies with **`malformed`**. No new
  wire vocabulary; `CheckId.MALFORMED` already exists and is already emitted.
  **Condition:** the failure is recorded **distinctly in evidence** — an evidence
  field, not a wire code — so audit separates malformed-JSON from malformed-URL.
  `-02` change-list item 23.
- **Scope (R016/R019 thread):** three of the benchmark's four evasive cases are
  URL-shaped. `ND-048`'s base64-obfuscated shell command is **explicitly outside**
  this ticket.
- **Prior art:** `scopegate` (Apache-2.0, D. Mellafe Zuvic) is read and cited, not
  reinvented — *a scope gate must interpret a target at least as strictly as the
  networking stack that will later connect to it.*
- **R024 constraints:** the canonicalizer is **deterministic and dependency-pinned**
  (a canonicalization that changes under a library upgrade is an instrument change
  wearing a patch release), and the benchmark's three URL cases are the **acceptance
  tests**, 0/3 → 3/3, with `ND-048`'s case **asserted still-failing**.

---

## 1. The finding: these are three different problems, not one

The survey's most important result. `experiments/aliasing_benchmark.py` scores a case
as *caught* when the engine does **not** silently auto-execute — a denial and a Tier-3
proposal both count (`governed_verdict`). Measured against the shipped rule
`https://(bank|pay)\.example\.com/.*`:

| # | Evasive case | What defeats the rule | Closed by canonicalization? |
|---|---|---|---|
| 1 | `https://t.co/x9k2` | The host **is** `t.co`. The bank is behind a redirect. | **No.** See §2. |
| 2 | `https://203.0.113.7/transfer` | An IP literal is not a hostname. | Only with **CIDR matching** *and* a policy that declares the target's range. |
| 3 | `https://bank%2Eexample%2Ecom/transfer` | `%2E` is `.` after decoding. | **Yes** — this is canonicalization proper. |

**Canonicalization alone closes one of the three.** Saying "URL canonicalization gets
us 0/3 → 3/3" would be the same overstatement the `ND-040` disclosure already had to
correct once, when citing 0/4 implied this ticket closed the shell case too. It does
not, and neither does it close the shortener.

## 2. The shortener is not a canonicalization problem, and that is the question

`https://t.co/x9k2` canonicalizes perfectly: scheme `https`, host `t.co`, path
`/x9k2`. Nothing fails. The host genuinely *is* `t.co`; the bank is only reachable by
following a redirect, which is a **network call** — non-deterministic, and forbidden
by R024's determinism constraint and by the PDP's offline evaluation model.

So catching it needs a **second mechanism**: a declared class of hosts whose target
cannot be determined (redirectors, shorteners, open proxies) that **fails closed**.

**Why blanket fail-closed is wrong, measured not assumed.** The benchmark's
false-positive column is `innocent-ok 3/3` today, and one innocent is
`https://weather.example.com/today` on the same `net.http` action. A rule that denies
every host not on an allowlist would deny that too — trading `evasive 0/3 → 3/3` for
`innocent-ok 3/3 → 2/3`. **Governance that fires on innocents is over-blocking**, and
the benchmark exists partly to say so.

**What must NOT be done:** adding `t.co` to the effect pattern. That would make the
acceptance test pass by fitting the instrument that measures it — the fix would score
3/3 and close nothing. R024's wording is *measured against* the benchmark, not
tailored to it. Any mechanism here has to be general, and the benchmark's shortener
must be caught as an instance of a class, never by name.

**RULED (R025): `ND-040` owns it, as U4 inside this ticket** — the published scope
binds the way the published schedule does. Constraints: a **declared, versioned class**
of known redirector/shortener hosts, shipped as a starter list and customer-extendable,
matched **post-canonicalization by exact host**; **fails closed for members only**, so
`weather.example.com` is untouched and `innocent-ok` stays 3/3; the **undeclared-shortener
limitation is disclosed in the same breath as the fix**; and **no new wire vocabulary** —
the existing deny path with the class named in evidence. The disclosure's *mechanism*
sentence is corrected in the same arc: the promise stays, the description becomes true,
because the survey showed the shortener is not a canonicalization problem at all.

## 3. The canonicalization surface

R024 named it; the survey confirms each has a defeat in the current matcher, which
compares `re.fullmatch(pattern, str(value))` against a raw string
(`decision.py:117`).

| Concern | Why it bites |
|---|---|
| Percent-decoding | `bank%2Eexample%2Ecom` — case 3, the one this closes outright |
| Scheme normalization | `HTTPS:` vs `https:`; scheme-relative `//host/…` |
| IDNA / homographs | `bаnk.example.com` with Cyrillic `а`; punycode `xn--` forms |
| Host case | `BANK.example.com` |
| Trailing dot | `bank.example.com.` is the same host to the resolver |
| Userinfo | `https://bank.example.com@evil.test/` — the host is `evil.test` |
| Port defaulting | `https://bank.example.com:443/` ≡ no port |
| Subdomain semantics | `bank.example.com.evil.test` must not match `bank.example.com` |
| IP literals + CIDR | case 2; also `0x7f.1`, `2130706433`, IPv6 `[::1]`, IPv4-mapped |

**Deny on canonicalization failure.** A URL the canonicalizer cannot interpret is
`malformed` — a parse differential becomes a denial rather than a bypass. This is the
half of the ticket that is unambiguous and where scopegate's sentence lands.

## 4. Determinism and pinning (R024)

The canonicalization is part of the instrument: it decides what a rule matches, so a
change to it changes verdicts. Therefore:

- **No dependency to pin — resolved in U1, stronger than planned.** This section
  originally called for pinning `idna` exactly. The probe showed that unnecessary: the
  security property a canonicalizer needs is **non-collision and determinism**, not
  IDNA2008 completeness, and the standard library's IDNA codec already maps the
  Cyrillic homograph to `xn--ank-9cd.example.com` — visibly not `bank.example.com`,
  which is the whole requirement. So U1 adds **no runtime dependency at all**, which
  is the strongest available reading of *a canonicalization that changes under a
  library upgrade is an instrument change wearing a patch release*: the surest way to
  prevent that is to have no library to upgrade. It also avoids exact-pinning a
  runtime dependency of a *library*, which conflicts with every downstream that also
  depends on `idna`.
  IPv4 shorthand (`0x7f.1`, `2130706433`, `127.1`) is parsed in-module rather than by
  `socket.inet_aton`, whose acceptance of those forms is **platform-dependent** and
  therefore cannot be part of a deterministic instrument.
  The residual edge is recorded rather than hidden: the stdlib implements IDNA2003,
  which differs from IDNA2008 on a handful of characters. A difference yields a
  **non-match, never a false match**, so the failure direction is safe.
- **Recorded.** The canonicalizer's identity and version belong in the evidence, the
  same argument as `snapshot_schema` (R019) and `unicode_version` (E14): once a
  verdict depends on a normalisation, the normalisation's identity is part of what
  the verdict means. **Proposed: a `canon_schema` value recorded on the rule match**,
  so a verdict that changes after an upgrade is attributable rather than mysterious.
- **Property-tested over generated inputs**, not a hand-picked list — the standing
  reminder being the `⇒` miss, where a candidate set drawn from observed data
  reproduced that data's bias.
- **Idempotent**: `canon(canon(u)) == canon(u)`, asserted as a property. A normalizer
  that is not a fixed point cannot be an instrument.

## 5. Acceptance tests (R024)

Measured against the same instrument that disclosed the gap:

1. `experiments/aliasing_benchmark.py` evasive column **0/3 → 3/3** on the URL cases.
2. **`ND-048`'s shell case asserted STILL FAILING**, in the same test, so the fix
   cannot be read as closing more than it does. A negative acceptance criterion is
   the honest counterpart to a positive one.
3. **`innocent-ok` stays 3/3.** Non-negotiable: this is the over-blocking guard, and
   §2's mechanism is exactly what could break it.
4. `named 5/5` and `generic✓ 4/4` unchanged — no regression in what already worked.
5. A canonicalization failure denies `malformed` **and** records the distinct evidence
   field, per R013's condition.
6. Both directions on each canonicalization concern in §3: the evasion is caught
   **and** the legitimate spelling still matches.

## 6. Work order

- **U1** — the canonicalizer: pure, deterministic, pinned, property-tested,
  idempotent. No I/O, no DNS, no network. Ships behind nothing.
- **U2 + U3 — landed together, and they could not be separated.** The work order
  above had them as two steps; building U2 first showed they are one. `decide_raw`
  states plainly that *internal errors are deliberately not swallowed: an exception
  from the policy store, the database or the cap ledger propagates, because
  converting a bug into a routine denial would hide it.* That is right, and it means
  a `CanonicalizationError` raised inside the effect loop would **crash the PDP**
  rather than deny — and a malformed URL from a caller is *input*, not a bug. So U2
  without U3 is not a smaller increment, it is a reachable crash. They landed as one
  commit.

- **U2** — a URL-typed rule alongside the regex rule. The existing `pattern` form
  stays for non-URL params; a URL rule declares host/CIDR/subdomain semantics rather
  than a regex over a string. **Not a silent reinterpretation of existing rules** —
  an existing `param_effects` regex keeps matching exactly as it does today, or every
  deployed policy changes meaning under an upgrade.
- **U3** — deny-on-failure wired to `malformed` plus the distinct evidence field.
- **U4** — the §2 mechanism, **pending core's ruling**, with the innocents column as
  its guard.
- **U5** — benchmark and acceptance tests; CHANGELOG updates the disclosure from
  "known evasion" to "closed", naming precisely which cases and which remain.

## 7. The question this decomposition surfaces

**Does `ND-040` own the opaque-host mechanism, or is that a separate ticket?**

Canonicalization closes case 3 outright and case 2 with CIDR matching. **Case 1
cannot be closed by canonicalization at all** — the target is unknowable without a
network call, which determinism forbids. Closing it needs a declared class of
opaque/redirector hosts that fails closed, which is:

- a **policy-vocabulary** addition (deployers must declare it), and
- the one part of this ticket that can **cause over-blocking**, which the benchmark's
  innocents column measures and which no amount of canonicalization risks.

**Answered: `ND-040` owns all three, U4 carries the opaque-host class.** The published
scope binds like the published schedule, and a disclosure that keeps a wrong mechanism
to avoid an edit is not the register working — so the mechanism sentence is corrected
alongside the fix.

**U1 is done.** No new runtime dependency: the standard library's IDNA codec maps the
Cyrillic homograph to `xn--ank-9cd.example.com`, which is all the security property
needs — **non-collision and determinism, not IDNA2008 completeness**. That is the
strongest available reading of R024's pinning constraint: the surest way to stop a
canonicalization changing under a library upgrade is to have no library to upgrade.
IPv4 shorthand is parsed here rather than by `socket.inet_aton`, whose acceptance
varies by platform and so cannot be part of a deterministic instrument. The IDNA2003
edge is recorded in the module docstring: a difference produces a non-match, never a
false match, so the failure direction is safe.

**U2 and U3 are done.** A `param_effects` rule may now declare a `url:` block
(`hosts`, `include_subdomains`, `cidrs`, `schemes`) *instead of* a `pattern` —
exactly one of the two, enforced at model validation, because a rule with two
meanings has none that can be relied on. R026's acceptance is
`tests/guardrail/test_param_effects_compat.py`: for a corpus covering every pattern
shipped in this repository, plus generated pattern/value pairs, the **engine's**
answer on the regex branch equals `re.fullmatch(pattern, str(value)) is not None` —
the original expression as oracle, not a re-implementation of it, which could drift
in the same direction as the code it checks. The answers are read through
`decide_and_reserve` rather than from a matcher helper, because it is the deployed
path that must not change.

A target the canonicalizer refuses denies with the existing `malformed` (R013, no new
wire vocabulary) and records `malformed_kind='url_canonicalization'` plus
`canon_schema` — migration `0010`, R013's condition satisfied by an evidence field.
Two things found while writing it, recorded rather than smoothed over:

- **The other `malformed` writes no audit row at all.** An envelope that fails
  validation denies in `decide_raw` before a policy or a request object exists, so
  there is nothing to append against. The migration comment therefore names only the
  value the code emits; a `request_validation` value describing code that does not
  exist would be vocabulary for a feature nobody built. It is a pre-existing gap in
  the ledger, not one this ticket closes, and it is worth a ticket of its own.
- **An unreadable target denies even under the kill switch**, which otherwise clamps
  executable tiers to propose-only. A proposal asks a human to approve *this action*,
  and the engine cannot say what this action is. Bounds already behaves this way — an
  out-of-bounds action is denied, never proposed — so this is the same argument
  reaching a new input, but it is now asserted in a test rather than left as an
  emergent property of check ordering.

`ND-048`'s residue is untouched by every option above and stays disclosed as an open
gap with no ticketed fix.
