"""RFC 7638 JWK thumbprint for an Ed25519 (OKP) key, and nothing else.

Only the one key type this package ever issues or verifies (profile §3.1: EdDSA
over Ed25519). The thumbprint is computed over the REQUIRED members for an OKP key
(RFC 8037 §2: `crv`, `kty`, `x`), which happen to already be in RFC 7638's required
lexicographic order (`crv` < `kty` < `x`), so no separate ordering step is needed.
"""

from __future__ import annotations

import base64
import hashlib
import json


def thumbprint(public_key_bytes: bytes) -> str:
    """The `jkt` value (profile §3.2's `cnf.jkt`) for a raw 32-byte Ed25519 public key."""
    if len(public_key_bytes) != 32:
        raise ValueError(f"an Ed25519 public key is 32 bytes, got {len(public_key_bytes)}")
    jwk = {
        "crv": "Ed25519",
        "kty": "OKP",
        "x": base64.urlsafe_b64encode(public_key_bytes).rstrip(b"=").decode("ascii"),
    }
    canonical = json.dumps(jwk, sort_keys=True, separators=(",", ":")).encode("ascii")
    digest = hashlib.sha256(canonical).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
