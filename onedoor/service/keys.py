"""Keyed fingerprints of API keys: what the service records to tell keys apart.

A fingerprint is HMAC-SHA-256 of the key under a server-side secret, cut to 16 hex
characters and prefixed ``key-hmac:``. It identifies a key without disclosing any part
of it, and without the secret it cannot be checked against guesses -- which matters,
because nothing makes an operator choose a long key.

The secret is ``ONEDOOR_KEY_FINGERPRINT_SECRET`` when that is set. Otherwise one is
generated once and kept in a file beside the database, never inside it (other
processes, such as the Studio, read the database), so a key keeps its fingerprint
across restarts.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path

SECRET_ENV = "ONEDOOR_KEY_FINGERPRINT_SECRET"
SECRET_FILE_SUFFIX = ".key-fingerprint"
PREFIX = "key-hmac:"


def load_secret(db_path: str) -> bytes:
    """The fingerprint secret for the store at `db_path`, created on first use."""
    configured = os.environ.get(SECRET_ENV)
    if configured:
        return configured.encode("utf-8")
    if db_path == ":memory:":
        return secrets.token_bytes(32)
    path = Path(db_path + SECRET_FILE_SUFFIX)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        stored = path.read_text(encoding="utf-8").strip()
        if not stored:
            raise RuntimeError(f"the key fingerprint secret file {path} is empty") from None
        return stored.encode("utf-8")
    value = secrets.token_hex(32)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value + "\n")
    return value.encode("utf-8")


def fingerprint(key: str, secret: bytes) -> str:
    digest = hmac.new(secret, key.encode("utf-8"), hashlib.sha256).hexdigest()
    return PREFIX + digest[:16]
