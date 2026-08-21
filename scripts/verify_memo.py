#!/usr/bin/env python3
r"""Verify the integrity footer on a core memo.

Core memos carry an integrity footer from Response 008 onward. The preimage was
ratified by Response 009 and is implemented here exactly as written, because a
digest whose preimage each side guesses at is verifiable only by luck -- the third
instance of that class in this programme, after E8 decimals and Q-11 uids:

    body = every byte of the file strictly before the FINAL line beginning
           `Integrity:`, with all trailing whitespace (including newlines)
           stripped, followed by exactly one LF (0x0A). Bytes as stored, UTF-8.
           Digest is SHA-256 over body, lowercase hex.

Usage:

    python -m scripts.verify_memo docs/from_core/*.md

Exit 0 if every memo carrying a footer verifies; 1 otherwise.

Two traps, both walked into rather than foreseen, both now regression-tested:

1. FINAL line, not first match. Response 008 quotes its own footer format in its
   prose, so the marker occurs twice in that file. A first-match parser truncates
   body at the quotation and reports a mismatch indistinguishable from relay
   corruption -- the worst diagnostic shape available. Response 009 amended the
   definition to say FINAL for this reason.
2. A malformed footer is a FAILURE, never a skip. An earlier version of this script
   matched the footer with a regex anchored on `
...\Z`, so a CRLF-corrupted memo
   did not match, fell through to "no footer", and was reported as predating the
   protocol -- a silent pass on exactly the corruption the footer exists to catch.
   Absence of the marker means "predates the protocol"; presence of a marker that
   does not verify means "damaged", and the two must never collapse.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

MARKER = b"Integrity:"
PREFIX = b"Integrity: sha256(body) = "


class Result:
    """Outcome of one memo check. Falsy only when the memo is damaged."""

    def __init__(self, status: str, detail: str = "") -> None:
        self.status = status  # "ok" | "damaged" | "no-footer"
        self.detail = detail

    def __bool__(self) -> bool:
        return self.status != "damaged"


def _final_footer_start(raw: bytes) -> int | None:
    """Offset of the FINAL line beginning `Integrity:`, or None if there is none."""
    best = None
    start = 0
    while (i := raw.find(MARKER, start)) != -1:
        if i == 0 or raw[i - 1 : i] == b"\n":  # must begin a line
            best = i
        start = i + 1
    return best


def preimage(raw: bytes, footer_start: int) -> bytes:
    """Response 009's ratified preimage. Strips ALL trailing whitespace, not just LF."""
    return raw[:footer_start].rstrip() + b"\n"


def verify(path: Path) -> Result:
    raw = path.read_bytes()
    start = _final_footer_start(raw)
    if start is None:
        return Result("no-footer")
    footer = raw[start:].rstrip(b"\r\n")
    if not footer.startswith(PREFIX):
        return Result("damaged", "footer line is malformed")
    claimed = footer[len(PREFIX) :]
    if len(claimed) != 64 or not all(c in b"0123456789abcdef" for c in claimed):
        return Result("damaged", "claimed digest is not 64 lowercase hex chars")
    actual = hashlib.sha256(preimage(raw, start)).hexdigest()
    if actual != claimed.decode():
        hint = ""
        if b"\r\n" in raw:
            hint = " -- file contains CRLF; check .gitattributes and core.autocrlf BEFORE suspecting core"
        return Result("damaged", f"claimed {claimed.decode()[:12]}..., got {actual[:12]}...{hint}")
    return Result("ok")


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print(__doc__)
        return 2
    failed = False
    for path in sorted(paths):
        result = verify(path)
        if result.status == "no-footer":
            print(f"  --   {path.name}  (no integrity footer; predates the protocol)")
        elif result.status == "ok":
            print(f"  OK   {path.name}")
        else:
            failed = True
            print(f"  FAIL {path.name}  {result.detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
