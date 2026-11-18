"""`run_record.json` exists because, without it, there was no way to tell after the fact
whether an eval run that started had ever finished -- `RESULTS.md`/`FINDINGS.md` alone
carry no run-identifying data, so a run that died mid-way and one that completed look
identical once it's over. This record's whole job is to be checkable against the files
it claims to describe: these tests are that check, run against what `cli.run` actually
writes, never against a hand-built record."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

from eval.harness import cli

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_record_s_hashes_match_the_files_it_was_written_beside(tmp_path: Path) -> None:
    cli.run(only="permits", record=False, out_dir=tmp_path)
    record = json.loads((tmp_path / "run_record.json").read_text(encoding="utf-8"))
    assert record["results_sha256"] == _sha256_file(tmp_path / "RESULTS.md")
    assert record["findings_sha256"] == _sha256_file(tmp_path / "FINDINGS.md")


def test_the_record_s_tree_id_is_a_real_tree(tmp_path: Path) -> None:
    cli.run(only="permits", record=False, out_dir=tmp_path)
    record = json.loads((tmp_path / "run_record.json").read_text(encoding="utf-8"))
    kind = subprocess.run(
        ["git", "cat-file", "-t", record["onedoor_tree"]],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert kind == "tree", f"the record's onedoor_tree names a {kind!r}, not a tree"
    text = (tmp_path / "RESULTS.md").read_text(encoding="utf-8")
    assert record["onedoor_tree"] in text, "the record's tree id disagrees with RESULTS.md's own"


def test_the_record_s_times_are_utc_and_ordered(tmp_path: Path) -> None:
    cli.run(only="permits", record=False, out_dir=tmp_path)
    record = json.loads((tmp_path / "run_record.json").read_text(encoding="utf-8"))
    started = datetime.fromisoformat(record["started_at"])
    ended = datetime.fromisoformat(record["ended_at"])
    assert started.utcoffset().total_seconds() == 0, "started_at is not UTC"
    assert ended.utcoffset().total_seconds() == 0, "ended_at is not UTC"
    assert started <= ended


def test_a_run_that_never_finished_leaves_no_record(tmp_path: Path) -> None:
    """The record is written only after RESULTS.md and FINDINGS.md are both already on
    disk -- never ahead of them, and never describing a run that didn't get this far."""
    cli.run(only="permits", record=False, out_dir=tmp_path)
    (tmp_path / "RESULTS.md").unlink()
    (tmp_path / "FINDINGS.md").unlink()
    (tmp_path / "run_record.json").unlink()
    (tmp_path / "eval-results.svg").unlink(missing_ok=True)
    cli.run(only="permits", record=False, out_dir=tmp_path)
    assert (tmp_path / "run_record.json").exists()
    assert (tmp_path / "RESULTS.md").exists()
    assert (tmp_path / "FINDINGS.md").exists()


def test_the_record_s_versions_and_totals_are_present_and_well_typed(tmp_path: Path) -> None:
    cli.run(only="permits", record=False, out_dir=tmp_path)
    record = json.loads((tmp_path / "run_record.json").read_text(encoding="utf-8"))
    assert isinstance(record["python_version"], str) and record["python_version"]
    assert isinstance(record["onedoor_version"], str) and record["onedoor_version"]
    assert isinstance(record["totals"], dict) and record["totals"]
    assert all(isinstance(v, int) for v in record["totals"].values())
