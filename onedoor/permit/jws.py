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
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + padding)
    except (ValueError, TypeError) as exc:
        raise MalformedJWS(f"not valid base64url: {exc}") from exc


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
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
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
    return header, payload
