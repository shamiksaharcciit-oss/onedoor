"""The action object and its digest (bound-permit profile §4.3)."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping

from onedoor.permit import jcs


def action_digest(action_object: Mapping[str, object]) -> str:
    """`"sha-256=:" || BASE64(SHA256(domain_tag || 0x00 || JCS(A))) || ":"`.

    The domain tag separates this digest from every other digest that might be
    taken over the same JSON object -- the same reason every other digest in this
    codebase carries one. `A` must already be a JSON object (profile §4.3); this
    function does not derive A from a request, since that derivation is specific
    to each registered action type.
    """
    if not isinstance(action_object, dict):
        raise TypeError("the action object A must be a JSON object (profile §4.3)")
    body = jcs.DOMAIN_TAG + b"\x00" + jcs.canonical_bytes(action_object)
    digest = hashlib.sha256(body).digest()
    return "sha-256=:" + base64.b64encode(digest).decode("ascii") + ":"
