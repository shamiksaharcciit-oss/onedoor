"""V8 / S6 — the deposition page, and the command a stranger runs.

**This module is written for a reader who distrusts the operator, the vendor, and this
page** (R063 §6). Everything it asserts must be checkable by that reader with what the
page hands them: a command they can run, files they can hash, and outcomes named in the
three-outcome vocabulary.

## The page cannot verify, and says so

A verification performed by the vendor's own software, rendered by the vendor's own
page, is not evidence to someone who distrusts the vendor. So the page does two honest
things instead of one dishonest one: it **shows a verification that was run**, and it
**shows how to repeat it** without this program's cooperation.

`ratify.verify_files` is deliberately a thin function over two files and no database, so
the command below runs in a directory holding exactly those two files. If it ever needed
the store, the independence this page claims would be false.

## Running it

    python -m onedoor.studio.verify receipt.json snapshot.json

Exit status is the verdict: `0` verified, `1` failed, `2` the files could not be read.
**Three outcomes, in the exit code as well as the words** — a stranger scripting this
gets the same three answers a reader gets, which is R059 §2's whole-response honesty
applied to a command line.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass

from onedoor.studio import ratify

VERIFIED = "verified"
FAILED = "failed"
UNREADABLE = "unreadable"
"""The third outcome. A file that cannot be opened or parsed is **not** a failed check —
the check never ran. Collapsing them would tell a stranger the receipt is bad when what
is bad is their download."""

EXIT = {VERIFIED: 0, FAILED: 1, UNREADABLE: 2}

CANNOT_VERIFY = (
    "This page cannot verify anything for you. It was produced by the same software "
    "that produced the receipt, so it shows you a check that was run and the exact "
    "command to run it yourself, on files you hold, without this program's cooperation."
)
"""The oneview §4 discipline as a destination (R063 §6).

Not modesty. A verification rendered by the party being audited is worth exactly what
the auditor's trust in that party is worth, and this page's job is to need none of it.
"""

INDEPENDENCE = (
    "The command reads two files and opens no database. Copy them anywhere, run it "
    "there, and nothing this Studio holds can change the answer."
)

COMMAND = "python -m onedoor.studio.verify receipt.json snapshot.json"


@dataclass(frozen=True)
class Deposition:
    """Everything a stranger needs, resolved before rendering."""

    ratification_digest: str
    to_version: str
    receipt_json: str
    snapshot_text: str
    outcome: str
    detail: str

    @property
    def receipt_bytes(self) -> int:
        return len(self.receipt_json.encode("utf-8"))

    @property
    def snapshot_bytes(self) -> int:
        return len(self.snapshot_text.encode("utf-8"))


def available(ledger: sqlite3.Connection) -> tuple[tuple[str, str], ...]:
    """`(ratification_digest, ratified_at)` for every receipt this store can export.

    Read from `ratifications`, so the list offers what `export` can actually serve —
    the same discipline as V6's version dropdown, for the same reason.
    """
    rows = ledger.execute(
        "SELECT ratification_digest, created_at FROM ratifications "
        "ORDER BY created_at DESC, rowid DESC"
    ).fetchall()
    return tuple((str(r["ratification_digest"]), str(r["created_at"])) for r in rows)


def deposition(ledger: sqlite3.Connection, ratification_digest: str) -> Deposition | None:
    """The two files and the check, for one receipt. None when this store has no such
    receipt — absent, and rendered as absent rather than as a failed verification."""
    try:
        body, snapshot = ratify.export(ledger, ratification_digest)
    except ratify.RatificationRefused:
        return None

    receipt_json = json.dumps(body, indent=2, sort_keys=True)
    outcome, detail = check(receipt_json, snapshot)
    return Deposition(
        ratification_digest=ratification_digest,
        to_version=str(body.get("to_version") or ""),
        receipt_json=receipt_json,
        snapshot_text=snapshot,
        outcome=outcome,
        detail=detail,
    )


def check(receipt_json: str, snapshot_text: str) -> tuple[str, str]:
    """Run the third-party check over two in-memory strings.

    Shares `ratify.verify_files`' arithmetic by writing the same two files a stranger
    would — through a temporary directory, so the page and the command run **the same
    code over the same bytes**. A page that reimplemented the check would be a second
    implementation of the answer, and R062 §1 has already ruled on those.
    """
    import tempfile
    from pathlib import Path

    try:
        with tempfile.TemporaryDirectory(prefix="onedoor-deposition-") as scratch:
            receipt_path = Path(scratch) / "receipt.json"
            snapshot_path = Path(scratch) / "snapshot.json"
            receipt_path.write_text(receipt_json, encoding="utf-8")
            snapshot_path.write_text(snapshot_text, encoding="utf-8")
            return ratify.verify_files(str(receipt_path), str(snapshot_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return (UNREADABLE, f"the files could not be read: {exc}")


def main(argv: list[str] | None = None) -> int:
    """The command the page prints. Two files, no database, three exit codes."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(f"usage: {COMMAND}", file=sys.stderr)
        return EXIT[UNREADABLE]
    try:
        outcome, detail = ratify.verify_files(args[0], args[1])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        outcome, detail = UNREADABLE, f"the files could not be read: {exc}"
    stream = sys.stdout if outcome == VERIFIED else sys.stderr
    print(f"{outcome}: {detail}", file=stream)
    return EXIT.get(outcome, EXIT[FAILED])


if __name__ == "__main__":  # pragma: no cover - exercised through `main`
    raise SystemExit(main())
