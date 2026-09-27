"""onedoor.decision_ref: the standalone checker. One test per answer, plus two
sabotages: a checker that matched on `request_id` alone, never comparing the
digest, would wrongly call a genuine mismatch a match; a checker that skips a
line it cannot parse would wrongly call a damaged export "not in export".
Restoring either regression here makes a named test fail.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from onedoor.decision_digest import decision_digest
from onedoor.decision_ref import (
    DIGEST_MISMATCH,
    EXIT_USAGE_ERROR,
    EXPORT_DAMAGED,
    FORMAT,
    MALFORMED_REF,
    MATCHES,
    NOT_IN_EXPORT,
    check,
    check_files,
    main,
)

ROW_A = {"id": 1, "kind": "decision", "request_id": "req-a", "decision": "denied"}
ROW_B = {"id": 2, "kind": "exec_intent", "request_id": "req-b", "decision": "executed"}
# A resumption: req-c's propose and req-d's resumption are two different rows
# but the SAME logical action -- req-b and req-d deliberately share no id with
# each other; what matters below is that req-c (propose) and req-d (resume)
# are two DIFFERENT rows the checker must not confuse.
ROW_PROPOSE = {"id": 3, "kind": "decision", "request_id": "req-c", "decision": "proposed"}
ROW_RESUME = {"id": 4, "kind": "exec_intent", "request_id": "req-c", "decision": "executed"}
# ^ same request_id is unusual in practice (a resumption normally mints a new
# request_id) but is exactly the adversarial case worth testing: two rows,
# same request_id, different content, different digests.

EXPORT = [ROW_A, ROW_B, ROW_PROPOSE, ROW_RESUME]


def _ref(
    *, request_id: str, decision_digest_value: str, verdict: str = "deny", issuer: str = "iss"
) -> dict[str, object]:
    return {
        "format": FORMAT,
        "request_id": request_id,
        "decision_digest": decision_digest_value,
        "verdict": verdict,
        "issuer": issuer,
    }


def test_matches() -> None:
    ref = _ref(request_id="req-a", decision_digest_value=decision_digest(ROW_A))
    result = check(ref, EXPORT)
    assert result.status == MATCHES
    assert result.exit_code == 0


def test_digest_mismatch() -> None:
    ref = _ref(request_id="req-a", decision_digest_value="sha256:" + "0" * 64)
    result = check(ref, EXPORT)
    assert result.status == DIGEST_MISMATCH
    assert result.exit_code == 1


def test_not_in_export() -> None:
    ref = _ref(request_id="req-does-not-exist", decision_digest_value="sha256:" + "0" * 64)
    result = check(ref, EXPORT)
    assert result.status == NOT_IN_EXPORT
    assert result.exit_code == 2


@pytest.mark.parametrize(
    "bad_ref",
    [
        {},
        {"format": "onedoor-decision-ref/1"},  # missing fields
        {**_ref(request_id="req-a", decision_digest_value="x"), "format": "wrong/1"},
        {**_ref(request_id="req-a", decision_digest_value="x"), "verdict": "allow"},
        {**_ref(request_id="req-a", decision_digest_value="x"), "issuer": ""},
        {
            **_ref(request_id="req-a", decision_digest_value="not-a-digest"),
        },
        "not even an object",
        None,
        42,
    ],
)
def test_malformed_ref(bad_ref: object) -> None:
    result = check(bad_ref, EXPORT)
    assert result.status == MALFORMED_REF
    assert result.exit_code == 3


def test_the_sabotage_the_ruling_names() -> None:
    """A ref naming req-c's digest for the PROPOSE row must not be reported as
    matching the RESUME row just because they share a request_id -- a checker
    that compared only `request_id` (the sabotage) would wrongly call this a
    match against whichever row happened to be checked first."""
    propose_digest = decision_digest(ROW_PROPOSE)
    resume_digest = decision_digest(ROW_RESUME)
    assert propose_digest != resume_digest, "the fixture rows must actually differ"

    ref_for_propose = _ref(
        request_id="req-c", decision_digest_value=propose_digest, verdict="propose"
    )
    result = check(ref_for_propose, EXPORT)
    assert result.status == MATCHES
    assert "id=3" in result.detail  # the propose row, not the resume row

    ref_for_resume = _ref(request_id="req-c", decision_digest_value=resume_digest, verdict="permit")
    result2 = check(ref_for_resume, EXPORT)
    assert result2.status == MATCHES
    assert "id=4" in result2.detail

    # A digest that names NEITHER row sharing this request_id must never match.
    ref_for_neither = _ref(request_id="req-c", decision_digest_value="sha256:" + "f" * 64)
    result3 = check(ref_for_neither, EXPORT)
    assert result3.status == DIGEST_MISMATCH


def test_check_files_matches_end_to_end(tmp_path: Path) -> None:
    export_path = tmp_path / "export.jsonl"
    export_path.write_text("".join(json.dumps(r) + "\n" for r in EXPORT), encoding="utf-8")
    ref_path = tmp_path / "ref.json"
    ref = _ref(request_id="req-b", decision_digest_value=decision_digest(ROW_B), verdict="permit")
    ref_path.write_text(json.dumps(ref), encoding="utf-8")

    result = check_files(export_path, ref_path)
    assert result.status == MATCHES


def test_check_files_reports_export_damaged_on_an_unparseable_line(tmp_path: Path) -> None:
    """An unparseable line is never silently skipped: skipping it would let a
    truncated or corrupted export answer NOT_IN_EXPORT about a row that is,
    in fact, sitting right there on the damaged line."""
    export_path = tmp_path / "export.jsonl"
    export_path.write_text(
        json.dumps(ROW_A) + "\n" + "{not json\n" + json.dumps(ROW_B) + "\n", encoding="utf-8"
    )
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(
        json.dumps(_ref(request_id="req-b", decision_digest_value=decision_digest(ROW_B))),
        encoding="utf-8",
    )
    result = check_files(export_path, ref_path)
    assert result.status == EXPORT_DAMAGED
    assert result.exit_code == 4
    assert "line 2" in result.detail


def test_check_files_reports_export_damaged_on_a_non_object_line(tmp_path: Path) -> None:
    export_path = tmp_path / "export.jsonl"
    export_path.write_text(json.dumps(ROW_A) + "\n" + "[1, 2, 3]\n", encoding="utf-8")
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(
        json.dumps(_ref(request_id="req-a", decision_digest_value=decision_digest(ROW_A))),
        encoding="utf-8",
    )
    result = check_files(export_path, ref_path)
    assert result.status == EXPORT_DAMAGED
    assert "line 2" in result.detail


def test_check_files_reports_export_damaged_on_a_sha256_mismatch(tmp_path: Path) -> None:
    export_path = tmp_path / "export.jsonl"
    export_path.write_text(json.dumps(ROW_A) + "\n", encoding="utf-8")
    sidecar_path = tmp_path / "export.jsonl.sha256"
    sidecar_path.write_text("0" * 64 + "  export.jsonl\n", encoding="utf-8")
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(
        json.dumps(_ref(request_id="req-a", decision_digest_value=decision_digest(ROW_A))),
        encoding="utf-8",
    )
    result = check_files(export_path, ref_path)
    assert result.status == EXPORT_DAMAGED
    assert "sha256" in result.detail


def test_check_files_matches_when_the_sha256_sidecar_is_correct(tmp_path: Path) -> None:
    """The sidecar check must not itself break the ordinary matching path.

    Written with `write_bytes`, not `write_text`: the digest below must match
    the file's ACTUAL bytes, and `write_text` translates `\\n` to the
    platform's line ending, which would make the two disagree on Windows.
    """
    export_path = tmp_path / "export.jsonl"
    text = json.dumps(ROW_A) + "\n"
    export_path.write_bytes(text.encode("utf-8"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    (tmp_path / "export.jsonl.sha256").write_text(f"{digest}  export.jsonl\n", encoding="utf-8")
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(
        json.dumps(_ref(request_id="req-a", decision_digest_value=decision_digest(ROW_A))),
        encoding="utf-8",
    )
    result = check_files(export_path, ref_path)
    assert result.status == MATCHES


def _check_files_that_skips_unparseable_lines(export_path: Path, ref_path: Path) -> str:
    """The sabotage this module's tests guard against: the checker's first
    cut, restored here to prove the regression it corrects would actually be
    caught. It skips a line it cannot parse instead of reporting
    EXPORT_DAMAGED -- exactly the shape of bug that would let a truncated
    export answer NOT_IN_EXPORT about a row sitting on the damaged line."""
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
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
    return check(ref, rows).status


def test_the_export_damaged_sabotage(tmp_path: Path) -> None:
    """req-b's own line is the one that fails to parse -- not some other,
    unrelated line. Restoring the old skip-on-parse-error behaviour therefore
    drops req-b's row entirely and answers NOT_IN_EXPORT, the wrong answer:
    the row is there, just damaged. The real `check_files` must give a
    different answer on the exact same fixture."""
    export_path = tmp_path / "export.jsonl"
    export_path.write_text(json.dumps(ROW_A) + "\n" + "{not json\n", encoding="utf-8")
    ref_path = tmp_path / "ref.json"
    ref_path.write_text(
        json.dumps(_ref(request_id="req-b", decision_digest_value=decision_digest(ROW_B))),
        encoding="utf-8",
    )

    assert _check_files_that_skips_unparseable_lines(export_path, ref_path) == NOT_IN_EXPORT

    result = check_files(export_path, ref_path)
    assert result.status == EXPORT_DAMAGED
    assert result.status != NOT_IN_EXPORT


# --- The CLI: one exit code per answer, plus the usage-error code -------------------


def _write(tmp_path: Path, name: str, obj: object) -> Path:
    path = tmp_path / name
    if isinstance(obj, list):
        path.write_text("".join(json.dumps(o) + "\n" for o in obj), encoding="utf-8")
    else:
        path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def test_cli_exit_code_matches(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    export_path = _write(tmp_path, "export.jsonl", EXPORT)
    ref_path = _write(
        tmp_path, "ref.json", _ref(request_id="req-a", decision_digest_value=decision_digest(ROW_A))
    )
    rc = main(["check", "--export", str(export_path), "--ref", str(ref_path)])
    assert rc == 0
    assert "matches" in capsys.readouterr().out


def test_cli_exit_code_digest_mismatch(tmp_path: Path) -> None:
    export_path = _write(tmp_path, "export.jsonl", EXPORT)
    ref_path = _write(
        tmp_path, "ref.json", _ref(request_id="req-a", decision_digest_value="sha256:" + "0" * 64)
    )
    rc = main(["check", "--export", str(export_path), "--ref", str(ref_path)])
    assert rc == 1


def test_cli_exit_code_not_in_export(tmp_path: Path) -> None:
    export_path = _write(tmp_path, "export.jsonl", EXPORT)
    ref_path = _write(
        tmp_path, "ref.json", _ref(request_id="nope", decision_digest_value="sha256:" + "0" * 64)
    )
    rc = main(["check", "--export", str(export_path), "--ref", str(ref_path)])
    assert rc == 2


def test_cli_exit_code_malformed_ref(tmp_path: Path) -> None:
    export_path = _write(tmp_path, "export.jsonl", EXPORT)
    ref_path = _write(tmp_path, "ref.json", {"not": "a valid ref"})
    rc = main(["check", "--export", str(export_path), "--ref", str(ref_path)])
    assert rc == 3


def test_cli_exit_code_export_damaged(tmp_path: Path) -> None:
    export_path = tmp_path / "export.jsonl"
    export_path.write_text(json.dumps(ROW_A) + "\n" + "{not json\n", encoding="utf-8")
    ref_path = _write(
        tmp_path, "ref.json", _ref(request_id="req-a", decision_digest_value=decision_digest(ROW_A))
    )
    rc = main(["check", "--export", str(export_path), "--ref", str(ref_path)])
    assert rc == 4


def test_cli_exit_code_usage_error_on_missing_export(tmp_path: Path) -> None:
    ref_path = _write(
        tmp_path, "ref.json", _ref(request_id="req-a", decision_digest_value=decision_digest(ROW_A))
    )
    rc = main(["check", "--export", str(tmp_path / "missing.jsonl"), "--ref", str(ref_path)])
    assert rc == EXIT_USAGE_ERROR


def test_cli_exit_code_usage_error_on_missing_ref(tmp_path: Path) -> None:
    export_path = _write(tmp_path, "export.jsonl", EXPORT)
    rc = main(["check", "--export", str(export_path), "--ref", str(tmp_path / "missing.json")])
    assert rc == EXIT_USAGE_ERROR


def test_the_four_named_exit_codes_are_distinct_from_each_other_and_from_usage_error() -> None:
    from onedoor.decision_ref import EXIT_CODES

    codes = list(EXIT_CODES.values()) + [EXIT_USAGE_ERROR]
    assert len(codes) == len(set(codes)), "every outcome must have its own exit code"
