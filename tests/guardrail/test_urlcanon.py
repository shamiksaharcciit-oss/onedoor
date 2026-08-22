"""The URL canonicalizer (ND-040 / U1).

Every test here comes in the same shape: **the evasion is caught AND the legitimate
spelling still matches.** A canonicalizer tested only in the deny direction is how a
scope gate becomes an over-blocker, and the benchmark's `innocent-ok` column exists
to say so.

Inputs for the equivalence and collision properties are **generated**, not
hand-picked. The standing reminder: an exhaustive-looking search for a corrupted
character missed `⇒` because the candidate set was assembled from characters already
seen, and a hand-written list of URL spellings has the same shape of blind spot.
"""

from __future__ import annotations

import itertools
import random

import pytest

from onedoor.guardrail.urlcanon import (
    CANON_SCHEMA,
    CanonicalizationError,
    canonicalize,
    host_matches,
)

BANK = "bank.example.com"


# --------------------------------------------------------------------------
# The named defeats: each one, both directions.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spelling", "why"),
    [
        ("https://bank.example.com/transfer", "the plain form"),
        ("https://BANK.Example.COM/transfer", "host case"),
        ("https://bank.example.com./transfer", "trailing dot -- same host to a resolver"),
        ("https://bank%2Eexample%2Ecom/transfer", "percent-encoded dots"),
        ("https://bank.example.com:443/transfer", "the scheme's default port"),
        ("HTTPS://bank.example.com/transfer", "scheme case"),
        ("  https://bank.example.com/transfer  ", "surrounding whitespace"),
    ],
)
def test_equivalent_spellings_reach_the_same_target(spelling: str, why: str) -> None:
    assert canonicalize(spelling).host == BANK, why


@pytest.mark.parametrize(
    ("spelling", "why"),
    [
        ("https://bank.example.com@evil.test/x", "userinfo: the host is what follows @"),
        ("https://bank.example.com.evil.test/x", "suffixing: a different registrable domain"),
        ("https://bankexample.com/x", "a missing dot is a different host"),
        ("https://xbank.example.com/x", "a prefixed label is a different host"),
        ("https://бank.example.com/x", "Cyrillic homograph"),
    ],
)
def test_lookalikes_do_not_reach_the_target(spelling: str, why: str) -> None:
    """The other direction. Canonicalisation must not manufacture matches either."""
    assert canonicalize(spelling).host != BANK, why


def test_the_homograph_encodes_to_punycode_rather_than_colliding() -> None:
    """A homograph is a *different host*, and must be visibly so.

    The security property is non-collision, not IDNA2008 completeness -- which is
    what lets this run on the standard library with no dependency to pin.
    """
    canon = canonicalize("https://бank.example.com/x")
    assert canon.host.startswith("xn--")
    assert canon.host != BANK


# --------------------------------------------------------------------------
# IP literals: a resolver accepts several spellings of one address.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spelling",
    ["https://127.0.0.1/x", "https://0x7f.1/x", "https://2130706433/x", "https://127.1/x"],
)
def test_ipv4_shorthand_forms_reach_one_address(spelling: str) -> None:
    canon = canonicalize(spelling)
    assert canon.host == "127.0.0.1"
    assert canon.is_ip


def test_ipv6_is_compressed_to_one_form() -> None:
    assert canonicalize("https://[0:0:0:0:0:0:0:1]/x").host == canonicalize("https://[::1]/x").host


def test_an_ip_literal_is_marked_as_one() -> None:
    """`is_ip` is what lets a rule apply CIDR semantics instead of name semantics."""
    assert canonicalize("https://203.0.113.7/transfer").is_ip
    assert not canonicalize("https://bank.example.com/transfer").is_ip


# --------------------------------------------------------------------------
# Refusal: a parse differential becomes a denial, never a bypass.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spelling", "why"),
    [
        ("", "empty"),
        ("   ", "whitespace only"),
        ("bank.example.com/x", "no scheme: no single interpretation"),
        ("//bank.example.com/x", "scheme-relative"),
        ("https://", "no host"),
        ("https://bank%2Fevil.test/x", "percent-encoding hid a delimiter"),
        ("https://bank%40evil.test/x", "percent-encoded userinfo separator"),
        ("https://[not-an-ipv6]/x", "unparseable IPv6 literal"),
        ("https://" + "a" * 300 + ".test/x", "label too long for the IDNA codec"),
        ("https://bank..example.com/x", "empty label"),
    ],
)
def test_uninterpretable_targets_are_refused_not_guessed(spelling: str, why: str) -> None:
    """scopegate's sentence: interpret at least as strictly as the networking stack.

    Where that is impossible, refuse. The caller turns this into a `malformed`
    denial (R013), so a parse differential is a denial rather than a bypass.
    """
    with pytest.raises(CanonicalizationError):
        canonicalize(spelling)


# --------------------------------------------------------------------------
# Properties, over generated inputs.
# --------------------------------------------------------------------------


def _generated_urls(rng: random.Random, n: int = 400) -> list[str]:
    hosts = ["bank.example.com", "pay.example.com", "weather.example.com", "t.co", "a.b.c.d.test"]
    schemes = ["http", "https", "HTTP", "HttpS"]
    paths = ["/", "/transfer", "/a/b?q=1", "/x#frag", ""]
    out = []
    for _ in range(n):
        host = rng.choice(hosts)
        if rng.random() < 0.3:
            host = host.upper() if rng.random() < 0.5 else host + "."
        if rng.random() < 0.2:
            host = host.replace(".", "%2E", rng.randint(1, 2))
        scheme = rng.choice(schemes)
        port = ""
        if rng.random() < 0.25:
            port = ":443" if scheme.lower() == "https" else ":80"
        out.append(f"{scheme}://{host}{port}{rng.choice(paths)}")
    return out


def test_canonicalization_is_idempotent() -> None:
    """A normalizer that is not a fixed point cannot be an instrument."""
    rng = random.Random(20260822)
    for url in _generated_urls(rng):
        once = canonicalize(url)
        assert canonicalize(str(once)) == once, f"not a fixed point: {url!r}"


def test_the_same_input_always_gives_the_same_output() -> None:
    """Determinism, asserted rather than assumed: no clock, no I/O, no hidden state."""
    rng = random.Random(20260822)
    for url in _generated_urls(rng, n=120):
        assert canonicalize(url) == canonicalize(url)


def test_distinct_hosts_never_collide() -> None:
    """Canonicalisation must lose spelling, never identity.

    A normalizer that maps two different targets together is worse than none: it
    would let a rule written for one host match another.
    """
    hosts = [
        "bank.example.com",
        "pay.example.com",
        "bankexample.com",
        "bank.example.com.evil.test",
        "evil.test",
        "t.co",
        "127.0.0.1",
        "203.0.113.7",
    ]
    canon = {h: canonicalize(f"https://{h}/x").host for h in hosts}
    for a, b in itertools.combinations(hosts, 2):
        assert canon[a] != canon[b], f"{a} and {b} canonicalized to the same host"


def test_equivalent_spellings_agree_across_the_generated_space() -> None:
    """Every spelling of one host reaches one canonical host."""
    rng = random.Random(20260823)
    groups: dict[str, set[str]] = {}
    for url in _generated_urls(rng):
        canon = canonicalize(url)
        groups.setdefault(canon.host, set()).add(url)
    # the generator must actually have produced several spellings per host
    assert any(len(v) > 5 for v in groups.values()), "the probe space is too thin to prove anything"
    for host, urls in groups.items():
        for url in urls:
            assert canonicalize(url).host == host


# --------------------------------------------------------------------------
# host_matches: the label boundary is where the bypass lives.
# --------------------------------------------------------------------------


def test_subdomain_matching_respects_the_label_boundary() -> None:
    """`bank.example.com.evil.test` shares a PREFIX, not a suffix, with the target.

    Suffix matching without a label boundary is the classic bypass, so the boundary
    is enforced rather than assumed -- and `include_subdomains` is explicit, because
    the two readings disagree exactly where an attacker lives.
    """
    assert host_matches(BANK, BANK, include_subdomains=False)
    assert not host_matches("evil.test", BANK, include_subdomains=False)

    assert host_matches("a.example.com", "example.com", include_subdomains=True)
    assert not host_matches("a.example.com", "example.com", include_subdomains=False)

    # the bypasses
    assert not host_matches("bank.example.com.evil.test", BANK, include_subdomains=True)
    assert not host_matches("notexample.com", "example.com", include_subdomains=True)
    assert not host_matches("xexample.com", "example.com", include_subdomains=True)


def test_the_declared_host_is_canonicalized_too() -> None:
    """A policy written `BANK.Example.COM.` must mean the same host as the request."""
    assert host_matches(BANK, "BANK.Example.COM.", include_subdomains=False)


def test_the_schema_names_the_algorithm_and_its_interpreter() -> None:
    """Once a verdict depends on a normalisation, that normalisation's identity is
    part of what the verdict means -- the snapshot_schema / unicode_version argument."""
    assert CANON_SCHEMA.startswith("onedoor/url-canon/")
    assert "py3." in CANON_SCHEMA
