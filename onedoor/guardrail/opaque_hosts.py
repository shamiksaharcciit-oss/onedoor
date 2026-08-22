"""Hosts whose real target cannot be determined without a network call (ND-040, U4).

`https://t.co/x9k2` canonicalizes perfectly: scheme `https`, host `t.co`, path
`/x9k2`. Nothing fails, and nothing in U1 or U2 catches it, because **the shortener
is not a canonicalization problem at all** — the host genuinely *is* `t.co`, and the
bank is reachable only by following a redirect. Following it is a network call:
non-deterministic, forbidden by the PDP's offline evaluation model, and forbidden by
R024's determinism constraint on this very instrument.

So the mechanism cannot be "resolve it". It has to be **"declare that you cannot"**:
a versioned class of hosts whose target is unknowable, matched by exact host after
canonicalization, treated as *possibly the declared target* — because it might be.

Why membership makes the rule match rather than denying outright
----------------------------------------------------------------
A member host is handled **exactly as the declared target would be**: the rule's
`add_effects` apply, and the effect's tier floor and caps decide the verdict. That is
the whole semantics, and it is the conservative direction by construction — an effect
can only raise a floor or add a cap, never lower one — so an opaque host can never be
*more* permitted than a known one. It also needs **no new wire vocabulary** (R025):
the reason code is `effect_floor`, which already exists and already means what
happened. A separate deny path would have had to invent a code for "we could not tell
where this goes", and inventing wire vocabulary to describe an evidence fact is
exactly what R013 declined to do for malformed URLs.

Why the class fails closed for members ONLY
-------------------------------------------
Measured, not assumed. The benchmark's false-positive column is `innocent-ok 3/3`,
and one of those innocents is `https://weather.example.com/today` on the same
`net.http` action. A rule that governed every host not on an allowlist would take
`evasive 0/3 -> 3/3` and `innocent-ok 3/3 -> 2/3`. **Governance that fires on
innocents is over-blocking**, and the benchmark exists partly to say so. Nothing here
touches a host that is not a declared member.

The limitation, stated where the fix is
---------------------------------------
**An undeclared shortener is not caught.** This list is a starter, not a census:
new redirectors appear constantly, anyone can run one on their own domain, and a
determined caller can use one this file has never heard of. The mechanism raises the
cost of that evasion and names the ones worth naming; it does not close the class.
Saying otherwise would be the same overstatement the `ND-040` disclosure already had
to correct once. `extra` on the policy's `opaque` block exists precisely because the
deployer knows their own environment's redirectors better than this file does.

Membership is a claim about the **service** — that it exists to turn one URL into
another — never about any particular link. A shortened link to an innocuous page is
still opaque *to the PDP at decision time*, which is the only moment that matters.
"""

from __future__ import annotations

from onedoor.guardrail.urlcanon import CanonicalizationError, _canonical_host

OPAQUE_HOSTS_SCHEMA = "onedoor/opaque-hosts/1"
"""Identity of the shipped class, recorded beside a verdict that depends on it.

Versioned for the same reason `canon_schema` and `snapshot_schema` are: adding a host
to this list changes what some policy matches, so a verdict that changes after an
upgrade has to be attributable to the list rather than to the rules. Adding a host is
a **visible instrument change**, and the version is how it becomes visible.
"""

POLICY_DECLARED = "policy"
"""Recorded when a deployer's own `extra` entry matched rather than the shipped list."""

BUILTIN: frozenset[str] = frozenset(
    {
        # General-purpose URL shorteners.
        "bit.ly",
        "buff.ly",
        "cutt.ly",
        "goo.gl",
        "is.gd",
        "ow.ly",
        "rb.gy",
        "rebrand.ly",
        "s.id",
        "shorturl.at",
        "t.ly",
        "tiny.cc",
        "tinyurl.com",
        "v.gd",
        # Platform-operated shorteners and link wrappers.
        "amzn.to",
        "dlvr.it",
        "fb.me",
        "ift.tt",
        "lnkd.in",
        "t.co",
        "trib.al",
        "youtu.be",
    }
)
"""The shipped starter list. Canonical hosts, lowercase, no trailing dot.

Kept deliberately short and boring: every entry is a service whose *purpose* is to
stand between a caller and a destination. A list that grew by suspicion rather than by
that test would start governing hosts for looking unfamiliar, which is the
over-blocking failure the benchmark's innocents column measures.
"""


def declared_members(extra: tuple[str, ...] | list[str]) -> frozenset[str]:
    """Canonicalize a deployer's `extra` list once, at policy-load time.

    Raises :class:`CanonicalizationError` for an entry that cannot be read as a host,
    so an authoring error surfaces when the policy is written rather than as a rule
    that silently never matches.
    """
    return frozenset(_canonical_host(host)[0] for host in extra)


def classify(canonical_host: str, *, builtin: bool, extra: frozenset[str]) -> str | None:
    """Which declared opaque class does this host belong to, if any?

    Returns the class identity for the evidence row, or None for a host whose target
    the policy has not declared unknowable. Exact host match only (R025): a subdomain
    of a shortener is a different service, and suffix matching without a label
    boundary is the classic bypass in the opposite direction.
    """
    if canonical_host in extra:
        return POLICY_DECLARED
    if builtin and canonical_host in BUILTIN:
        return OPAQUE_HOSTS_SCHEMA
    return None


__all__ = [
    "BUILTIN",
    "OPAQUE_HOSTS_SCHEMA",
    "POLICY_DECLARED",
    "CanonicalizationError",
    "classify",
    "declared_members",
]
