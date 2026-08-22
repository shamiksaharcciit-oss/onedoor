"""Ed25519 signatures over `row_hash`, and the keyring that makes them checkable (ND-015).

A receipt system must not be its own witness
--------------------------------------------
That sentence (R038 §1) is the whole reason this module has five outcomes rather than
three. A signature checked against a public key found in **the same store as the data
it signs** proves internal consistency and nothing else: an attacker who can write the
database adds their own public key, re-signs what they altered, and hands you a store
that verifies perfectly against itself. The append-only triggers do not close it — they
stop `UPDATE` and `DELETE`, and a keyring must accept `INSERT`s or rotation is
impossible. The chain does not close it either: a keyring row is not an `actions_audit`
row and is not chained.

So `verified` **requires a trust anchor from outside the store** — an expected `key_id`
the caller supplies. But the in-store match is real information, and throwing it away
would be dishonest in the other direction, so it gets its own name:

``verified``        the signature checks against a key the CALLER vouched for
``self_consistent`` it matches this store's own keyring — real, and not the same thing
``unverifiable``    the key is unknown here: the signature may be perfectly good
``failed``          the bytes do not verify
``absent``          no signature; signing was not in operation

Custody (R037 §2), none of it negotiable here
---------------------------------------------
The **private key is deployer-supplied** and never enters the repo, the database, or any
receipt. `key_id` is **derived** — a fingerprint of the public key bytes — never
assigned, because a label someone chooses can drift from what it names and a digest
cannot. Rotation is **append-only**: a new key gets a new derived id and old receipts
verify forever under the old public key, because public keys are evidence and evidence
is not deleted.

X-6 at enable time (R038 §2)
----------------------------
`cryptography` is a `[signed]` extra, not a hard install requirement — a library-only
user who never signs should not carry it. The failure mode that matters is a deployment
that *believes* it signs and does not, and a hard install dependency does nothing about
that, because belief comes from config. So: **signing configured plus library missing
means the process refuses to start.** Loud, immediate, and no stream of unsigned rows.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from onedoor.store.clock import to_iso

ALGORITHM = "ed25519"
"""What goes in the `alg` column: the ALGORITHM, never the library (R038 §3).

Ed25519 is output-deterministic per RFC 8032 — a correct implementation produces
identical bytes forever — so a library version in per-row evidence would assert an
output dependence that does not exist, and a misleading identity in a receipt is worse
than none. The library and its pinned version are recorded once at the deployment
layer, where a hypothetical defect would be traced by deployment rather than per row.
"""

KEY_ID_PREFIX = "ed25519:"
"""Namespaces the fingerprint, so a `key_id` says what kind of key it names."""

SIGNING_KEY_ENV = "ONEDOOR_SIGNING_KEY_PATH"
"""Where the deployer says their private key lives. A path, never the key itself, and
never a value this repository or this database has seen."""


class SigningUnavailable(RuntimeError):
    """Signing is configured and the library is not installed.

    Raised at startup, deliberately fatal (R038 §2). The alternative -- carrying on and
    writing unsigned rows -- is the failure this whole ticket is defending against: a
    deployment that believes it is signing and is not.
    """


class KeyringError(RuntimeError):
    """The keyring could not be read or extended."""


def _backend() -> Any:
    """Import the Ed25519 primitives, or say precisely why they are missing."""
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:  # pragma: no cover - exercised via require_available
        raise SigningUnavailable(
            "signing is configured but the `cryptography` package is not installed. "
            "Install onedoor's `signed` extra (`pip install 'onedoor[signed]'`) or turn "
            "signing off. Refusing to start rather than write unsigned rows."
        ) from exc
    return ed25519


def _serialization() -> Any:
    """The key-loading primitives, behind the same guard as the curve ones.

    Behind the guard rather than beside it: an earlier version imported this at the top
    of `load_private_key` and the raw `ImportError` escaped before `_backend()` could
    turn it into the fatal, explanatory `SigningUnavailable`. Found by the
    library-missing test, which is the test earning its keep -- a deployment hitting
    that path would have seen a bare import error instead of the sentence telling it
    what to install.
    """
    try:
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:
        raise SigningUnavailable(
            "signing is configured but the `cryptography` package is not installed. "
            "Install onedoor's `signed` extra (`pip install 'onedoor[signed]'`) or turn "
            "signing off. Refusing to start rather than write unsigned rows."
        ) from exc
    return serialization


def available() -> bool:
    """Is the signing library importable? A question, not an assertion."""
    try:
        _backend()
    except SigningUnavailable:
        return False
    return True


def require_available() -> None:
    """The enable-time gate. Call this wherever signing is switched on."""
    _backend()


def key_id_for(public_bytes: bytes) -> str:
    """Derive a `key_id` from the public key. Never assigned, always derived.

    A fingerprint cannot drift from what it names; a chosen label can. The same
    content-addressing argument as everything else in this epic, at the key layer.
    """
    return KEY_ID_PREFIX + hashlib.sha256(public_bytes).hexdigest()


@dataclass(frozen=True)
class SigningKey:
    """A loaded private key and the identity derived from its public half."""

    key_id: str
    _private: Any

    def sign(self, row_hash: str) -> str:
        """Sign one row's hash. The signature attests the sealed bytes and nothing else."""
        signature: bytes = self._private.sign(row_hash.encode("ascii"))
        return signature.hex()


def load_private_key(path: str) -> SigningKey:
    """Load a deployer-supplied Ed25519 private key from a PEM file.

    The key material stays in the process. It is never written to the database, never
    put in a receipt, and never logged -- `SigningKey` carries the derived id for
    evidence and the key object for use.
    """
    serialization = _serialization()
    _backend()
    try:
        with open(path, "rb") as handle:
            private = serialization.load_pem_private_key(handle.read(), password=None)
    except OSError as exc:
        raise SigningUnavailable(f"the configured signing key is unreadable: {exc}") from exc

    public_bytes: bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return SigningKey(key_id=key_id_for(public_bytes), _private=private)


def public_bytes_of(key: SigningKey) -> bytes:
    serialization = _serialization()
    raw: bytes = key._private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return raw


# --- The keyring ------------------------------------------------------------------


def register_public_key(
    conn: sqlite3.Connection, public_bytes: bytes, now: datetime, *, note: str = ""
) -> str:
    """Add a public key to the keyring. Append-only: rotation grows the ring.

    Returns the derived `key_id`. Re-registering the same key is a no-op rather than an
    error -- the ring is a set of facts, and asserting a fact twice does not make it
    two facts.

    **Public keys are evidence**, so nothing here deletes or replaces. A rotated-out key
    stays, because the receipts it signed must verify forever.
    """
    key_id = key_id_for(public_bytes)
    conn.execute(
        "INSERT INTO signing_keys (key_id, public_key, alg, registered_at, note) "
        "VALUES (?,?,?,?,?) ON CONFLICT(key_id) DO NOTHING",
        (key_id, public_bytes, ALGORITHM, to_iso(now), note),
    )
    return key_id


def keyring(conn: sqlite3.Connection) -> dict[str, bytes]:
    """Every public key this store knows, by derived id."""
    return {
        str(r["key_id"]): bytes(r["public_key"])
        for r in conn.execute("SELECT key_id, public_key FROM signing_keys").fetchall()
    }


def verify_signature(public_bytes: bytes, row_hash: str, signature_hex: str) -> bool:
    """Does this signature check out against this public key? A bad signature is False.

    Never raises on a bad signature: a verifier that throws cannot be run against a
    suspect archive, which is the only archive worth running one against.
    """
    ed25519 = _backend()
    try:
        public = ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)
        public.verify(bytes.fromhex(signature_hex), row_hash.encode("ascii"))
    except Exception:  # noqa: BLE001 - any verification failure is a False, not a crash
        return False
    return True
