"""HTTP Message Signatures (RFC 9421), scoped to the fixed component set the
bound-permit profile requires (§4.2): `@method`, `@authority`, `@path`, `@query`,
`content-digest`, `idempotency-key`, `aadp-permit`.

Not a general RFC 9421 library. It implements exactly the signature-base
construction and the `Signature-Input`/`Signature` field serialization needed for
one signature, over one fixed, known component list, with EdDSA/Ed25519 -- the
same "cite the RFC, implement the part this codebase actually needs, disclose the
restriction" discipline `jcs.py` and `jws.py` both follow. A deployment that needs
additional covered components, multiple signatures, or another algorithm needs a
fuller implementation than this one.

Component values, per RFC 9421 §2.2, quoted here so the citation is checkable:
`@method` is the request method as a string; `@authority` is the request's
authority, lowercased, default port omitted; `@path` is the absolute path with no
query; `@query` is the entire normalized query string **including the leading
`?`** (an empty query string is just `?`, RFC 9421 §2.2.7's own worked example).
"""

from __future__ import annotations

from typing import Any

SIGNATURE_LABEL = "sig1"

COVERED_COMPONENTS: tuple[str, ...] = (
    "@method",
    "@authority",
    "@path",
    "@query",
    "content-digest",
    "idempotency-key",
    "aadp-permit",
)
"""bound-permit profile §4.2's minimum covered-component list, in signing order."""


def _sf_string(value: str) -> str:
    """RFC 8941 `sf-string`: quoted, with `\\` and `"` escaped. No control chars
    or non-ASCII are expected in any value this module quotes (component names,
    `keyid`, `alg`); a value carrying one is rejected rather than mis-serialized.
    """
    if any(ord(ch) < 0x20 or ord(ch) > 0x7E for ch in value):
        raise ValueError(f"value is not a valid RFC 8941 sf-string: {value!r}")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def extract_keyid(signature_input_header: str) -> str | None:
    """The `keyid` parameter as the presenter's own `Signature-Input` claims it,
    read directly from the raw header -- independent of, and prior to, the full
    recomputed comparison `verify` performs, and prior to any cryptography.

    Used to tell apart the two ways a presented signature can fail to bind to
    `cnf.jkt` (profile V09): a signature that honestly names a different key is
    `presenter-key-mismatch`, checked here before any key resolution or
    verification is attempted; a signature that claims `cnf.jkt` but does not
    verify under it is `request-signature-invalid`, which only `verify` itself
    can determine. Returns `None` if no `keyid` parameter can be found at all,
    which the caller treats as `binding-incomplete` -- structurally different
    from a keyid that IS present and simply wrong.

    A small hand-written scanner, not a regex: it reverses exactly the escaping
    `_sf_string` applies (`\\` and `"` only), character by character, so it
    cannot be confused by a crafted value that embeds extra quotes or
    backslashes into looking like more than one parameter.
    """
    marker = 'keyid="'
    start = signature_input_header.find(marker)
    if start == -1:
        return None
    i = start + len(marker)
    text = signature_input_header
    result: list[str] = []
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            result.append(text[i + 1])
            i += 2
            continue
        if ch == '"':
            return "".join(result)
        result.append(ch)
        i += 1
    return None  # unterminated quoted string


def signature_params_value(*, created: int, keyid: str, alg: str = "ed25519") -> str:
    """The `@signature-params` value: an RFC 8941 Inner List of the covered
    component identifiers, followed by this signature's parameters."""
    items = " ".join(_sf_string(name) for name in COVERED_COMPONENTS)
    params = f";created={int(created)};keyid={_sf_string(keyid)};alg={_sf_string(alg)}"
    return f"({items}){params}"


def signature_base(
    components: dict[str, str], *, created: int, keyid: str, alg: str = "ed25519"
) -> str:
    """The bytes that get signed (RFC 9421 §2.5), as text -- one line per covered
    component (`"<name>": <value>`), then the `"@signature-params"` line, joined
    by LF with no trailing newline.
    """
    missing = [name for name in COVERED_COMPONENTS if name not in components]
    if missing:
        raise KeyError(f"missing covered component value(s): {missing}")
    lines = [f"{_sf_string(name)}: {components[name]}" for name in COVERED_COMPONENTS]
    lines.append(
        f'"@signature-params": {signature_params_value(created=created, keyid=keyid, alg=alg)}'
    )
    return "\n".join(lines)


def sign(
    components: dict[str, str], *, created: int, keyid: str, private_key: Any
) -> tuple[str, str]:
    """Returns `(signature_input_header_value, signature_header_value)`.

    `private_key` is `Any`, duck-typed the same way `jws.encode`'s is: anything
    with a `.sign(bytes) -> bytes` method, without this module importing
    `cryptography` just to name the type.
    """
    base = signature_base(components, created=created, keyid=keyid)
    signature: bytes = private_key.sign(base.encode("ascii"))
    import base64

    sig_input = f"{SIGNATURE_LABEL}={signature_params_value(created=created, keyid=keyid)}"
    sig_value = f"{SIGNATURE_LABEL}=:{base64.b64encode(signature).decode('ascii')}:"
    return sig_input, sig_value


class SignatureVerificationError(ValueError):
    """The HTTP message signature is missing, malformed, or does not verify."""


def verify(
    components: dict[str, str],
    *,
    created: int,
    keyid: str,
    signature_input_header: str,
    signature_header: str,
    public_key_bytes: bytes,
) -> None:
    """Raises `SignatureVerificationError` on any failure; returns `None` on success.

    Recomputes the expected `Signature-Input` value from the caller's own
    `components`/`created`/`keyid` (never trusts the header's own claimed
    covered-component list) and checks the presented header matches it exactly --
    a presenter cannot shrink the covered-component set by sending a
    `Signature-Input` that omits one, since the recipient's own expectation is
    what gets verified.
    """
    import base64

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519

    expected_input = f"{SIGNATURE_LABEL}={signature_params_value(created=created, keyid=keyid)}"
    if signature_input_header.strip() != expected_input:
        raise SignatureVerificationError(
            "Signature-Input does not match the expected covered components/parameters "
            f"(binding-incomplete): expected {expected_input!r}, got "
            f"{signature_input_header.strip()!r}"
        )
    prefix = f"{SIGNATURE_LABEL}=:"
    header = signature_header.strip()
    if not (header.startswith(prefix) and header.endswith(":")):
        raise SignatureVerificationError("Signature header is not a well-formed byte sequence")
    try:
        signature = base64.b64decode(header[len(prefix) : -1])
    except (ValueError, TypeError) as exc:
        raise SignatureVerificationError(f"Signature header is not valid base64: {exc}") from exc

    base = signature_base(components, created=created, keyid=keyid)
    try:
        key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
        key.verify(signature, base.encode("ascii"))
    except InvalidSignature as exc:
        raise SignatureVerificationError(
            "the signature does not verify under the given key"
        ) from exc
