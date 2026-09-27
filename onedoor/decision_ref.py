"""The decision reference: a small, plain JSON object naming one onedoor
decision, joinable and checkable against an export of `actions_audit`.

Ruling on joining a onedoor decision to a onetrace run: the enforcement point
holds both halves at once and passes onedoor's answer into a run's own
receipt as exactly this shape:

    {"format": "onedoor-decision-ref/1",
     "request_id": "<the decide request's id>",
     "decision_digest": "sha256:<hex>",
     "verdict": "permit | deny | propose",
     "issuer": "<the onedoor deployment's declared id>"}

`onedoor.guardrail.models.DecisionRef` is the same shape as a pydantic model,
used by the engine itself. This module is deliberately separate and
stdlib-only: a consumer (a onetrace console, say) can vendor `check` and
`decision_digest` (from `onedoor.decision_digest`, itself stdlib-only)
without taking on onedoor's own dependency tree.

    python -m onedoor.decision_ref check --export <file.jsonl> --ref <ref.json>

Answers exactly one of five, each with its own exit code, distinct from the
generic usage-error code (64, the `sysexits.h` convention for "the command
line was used incorrectly") a missing or unreadable file gets instead:

    0   matches           -- a row in the export has this exact digest
    1   digest mismatch   -- a row shares the request_id, none matches the digest
    2   not in export     -- no row in the export shares the request_id at all
    3   malformed ref     -- the ref itself is not a well-formed decision_ref/1
    4   export damaged    -- the export's .sha256 does not match, or a line will not parse

A damaged export is never silently skipped into looking like `not in export`
(core ruling, effective immediately): a corrupted or truncated file could
otherwise hide the very row a reference names, and answer "not in export"
about a row that is, in fact, there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import NamedTuple

from onedoor.decision_digest import decision_digest

FORMAT = "onedoor-decision-ref/1"

MATCHES = "matches"
DIGEST_MISMATCH = "digest_mismatch"
NOT_IN_EXPORT = "not_in_export"
MALFORMED_REF = "malformed_ref"
EXPORT_DAMAGED = "export_damaged"

EXIT_CODES: dict[str, int] = {
    MATCHES: 0,
    DIGEST_MISMATCH: 1,
    NOT_IN_EXPORT: 2,
    MALFORMED_REF: 3,
    EXPORT_DAMAGED: 4,
}
EXIT_USAGE_ERROR = 64
"""Not one of the five named outcomes: the command itself could not run (a
missing file, an unreadable ref) -- kept clearly outside 0-4 so a script
branching on those five never mistakes a usage error for one of them."""

_REQUIRED_FIELDS = ("format", "request_id", "decision_digest", "verdict", "issuer")
_VALID_VERDICTS = ("permit", "deny", "propose")


class CheckResult(NamedTuple):
    status: str
    """One of `MATCHES`, `DIGEST_MISMATCH`, `NOT_IN_EXPORT`, `MALFORMED_REF`,
    `EXPORT_DAMAGED`."""
    detail: str

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]


def _malformed_ref_reason(ref: object) -> str | None:
    """`None` if `ref` is a well-formed `onedoor-decision-ref/1` object, else a
    plain-words reason it is not."""
    if not isinstance(ref, Mapping):
        return "ref is not a JSON object"
    for field in _REQUIRED_FIELDS:
        if field not in ref:
            return f"missing field: {field!r}"
    if ref["format"] != FORMAT:
        return f"unknown format: {ref['format']!r} (expected {FORMAT!r})"
    if not isinstance(ref["request_id"], str) or not ref["request_id"]:
        return "request_id must be a non-empty string"
    digest = ref["decision_digest"]
    if (
        not isinstance(digest, str)
        or not digest.startswith("sha256:")
        or len(digest) != len("sha256:") + 64
    ):
        return "decision_digest must be a 'sha256:<64 hex chars>' string"
    if ref["verdict"] not in _VALID_VERDICTS:
        return f"verdict must be one of {_VALID_VERDICTS}, got {ref['verdict']!r}"
    if not isinstance(ref["issuer"], str) or not ref["issuer"]:
        return "issuer must be a non-empty string"
    return None


def check(ref: object, export_rows: Iterable[Mapping[str, object]]) -> CheckResult:
    """Check `ref` against the rows of an export, already parsed (one dict per
    `actions_audit` row, in whatever order).

    A ref naming a `request_id` that more than one row shares (a resumption:
    the original propose and its later resumption both carry rows) is
    resolved correctly by design, not by accident: every candidate row's OWN
    digest is recomputed and compared, so the check matches the one row the
    ref actually names, never merely "a row with this request_id exists" --
    the sabotage this function's own tests guard against.
    """
    problem = _malformed_ref_reason(ref)
    if problem is not None:
        return CheckResult(MALFORMED_REF, problem)
    assert isinstance(ref, Mapping)  # narrowed by _malformed_ref_reason returning None

    request_id = ref["request_id"]
    candidates = [row for row in export_rows if row.get("request_id") == request_id]
    if not candidates:
        return CheckResult(NOT_IN_EXPORT, f"no row with request_id {request_id!r} in the export")

    target_digest = ref["decision_digest"]
    for row in candidates:
        if decision_digest(row) == target_digest:
            return CheckResult(MATCHES, f"row id={row.get('id')!r} matches")

    return CheckResult(
        DIGEST_MISMATCH,
        f"{len(candidates)} row(s) with request_id {request_id!r} found in the export, "
        f"none has digest {target_digest!r}",
    )


def _sidecar_digest(sidecar_text: str, export_name: str) -> str | None:
    """The hex digest a `.sha256` sidecar names for `export_name`, or `None`
    if the sidecar does not name it in a form this reads -- callers treat
    `None` as "nothing to check against", never as damage in itself."""
    first_line = sidecar_text.strip().splitlines()[0] if sidecar_text.strip() else ""
    parts = first_line.split(None, 1)
    if len(parts) != 2:
        return None
    digest, name = parts
    name = name.strip().removeprefix("*")  # sha256sum's binary-mode marker
    return digest if name == export_name else None


def check_files(export_path: Path, ref_path: Path) -> CheckResult:
    """`check`, reading both files from disk.

    Raises `OSError`/`json.JSONDecodeError` for a ref that cannot be read or
    parsed at all -- a usage error, not one of the five named outcomes (the
    CLI below maps it to `EXIT_USAGE_ERROR`); a ref is one small file supplied
    by the caller, and an unreadable one is a mistake in the invocation, not a
    fact about the export.

    The export is different: it is the thing being checked, so damage to IT
    is itself an outcome (`EXPORT_DAMAGED`), never an exception and never a
    silent skip. Its own `<export>.sha256` sidecar (as `python -m
    onedoor.export` writes beside every export) is verified first, when one
    is present beside it; a mismatch is reported before a single line is
    parsed, since a file that fails its own checksum cannot be trusted to
    explain itself line by line. After that, every non-blank line must parse
    as a JSON object -- one that doesn't is `EXPORT_DAMAGED`, not a skipped
    line, because a corrupted or truncated export could otherwise hide the
    very row a reference names and this would then wrongly answer
    `NOT_IN_EXPORT` about a row that is, in fact, there.
    """
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    export_bytes = export_path.read_bytes()

    sidecar_path = export_path.with_name(export_path.name + ".sha256")
    if sidecar_path.is_file():
        expected = _sidecar_digest(sidecar_path.read_text(encoding="utf-8"), export_path.name)
        if expected is not None:
            actual = hashlib.sha256(export_bytes).hexdigest()
            if actual != expected:
                return CheckResult(
                    EXPORT_DAMAGED,
                    f"{export_path.name}.sha256 says {expected}, the file's own sha256 is "
                    f"{actual}: the export does not match its own checksum",
                )

    rows: list[Mapping[str, object]] = []
    for lineno, raw_line in enumerate(export_bytes.decode("utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            return CheckResult(
                EXPORT_DAMAGED, f"line {lineno} of {export_path.name} is not valid JSON: {exc}"
            )
        if not isinstance(row, dict):
            return CheckResult(
                EXPORT_DAMAGED,
                f"line {lineno} of {export_path.name} is valid JSON but not an object",
            )
        rows.append(row)
    return check(ref, rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m onedoor.decision_ref",
        description="Check a decision reference against an onedoor export.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check_p = sub.add_parser("check", help="check one ref against one export")
    check_p.add_argument("--export", required=True, type=Path, help="export .jsonl file")
    check_p.add_argument("--ref", required=True, type=Path, help="decision_ref .json file")
    args = parser.parse_args(argv)

    if args.command == "check":
        if not args.export.is_file():
            print(f"usage error: no export file at {args.export}", file=sys.stderr)
            return EXIT_USAGE_ERROR
        if not args.ref.is_file():
            print(f"usage error: no ref file at {args.ref}", file=sys.stderr)
            return EXIT_USAGE_ERROR
        try:
            result = check_files(args.export, args.ref)
        except json.JSONDecodeError as exc:
            print(f"usage error: {args.ref} is not valid JSON: {exc}", file=sys.stderr)
            return EXIT_USAGE_ERROR
        print(f"{result.status.replace('_', ' ')}: {result.detail}")
        return result.exit_code

    return EXIT_USAGE_ERROR  # pragma: no cover - argparse's `required=True` prevents this


if __name__ == "__main__":
    raise SystemExit(main())
