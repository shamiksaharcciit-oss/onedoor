"""Deterministic URL canonicalization for effect matching (ND-040, U1).

`param_effects` compares a regex against a parameter's *string* form, which is the
right shape for effect derivation and the wrong parser for a URL. A pattern like
`https://(bank|pay)\\.example\\.com/.*` is defeated by percent-encoding, a `user@host`
prefix, a trailing dot, case, an IP literal, and IDN homographs -- disclosed against
`<=0.4.0` and measured by `experiments/aliasing_benchmark.py`.

The governing sentence is `scopegate`'s (Apache-2.0, D. Mellafe Zuvic), cited rather
than reinvented: **a scope gate must interpret a target at least as strictly as the
networking stack that will later connect to it.** Where this module cannot interpret a
target at least that strictly, it refuses rather than guesses -- a parse differential
becomes a denial, never a bypass.

Determinism
-----------
No I/O. No DNS. No network. No clock. The same string canonicalizes to the same
result on every host, forever, or the instrument is not an instrument.

**No new runtime dependency**, which is the strongest available reading of R024's
"deterministic and dependency-pinned": a canonicalization that changes under a
library upgrade is an instrument change wearing a patch release, and the surest way
to prevent that is to have no library to upgrade. Host encoding uses the standard
library's IDNA codec; IP parsing is implemented here rather than delegated to
`socket.inet_aton`, whose acceptance of shorthand forms is platform-dependent and so
cannot be part of a deterministic instrument.

`CANON_SCHEMA` names this algorithm, and belongs in evidence beside a verdict that
depends on it -- the same argument as `snapshot_schema` (R019) and `unicode_version`
(E14). Once a verdict depends on a normalisation, the normalisation's identity is
part of what the verdict means.

Known limitation, stated rather than implied: the standard library implements
IDNA2003, which differs from IDNA2008 on a handful of characters (`ß`, final sigma
and a few others). A difference produces a *non-match*, never a false match, so the
failure direction is safe -- but a policy written against an IDN host in that set
would not match a request spelling it the other way. Recorded here because a
canonicalizer's edges are exactly what a reader needs to know.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from ipaddress import AddressValueError, IPv4Address, IPv6Address
from urllib.parse import unquote, urlsplit

CANON_SCHEMA = f"onedoor/url-canon/1+py{sys.version_info.major}.{sys.version_info.minor}"
"""Identity of this canonicalization, for the evidence row.

The Python minor version is part of it because the IDNA codec ships with the
interpreter: a verdict that depends on a normalisation depends on whose
normalisation it was.
"""

DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}

# Characters that must never appear in a host after percent-decoding. Their presence
# means the encoding was hiding a delimiter -- `bank%2Fevil.test` is not a host with a
# slash in it, it is an attempt to make one string look like another.
_HOST_FORBIDDEN = set("/?#@:\\ \t\n\r\x00[]")


class CanonicalizationError(ValueError):
    """The target could not be interpreted, so it is refused rather than guessed.

    Callers translate this into a denial with reason `malformed` (R013), recording
    the failure distinctly in evidence so audit can tell malformed-URL from
    malformed-JSON without expanding the wire vocabulary.
    """


@dataclass(frozen=True)
class CanonicalUrl:
    """A URL reduced to the form two spellings of the same target share."""

    scheme: str
    host: str
    """Lowercase ASCII: punycode for IDN, canonical text for an IP literal, no
    trailing dot, percent-decoding resolved."""
    port: int | None
    """None when the port is the scheme's default -- `:443` and nothing are the same
    target, and a matcher that disagrees is a bypass."""
    path: str
    is_ip: bool

    def __str__(self) -> str:
        netloc = self.host if self.port is None else f"{self.host}:{self.port}"
        return f"{self.scheme}://{netloc}{self.path}"


def _parse_ipv4_shorthand(text: str) -> IPv4Address | None:
    """Parse the dotted/octal/hex/integer IPv4 forms a resolver accepts.

    `0x7f.1`, `2130706433` and `127.1` all reach 127.0.0.1, and a matcher that only
    understands dotted-quad sees three different strings. Implemented here rather
    than via `socket.inet_aton` because that function's shorthand handling varies by
    platform, and a canonicalization that differs between hosts is not deterministic.
    """
    parts = text.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    values: list[int] = []
    for part in parts:
        if not part:
            return None
        try:
            if part.lower().startswith("0x"):
                value = int(part, 16)
            elif part.startswith("0") and len(part) > 1:
                value = int(part, 8)
            else:
                value = int(part, 10)
        except ValueError:
            return None
        if value < 0:
            return None
        values.append(value)
    # The final part absorbs the remaining octets: 127.1 is 127.0.0.1.
    *leading, last = values
    if any(v > 0xFF for v in leading):
        return None
    span = 8 * (4 - len(leading))
    if last >= (1 << span):
        return None
    packed = 0
    for v in leading:
        packed = (packed << 8) | v
    packed = (packed << span) | last
    try:
        return IPv4Address(packed)
    except AddressValueError:
        return None


def _canonical_host(raw_host: str) -> tuple[str, bool]:
    """Return (canonical host, is_ip). Raises on anything uninterpretable."""
    if not raw_host:
        raise CanonicalizationError("empty host")

    # IPv6 arrives bracketed from urlsplit's netloc but unbracketed from .hostname.
    if ":" in raw_host:
        try:
            return IPv6Address(raw_host.strip("[]")).compressed, True
        except AddressValueError as exc:
            raise CanonicalizationError(f"unparseable IPv6 host: {raw_host!r}") from exc

    # Percent-decoding first: `bank%2Eexample%2Ecom` is `bank.example.com`, and a
    # matcher that does not decode compares against a string nobody will connect to.
    decoded = unquote(raw_host)
    if decoded != unquote(decoded):
        raise CanonicalizationError("doubly percent-encoded host")
    if set(decoded) & _HOST_FORBIDDEN:
        raise CanonicalizationError(f"percent-encoding hid a delimiter in host: {raw_host!r}")

    host = decoded.rstrip(".").lower()
    if not host:
        raise CanonicalizationError("host is only dots")

    ipv4 = _parse_ipv4_shorthand(host)
    if ipv4 is not None:
        return ipv4.compressed, True

    try:
        encoded = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError) as exc:
        # A label too long, an empty label, or a form the codec refuses. The
        # networking stack would reject or resolve it differently than we can
        # predict, so we refuse rather than guess.
        raise CanonicalizationError(f"host is not encodable as IDNA: {raw_host!r}") from exc
    if not encoded or ".." in encoded:
        raise CanonicalizationError(f"malformed host labels: {raw_host!r}")
    return encoded, False


def canonicalize(raw: str) -> CanonicalUrl:
    """Reduce a URL to the form two spellings of the same target share.

    Raises :class:`CanonicalizationError` for anything it cannot interpret exactly.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise CanonicalizationError("empty URL")

    try:
        split = urlsplit(raw.strip())
    except ValueError as exc:
        raise CanonicalizationError(f"unparseable URL: {exc}") from exc

    scheme = split.scheme.lower()
    if not scheme:
        # A scheme-relative or bare-host string has no single interpretation: the
        # scheme decides the default port and often the protocol's own rules.
        raise CanonicalizationError("URL has no scheme")

    try:
        # .hostname resolves userinfo correctly -- the host of
        # `https://bank.example.com@evil.test/` is evil.test, which is exactly the
        # confusion a string matcher falls for.
        raw_host = split.hostname
    except ValueError as exc:
        raise CanonicalizationError(f"unparseable host: {exc}") from exc
    if raw_host is None:
        raise CanonicalizationError("URL has no host")

    host, is_ip = _canonical_host(raw_host)

    try:
        port = split.port
    except ValueError as exc:
        raise CanonicalizationError(f"invalid port: {exc}") from exc
    if port is not None and DEFAULT_PORTS.get(scheme) == port:
        port = None

    path = split.path or "/"
    return CanonicalUrl(scheme=scheme, host=host, port=port, path=path, is_ip=is_ip)


def host_matches(canonical_host: str, declared: str, *, include_subdomains: bool) -> bool:
    """Does a canonical host match a declared one?

    `include_subdomains` is explicit rather than implied, because the two readings
    disagree exactly where an attacker lives: `bank.example.com.evil.test` is a
    subdomain of `evil.test` and shares a *prefix* with `bank.example.com`. Suffix
    matching without a label boundary is the classic bypass, so the boundary is
    enforced rather than assumed.
    """
    declared_canon, _ = _canonical_host(declared)
    if canonical_host == declared_canon:
        return True
    if not include_subdomains:
        return False
    return canonical_host.endswith("." + declared_canon)
