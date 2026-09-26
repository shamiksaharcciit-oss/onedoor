"""JWS compact serialization (RFC 7515), EdDSA/Ed25519 only.

Built directly on the `cryptography` package already vendored for onedoor's own
row signing (`onedoor.guardrail.signing`), rather than adding a JWT/JOSE library:
a bound permit uses exactly one algorithm (EdDSA over Ed25519, profile §3.1) and
exactly one serialization (compact), so the general-purpose surface a JOSE library
carries -- other algorithms, JWE, JWK parsing, key rotation policies -- is not
surface this package needs to trust. Base64url without padding, per RFC 7515 §2.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any


class MalformedJWS(ValueError):
    """The token is not a well-formed three-part compact JWS."""


class SignatureInvalid(ValueError):
    """The token parses, but the signature does not verify under the given key."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """Base64url without padding (RFC 7515 §2), and canonical: the decoded bytes,
    re-encoded, must reproduce `text` exactly.

    Python's own decoder is lenient in three ways RFC 4648 does not require a
    decoder to accept: it takes padding characters even though this format never
    carries any, it accepts the standard `+`/`/` alphabet as well as the
    URL-safe one, and it does not check that the unused bits in the last symbol
    of a non-4-aligned group are zero -- so several different strings can decode
    to the same bytes. Re-encoding and comparing closes all three at once: the
    canonical form of any given bytes is unique, so a text that is not already
    that canonical form is rejected rather than silently accepted as one of
    several spellings of the same permit.
    """
    if "=" in text:
        raise MalformedJWS(
            f"base64url segment carries padding, which compact JWS forbids: {text!r}"
        )
    padding = "=" * (-len(text) % 4)
    try:
        decoded = base64.urlsafe_b64decode(text + padding)
    except (ValueError, TypeError) as exc:
        raise MalformedJWS(f"not valid base64url: {exc}") from exc
    if _b64url_encode(decoded) != text:
        raise MalformedJWS(f"not canonical base64url (non-minimal encoding): {text!r}")
    return decoded


def _reject_non_finite(constant: str) -> float:
    """`json.loads`'s `parse_constant`: refuse `NaN`, `Infinity` and `-Infinity`
    anywhere in the header or payload, rather than the float `json.loads`
    otherwise silently produces for them (a non-standard extension to JSON that
    Python's decoder accepts by default).

    Not merely a defensive nicety for the two numeric claims this package
    itself compares (`onedoor.permit.recipient`'s own `_as_int` already refuses
    a non-integer there): a non-finite value anywhere else in the payload --
    inside `authorization_details`, `cnf`, `mandate`, anywhere -- is exactly
    the same hazard, and this refuses it at the one place untrusted JSON text
    enters this package rather than trusting every future reader of a claim to
    re-derive the same defence.
    """
    raise MalformedJWS(f"non-finite numeric constant not allowed in JSON: {constant}")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """`json.loads`'s `object_pairs_hook`: refuse a JSON object that names the
    same key twice, rather than silently keeping the last value the way
    `json.loads` does by default.

    A duplicate key is a genuine parser-ambiguity hazard, not merely untidy
    input: different JSON parsers resolve a duplicate differently (first wins,
    last wins, or reject), so a header or payload that relies on the reader's
    particular choice is not something this codec's own signature can be said
    to cover unambiguously. Refused here, at the one place untrusted JSON text
    enters this package, rather than normalised.
    """
    seen: set[str] = set()
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in seen:
            raise MalformedJWS(f"duplicate object key: {key!r}")
        seen.add(key)
        result[key] = value
    return result


def encode(header: Mapping[str, object], payload: Mapping[str, object], private_key: Any) -> str:
    """Sign `payload` under `header` with an Ed25519 private key, compact form.

    `private_key` is typed `Any` on purpose: this module never imports
    `cryptography` at module scope (only inside `verify`, to keep the happy-path
    import light), so it cannot name `Ed25519PrivateKey` as a type here. The
    contract is duck-typed -- anything with a `.sign(bytes) -> bytes` method that
    behaves like an Ed25519 private key.
    """
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature: bytes = private_key.sign(signing_input)
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def parse(token: str) -> tuple[dict[str, object], dict[str, object], bytes, bytes]:
    """Split and JSON-decode a compact JWS, without verifying the signature.

    Returns `(header, payload, signing_input, signature)`. Raises `MalformedJWS`
    for anything that is not a well-formed three-part token with two JSON objects
    -- never a bare `IndexError`/`JSONDecodeError`, so a caller's `except
    MalformedJWS` catches every shape of bad input.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise MalformedJWS(f"expected 3 dot-separated parts, got {len(parts)}")
    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(
            _b64url_decode(header_b64),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
        payload = json.loads(
            _b64url_decode(payload_b64),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except json.JSONDecodeError as exc:
        raise MalformedJWS(f"header or payload is not valid JSON: {exc}") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise MalformedJWS("header and payload must both be JSON objects")
    signature = _b64url_decode(signature_b64)
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    return header, payload, signing_input, signature


def verify(token: str, public_key_bytes: bytes) -> tuple[dict[str, object], dict[str, object]]:
    """Parse and verify a compact JWS under a raw 32-byte Ed25519 public key.

    Raises `MalformedJWS` for a structurally bad token and `SignatureInvalid` for
    one that parses but does not verify -- two different failure modes, on
    purpose: a recipient's `malformed` check (profile §8.1 step 1) and its
    `signature-invalid` check (step 2) are different steps in a fixed order, and
    collapsing them here would make the caller re-derive which one fired.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519

    header, payload, signing_input, signature = parse(token)
    try:
        key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        key.verify(signature, signing_input)
    except InvalidSignature as exc:
        raise SignatureInvalid("the signature does not verify under the given key") from exc
    except (ValueError, TypeError) as exc:
        # `from_public_bytes` raises for anything that is not exactly 32 bytes
        # (the wrong key type or curve behind the caller's key material) --
        # this is a signature-invalid outcome too, not a crash a caller of this
        # public function should have to guard against separately.
        raise SignatureInvalid(f"public key is not a usable Ed25519 key: {exc}") from exc
    return header, payload
