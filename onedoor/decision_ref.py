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

Answers exactly one of four, each with its own exit code, distinct from the
generic usage-error code (64, the `sysexits.h` convention for "the command
line was used incorrectly") a missing or unreadable file gets instead:

    0   matches           -- a row in the export has this exact digest
    1   digest mismatch   -- a row shares the request_id, none matches the digest
    2   not in export     -- no row in the export shares the request_id at all
    3   malformed ref     -- the ref itself is not a well-formed decision_ref/1
"""

from __future__ import annotations

import argparse
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

EXIT_CODES: dict[str, int] = {
    MATCHES: 0,
    DIGEST_MISMATCH: 1,
    NOT_IN_EXPORT: 2,
    MALFORMED_REF: 3,
}
EXIT_USAGE_ERROR = 64
"""Not one of the four named outcomes: the command itself could not run (a
missing file, unreadable JSON in the export line-by-line stream) -- kept
clearly outside 0-3 so a script branching on those four never mistakes a
usage error for one of them."""

_REQUIRED_FIELDS = ("format", "request_id", "decision_digest", "verdict", "issuer")
_VALID_VERDICTS = ("permit", "deny", "propose")


class CheckResult(NamedTuple):
    status: str
    """One of `MATCHES`, `DIGEST_MISMATCH`, `NOT_IN_EXPORT`, `MALFORMED_REF`."""
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


def check_files(export_path: Path, ref_path: Path) -> CheckResult:
    """`check`, reading both files from disk. Raises `OSError`/`json.JSONDecodeError`
    for a file that cannot be read or parsed at all -- a usage error, not one
    of the four named outcomes (the CLI below maps it to `EXIT_USAGE_ERROR`).
    A single unparseable LINE inside an otherwise-readable export is not
    fatal: it is skipped, since it cannot be the row the ref names either way.
    """
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    rows: list[Mapping[str, object]] = []
    for line in export_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
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
