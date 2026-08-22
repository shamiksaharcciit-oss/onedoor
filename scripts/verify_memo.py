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

Forward 003 clarified two readings of that definition, both binding:

  - "trailing whitespace stripped" means trailing **ASCII** whitespace, byte-level:
    the set ` \t\n\r\f\v`. Text-semantics stripping never enters a preimage -- a body
    ending in U+00A0 would otherwise digest differently across Unicode versions, the
    same reasoning that removed normalisation from ACJ preimages (E14). Operating on
    `bytes` is what makes this true here.
  - The file **ends** at the footer line with **at most one** terminating LF. A
    missing final LF is tolerated; any byte after that LF -- whitespace included -- is
    malformed, never ignorable: a passing verification must attest every byte in the
    file, and the permissive reading lets unattested content ride under a green
    verdict. (The tolerance was ratified on the forensics channel and relayed in
    R014 section 3; delivery's first pass required the LF, which was stricter than
    the rule. Tightening is not automatically conforming.)

Four traps, all walked into rather than foreseen, all now regression-tested:

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
   Absence of the marker means the file cannot be checked; presence of a marker that
   does not verify means "damaged", and the two must never collapse.
5. Absence was reported as "predates the protocol", which is an INFERENCE this tool
   cannot make. It was true of memos 001-006 and false the first time an unfootered
   artifact arrived after the protocol started -- the Policy Studio design note, dated
   2026-08-22, printed as though it were a 2026-08-20 file. Nothing was corrupted, but
   the verdict asserted a fact about provenance from the absence of a footer, and a
   reader scanning the output would have filed a live gap under "expected". The tool
   now reports what it observed and leaves the question of whether that is expected to
   `docs/from_core/INTEGRITY.md`, which records provenance per file.

   **RULED (R030 section 2): an artifact with no footer makes NO INTEGRITY CLAIM, and
   is therefore ABSENT** -- never rejected, which would punish the archive for being
   honest about its own history, and never blended with `unverifiable`, which would
   invent a claim nobody made. Three states, three meanings: absent is no claim,
   unverifiable is a claim that cannot be checked, damaged is a claim that checked
   false. The label here says only what the file shows; WHY a given file makes no
   claim is provenance, and provenance lives in the sidecar beside a human who looked.
4. Trailing CR/LF after the footer was tolerated. The footer was parsed as
   `raw[start:].rstrip(b"\r\n")`, which silently accepted any number of trailing
   newline bytes -- a divergence from Forward 003 section 2 in the permissive
   direction, found by probing the clause rather than by re-reading the code, and
   escalated to core rather than quietly patched. Adding the check then moved
   CRLF files onto a new branch and dropped the encoding diagnosis, so the hint now
   attaches to the *outcome* rather than to one route.
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

    def damaged(detail: str) -> Result:
        """Every damaged verdict names the encoding cause when CRLF is present.

        The hint used to hang off the digest-mismatch branch alone. Adding the
        Forward 003 §2 trailing-byte check moved CRLF files onto a different branch,
        which silently dropped the diagnosis -- a diagnosability regression in the
        very property core endorsed as the pattern. Attaching it to the outcome
        rather than to one route is what makes it survive the next new branch.
        """
        if b"\r\n" in raw:
            detail += (
                " -- file contains CRLF; check .gitattributes and core.autocrlf "
                "BEFORE suspecting core"
            )
        return Result("damaged", detail)

    starts = _marker_lines(raw)
    if not starts:
        return Result("no-footer")
    if len(starts) > 1:
        return damaged(
            f"{len(starts)} lines begin with `Integrity:`; exactly one is permitted. "
            f"Ambiguity is surfaced, never resolved (Response 010)."
        )
    start = starts[0]
    # Forward 003 §2: the file ends at the footer line's terminating LF. Any byte
    # after it makes the file malformed, never ignorable -- a passing verification
    # must attest EVERY byte in the file, and the permissive reading lets unattested
    # content ride under a green verdict. This checker previously did
    # `raw[start:].rstrip(b"\r\n")`, which silently tolerated any number of trailing
    # CR/LF bytes; found by probing the clause rather than by reading the code.
    line_end = raw.find(b"\n", start)
    if line_end == -1:
        # Missing final LF is TOLERATED (ratified on the forensics channel, relayed
        # in R014 §3): the file ends at the footer line with AT MOST one terminating
        # LF. Delivery's first pass required the LF and was stricter than the rule --
        # the opposite error to the permissive one it had just fixed, and a reminder
        # that tightening is not automatically conforming.
        footer = raw[start:]
    else:
        if line_end + 1 != len(raw):
            extra = len(raw) - (line_end + 1)
            return damaged(
                f"{extra} byte(s) after the footer's terminating LF; the file must end "
                f"there. Unattested trailing content is malformed, not ignorable -- "
                f"whitespace included."
            )
        footer = raw[start:line_end]
    if not footer.startswith(PREFIX):
        return damaged("footer line is malformed")
    claimed = footer[len(PREFIX) :]
    if len(claimed) != 64 or not all(c in b"0123456789abcdef" for c in claimed):
        return damaged("claimed digest is not 64 lowercase hex chars")
    actual = hashlib.sha256(preimage(raw, start)).hexdigest()
    if actual != claimed.decode():
        return damaged(f"claimed {claimed.decode()[:12]}..., got {actual[:12]}...")
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
        # "none", not "none (predates the footer)". The generator cannot know why a
        # footer is missing, and it guessed wrong the first time it met an unfootered
        # artifact that did NOT predate the protocol. Why a given file has no footer
        # is provenance, and provenance is recorded in the notes below by a human who
        # checked -- not inferred from an absence by a script.
        cell = f"`{d}`" if d else "none"
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
            # ASCII on purpose: this line is a console output contract, and a Windows
            # terminal on cp1252 prints an em dash as a replacement character.
            print(f"  --   {path.name}  (ABSENT - no integrity claim)")
        elif result.status == "ok":
            print(f"  OK   {path.name}")
        else:
            failed = True
            print(f"  FAIL {path.name}  {result.detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
