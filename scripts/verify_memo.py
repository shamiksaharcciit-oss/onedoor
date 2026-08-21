#!/usr/bin/env python3
r"""Verify the integrity footer on a core memo.

Core memos carry an integrity footer from Response 008 onward. The preimage was
ratified by Response 009 and is implemented here exactly as written, because a
digest whose preimage each side guesses at is verifiable only by luck -- the third
instance of that class in this programme, after E8 decimals and Q-11 uids:

    body = every byte of the file strictly before THE line beginning `Integrity:`,
           with all trailing whitespace (including newlines) stripped, followed by
           exactly one LF (0x0A). Bytes as stored, UTF-8. SHA-256, lowercase hex.

    Exactly one line of a memo may begin with `Integrity:` -- a producer obligation
    (quotations are indented or kept mid-line). A verifier encountering more than one
    such line MUST reject the file as malformed.

Usage:

    python -m scripts.verify_memo docs/from_core/*.md

Exit 0 if every memo carrying a footer verifies; 1 otherwise.

Two traps, both walked into rather than foreseen, both now regression-tested:

1. FINAL line, not first match. Response 008 quotes its own footer format in its
   prose, so the marker occurs twice in that file. A first-match parser truncates
   body at the quotation and reports a mismatch indistinguishable from relay
   corruption -- the worst diagnostic shape available. Response 009 amended the
   definition to say FINAL for this reason.
2. Two marker lines is MALFORMED, not a tie to break. Response 009 amended the
   definition to anchor on the FINAL such line; Response 010 superseded that, because
   the forensics session's independent verifier *raised* on two markers instead. Two
   checkers disagreeing on the same file is the E005 defect class reproduced inside
   the memo protocol -- a receipt "verified" by one and invalid to the other. The
   grounding was already ours: ACJ rules duplicate keys `malformed`, never
   last-one-wins. Silently resolving an ambiguity the definition exists to close is
   the move this programme forbids everywhere else, and final-line anchoring was that
   move. Mid-line quotations are fine and Response 008 depends on it.
3. A malformed footer is a FAILURE, never a skip. An earlier version of this script
   matched the footer with a regex anchored on `\n...\Z`, so a CRLF-corrupted memo
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


def _marker_lines(raw: bytes) -> list[int]:
    """Offsets of every line beginning `Integrity:`. Mid-line occurrences do not count."""
    out = []
    start = 0
    while (i := raw.find(MARKER, start)) != -1:
        if i == 0 or raw[i - 1 : i] == b"\n":  # must begin a line
            out.append(i)
        start = i + 1
    return out


def preimage(raw: bytes, footer_start: int) -> bytes:
    """Response 009's ratified preimage. Strips ALL trailing whitespace, not just LF."""
    return raw[:footer_start].rstrip() + b"\n"


def verify(path: Path) -> Result:
    raw = path.read_bytes()
    starts = _marker_lines(raw)
    if not starts:
        return Result("no-footer")
    if len(starts) > 1:
        return Result(
            "damaged",
            f"{len(starts)} lines begin with `Integrity:`; exactly one is permitted. "
            f"Ambiguity is surfaced, never resolved (Response 010).",
        )
    start = starts[0]
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


BEGIN_MARK = "<!-- BEGIN GENERATED digests"
END_MARK = "<!-- END GENERATED digests -->"
# Files in the archive directory that are OURS, not received. Excluded by NAME,
# per Forward 001 -- and shared with tests/protocol/ so the generator and the
# checker cannot drift apart about what counts as a memo.
GENERATED_FILES = frozenset({"INTEGRITY.md"})


def digest_of(path: Path) -> str | None:
    """The recorded identity of a memo: its verified body digest, or None."""
    raw = path.read_bytes()
    starts = _marker_lines(raw)
    if len(starts) != 1 or verify(path).status != "ok":
        return None
    return hashlib.sha256(preimage(raw, starts[0])).hexdigest()


def table(paths: list[Path]) -> str:
    """Emit the ledger's digest rows.

    R012: *a digest in a ledger is generated, never transcribed.* Any recorded
    digest must be emitted into its cell by the verifier that computes it -- a
    hand-copied digest is a claim with no guard, and it will drift while staying
    green. So this function, not a human, writes those cells.

    Full 64 hex characters, never truncated: an elided digest is a transcription
    hazard of its own, and the ellipsis is where the two registers got mixed.
    """
    rows = ["| Memo | Body digest (`Integrity:` register) |", "|---|---|"]
    for path in sorted(paths):
        if path.name in GENERATED_FILES:
            continue
        d = digest_of(path)
        # ASCII only. A generated cell that has to survive a round trip is the last
        # place to put a character an encoding can eat.
        cell = f"`{d}`" if d else "none (predates the footer)"
        rows.append(f"| `{path.name}` | {cell} |")
    return "\n".join(rows) + "\n"


def render_block(paths: list[Path]) -> str:
    cmd = "python -m scripts.verify_memo --table docs/from_core/*.md"
    return f"{BEGIN_MARK}: {cmd} -->\n{table(paths)}{END_MARK}"


def write_block(ledger: Path, paths: list[Path]) -> bool:
    """Rewrite the generated block in place. Returns True if anything changed.

    The register has to be regenerated every time a memo is archived, and a step
    that is done by hand is a step that will eventually be done by hand *wrongly* --
    which is the whole of R012. So it is a command, not a habit.
    """
    text = ledger.read_text(encoding="utf-8")
    start, end = text.find(BEGIN_MARK), text.find(END_MARK)
    if start == -1 or end == -1:
        raise SystemExit(f"{ledger}: generated block markers not found")
    updated = text[:start] + render_block(paths) + text[end + len(END_MARK) :]
    if updated == text:
        return False
    ledger.write_text(updated, encoding="utf-8", newline="\n")
    return True


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args and args[0] == "--write":
        ledger = Path(args[1])
        paths = [Path(a) for a in args[2:]]
        changed = write_block(ledger, paths)
        print(f"  {'updated' if changed else 'unchanged'}  {ledger}")
        return 0
    if args and args[0] == "--table":
        paths = [Path(a) for a in args[1:]]
        if not paths:
            print("usage: --table <memo>...", file=sys.stderr)
            return 2
        print(render_block(paths))
        return 0
    paths = [Path(a) for a in args]
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
