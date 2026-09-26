"""JSON Canonicalization Scheme (RFC 8785), restricted to the grammar a bound
permit's action object actually uses.

Full JCS's genuinely hard problem is serializing a JSON **number** exactly as
ECMAScript's `Number::toString` would (RFC 8785 §3.2.2.3, via ECMA-262). Onedoor
never needs that: every action object this package builds or verifies carries
amounts and other precision-sensitive values as decimal **strings** (the same rule
AADP already applies wherever a monetary value appears), never as a bare JSON
number. So this module implements RFC 8785 exactly for the subset it needs --
object, array, string, integer, boolean, null -- and refuses a float outright
rather than silently rendering one, the same discipline the rest of this codebase
already applies to every other canonical form it writes.

Object property ordering (RFC 8785 §3.2.3) is by the UTF-16 code unit sequence of
the property name. Python's default string ordering coincides with that for every
name in the Basic Multilingual Plane (the overwhelmingly common case -- ASCII field
names like "type", "amount", "currency"). It does **not** coincide for names
containing characters outside the BMP (surrogate pairs sort differently under
UTF-16 code units than under Unicode code points): this module does not implement
that case and raises rather than silently produce non-conformant bytes for it.
"""

from __future__ import annotations

import json

DOMAIN_TAG = b"aadp:action:v1"
"""bound-permit profile §4.3's domain tag, prefixed before the JCS bytes."""


class NotCanonicalizable(TypeError):
    """A value this restricted JCS implementation does not (yet) handle."""


def _check_bmp_only(key: str) -> None:
    if any(ord(ch) > 0xFFFF for ch in key):
        raise NotCanonicalizable(
            f"object key {key!r} contains a character outside the Basic "
            f"Multilingual Plane; this module's key ordering does not implement "
            f"RFC 8785's UTF-16-code-unit rule for surrogate pairs"
        )


def _check_no_lone_surrogates(value: str) -> None:
    """A lone surrogate (U+D800-U+DFFF not part of a valid pair) is not valid
    Unicode text and cannot be encoded to UTF-8 -- `json.loads` will still
    happily *produce* one from a `\\uD800`-style escape with no partner, since
    JSON's own grammar does not forbid it. Left unchecked, `canonical_bytes`'s
    own `.encode("utf-8")` raises a raw `UnicodeEncodeError` instead of this
    module's own `NotCanonicalizable` -- a caller catching the latter (as
    `onedoor.permit.recipient` does at its own action-digest step) would not
    catch the former, and a value that should refuse cleanly crashes instead.
    Checked here, at the point the lone surrogate is first seen, not left for
    the encoder several calls later to discover.
    """
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise NotCanonicalizable(
            f"{value!r} contains a lone UTF-16 surrogate, which is not valid "
            f"Unicode text and cannot be canonicalized"
        )


def _canon(value: object) -> object:
    if isinstance(value, bool):  # before int: bool is an int subclass
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        _check_no_lone_surrogates(value)
        return value
    if value is None:
        return None
    if isinstance(value, float):
        raise NotCanonicalizable(
            f"a float ({value!r}) reached the bound-permit action object; RFC "
            f"8785's number serialization is not implemented here on purpose -- "
            f"represent it as a decimal string instead"
        )
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise NotCanonicalizable(f"non-string object key: {k!r}")
            _check_bmp_only(k)
            _check_no_lone_surrogates(k)
            out[k] = _canon(v)
        return dict(sorted(out.items()))
    if isinstance(value, list):
        return [_canon(v) for v in value]
    raise NotCanonicalizable(
        f"type not allowed in a bound-permit action object: {type(value).__name__}"
    )


def canonical_bytes(value: object) -> bytes:
    """The RFC 8785 canonical JSON bytes for `value`, restricted as documented above."""
    canon = _canon(value)
    return json.dumps(canon, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
