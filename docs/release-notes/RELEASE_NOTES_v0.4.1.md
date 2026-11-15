**Additive. Nothing existing changes meaning.** New opt-in policy vocabulary and two
forward-only migrations; every rule you have deployed matches exactly what it matched
under `0.4.0`, which is asserted rather than intended (see the compatibility corpus
below). No wire-observable change: no new reason codes, no changed verdict shapes, no
signature changes. A `-00` enforcement point is unaffected.

**Upgrading:** run the engine once to apply migrations `0010`–`0011`. Nothing else.

### Added — `ND-040`: URL-valued parameters are matched as URLs

A `param_effects` rule may now declare a `url:` block instead of a `pattern:`, and
matching happens against the **canonicalized target** rather than the parameter's
string form. Opt-in: a rule without a `url:` block matches exactly what it matched
before, and `tests/guardrail/test_param_effects_compat.py` asserts that against every
pattern shipped in this repository plus generated inputs — no deployed policy changes
meaning because the engine was upgraded.

```yaml
param_effects:
  - param: url
    add_effects: [money.egress]
    url:
      hosts: [bank.example.com]      # canonicalized on both sides
      include_subdomains: false      # explicit, never implied
      cidrs: [203.0.113.0/24]        # for IP-literal targets
      schemes: [https]
      opaque: {builtin: true}        # hosts whose target cannot be known
```

**Correcting the mechanism sentence in the `0.4.0` disclosure.** That entry said the
three URL-shaped evasions would be closed by canonicalizing first. Building it showed
that is true of **one** of them. The promise stands and is kept; the description of
how was wrong, and a disclosure that keeps a wrong mechanism to avoid an edit is not
a disclosure register working:

| Evasive case | What actually closes it |
|---|---|
| `https://bank%2Eexample%2Ecom/transfer` | **Canonicalization.** `%2E` decodes to `.`; this is the canonicalization case proper. |
| `https://203.0.113.7/transfer` | **CIDR matching, and a deployer who declares the network.** A hostname pattern cannot express an address at all. The mechanism makes the case expressible; it does not supply the knowledge. |
| `https://t.co/x9k2` | **Not canonicalization at all.** The host really *is* `t.co`; the bank is behind a redirect, and following it is a network call the PDP's offline model forbids. Closed by a **declared class of opaque hosts** — a shipped, versioned starter list plus the deployer's own, matched by exact host after canonicalization, treated as *possibly the declared target* because it might be. |

**The semantics in one sentence:** *a host in the declared redirector class is never
auto-executed; a human approves it, or policy denies it.* An action whose consequences
cannot be **verified** must not be auto-executed — that is not the same as saying it
can never happen. A redirector's true destination is unknowable without the network
call determinism forbids, and the honest governance answer to *unknowable* is "a human
decides", not "nobody decides".

This is an **invariant, not tier arithmetic**. It holds whatever the action's tier is
and whether or not the effect you attached declares a floor. Stating it that way is
not pedantry: relying on the effect floor alone left a real hole, found by probing this
exact condition before release. A policy could declare `opaque` and point at an effect
with `min_tier: null`, and a declared redirector would then auto-execute silently — the
deployer asked for the protection, the engine took the declaration, and nothing
escalated. The mechanism was one YAML line away from being decorative. It never shipped
that way.

**Measured on the instrument that disclosed the gap.**
`experiments/aliasing_benchmark.py` gains an **L3** layer beside L2 — L2 is left
exactly as it was, because a fix that edits the baseline it is measured against has
destroyed its own evidence:

```
layer    named  generic✓  evasive  innocent-ok   note
L2     5/5     4/4       0/4      3/3           + deterministic param rules
L3     5/5     4/4       3/4      3/3           + URL-typed rules (ND-040)
```

`tests/guardrail/test_aliasing_acceptance.py` asserts every number in that table in
CI, **including the one that did not move**: the base64 shell case (`ND-048`) is
asserted *still failing*, so this fix cannot be read as closing more than it does.
`innocent-ok` staying 3/3 is the over-blocking guard — governance that fires on
innocents is a defect, and the opaque-host class is exactly what could have broken it.

- **A target that cannot be interpreted is denied, not guessed.** A parse differential
  becomes a denial rather than a bypass — the governing sentence is `scopegate`'s
  (Apache-2.0, D. Mellafe Zuvic), cited rather than reinvented: *a scope gate must
  interpret a target at least as strictly as the networking stack that will later
  connect to it.* The reason code is the **existing** `malformed`; no new wire
  vocabulary. The audit row records `malformed_kind='url_canonicalization'` and the
  `canon_schema` that produced the verdict, so an operator can tell a broken client
  from someone probing the effect matcher, and so a verdict that changes after an
  upgrade is attributable to the canonicalizer rather than to the rules.
- **No new runtime dependency.** The canonicalization is part of the instrument, so a
  canonicalization that changes under a library upgrade would be an instrument change
  wearing a patch release. The standard library's IDNA codec maps the Cyrillic
  homograph to `xn--ank-9cd.example.com` — visibly not `bank.example.com` — which is
  the whole security property: **non-collision and determinism, not IDNA2008
  completeness**. IPv4 shorthand (`0x7f.1`, `2130706433`, `127.1`) is parsed in-module
  rather than by `socket.inet_aton`, whose acceptance of those forms is
  platform-dependent.
- **Upgrading:** run the engine once to apply migrations `0010`–`0011`, which add
  `malformed_kind`, `canon_schema` and `opaque_class` to `actions_audit`. Forward-only,
  all NULL on existing rows, and NULL means "this verdict did not depend on a
  canonicalization or an opaque declaration" — which for a pre-`ND-040` row is simply
  true.

### Known gaps this does NOT close

- **An undeclared shortener is not caught.** The opaque class is a starter list, not a
  census: new redirectors appear constantly, anyone can run one on their own domain,
  and a caller can use one this list has never heard of. The mechanism raises the cost
  of that evasion and names the ones worth naming; `opaque.extra` exists because a
  deployer knows their own environment's link-wrappers better than we do.
- **The IP-literal case needs a declared network.** A deployer who does not know their
  target's address range cannot write the CIDR that catches it.
- **`ND-048` is untouched.** `bash -c "$(echo <base64> | base64 -d)"` carries no
  matchable literal; the governed effect is real and no deterministic parameter rule
  reaches it. Ticketed as `ND-048` so it cannot age out of the disclosure, with **no
  fix scheduled** — and now asserted as still-failing in the test suite, so the gap
  cannot close by accident either.
- **The stdlib implements IDNA2003**, which differs from IDNA2008 on a handful of
  characters (`ß`, final sigma, a few others). A difference produces a **non-match,
  never a false match**, so the failure direction is safe — but a policy written
  against an IDN host in that set would not match a request spelling it the other way.
- **An envelope-validation `malformed` denial writes no audit row** (`ND-050`). A
  request whose envelope fails validation is denied before a policy or a request
  object exists, so there is nothing to append against and the returned result carries
  no `audit_id`. **Present in `≤0.4.0`; found while building `ND-040` and not caused by
  it.** The action does not happen and the caller is told, so nothing is mis-permitted
  — but "the audit log is append-only: decisions, results, denials, dry-runs and
  kill-switch blocks" is a claim this project makes, and one class of denial is outside
  it. Note the asymmetry this release creates and did not cause: a malformed **URL**
  now writes a row naming `malformed_kind`, a malformed **envelope** writes none.
  Ticketed, not fixed here — appending needs a row shape for a request that failed to
  parse, which is a design question rather than a one-liner.
