"""onedoor.decision_ref: the standalone checker. One test per answer, plus the
sabotage the ruling asks for -- a checker that matched on `request_id` alone,
never comparing the digest, would wrongly call a genuine mismatch a match, and
a named test here would fail if that regression landed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from onedoor.decision_digest import decision_digest
from onedoor.decision_ref import (
    DIGEST_MISMATCH,
    EXIT_USAGE_ERROR,
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


def test_check_files_skips_an_unparseable_export_line(tmp_path: Path) -> None:
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
    assert result.status == MATCHES


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
