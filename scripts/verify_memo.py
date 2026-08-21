#!/usr/bin/env python3
"""Verify the integrity footer on a core memo.

Core memos carry `Integrity: sha256(body) = <hex>` as their final line from
Response 008 onward, where `body` is every byte of the file above that line. Relay
has damaged two memos already (UTF-8 decoded as cp1252 with the C1 continuation
bytes discarded), and before the footer existed the only way to notice was to read
the mojibake and judge whether a given sequence had "probably" been an arrow. This
makes it a command.

    python -m scripts.verify_memo docs/from_core/*.md

Exit 0 if every memo with a footer verifies; 1 otherwise. Memos predating the
protocol (001-006) carry no footer and are reported as such, not failed.

One parsing trap, learned by walking into it: Response 008 *quotes its own footer
format* in its prose, so the marker occurs twice in that file. Anchor on the final
line, never on the first match, or the body is truncated at the quotation and the
digest disagrees for a reason that has nothing to do with relay.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

FOOTER = re.compile(rb"\nIntegrity: sha256\(body\) = ([0-9a-f]{64})\n?\Z")


def body_digest(raw: bytes, footer_start: int) -> str:
    """The digest core computes: bytes above the footer, one trailing newline."""
    return hashlib.sha256(raw[:footer_start].rstrip(b"\n") + b"\n").hexdigest()


def verify(path: Path) -> bool | None:
    """True/False if a footer is present and (in)valid; None if absent."""
    raw = path.read_bytes()
    match = FOOTER.search(raw)
    if match is None:
        return None
    return body_digest(raw, match.start()) == match.group(1).decode()


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        print(__doc__)
        return 2
    failed = False
    for path in sorted(paths):
        result = verify(path)
        if result is None:
            print(f"  --   {path.name}  (no integrity footer; predates the protocol)")
        elif result:
            print(f"  OK   {path.name}")
        else:
            failed = True
            print(f"  FAIL {path.name}  <-- body does not match its claimed digest")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
