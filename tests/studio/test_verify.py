"""V8 / S6 — the deposition page and the verifier's own three-outcome vocabulary.

F-V1: a search of `tests/studio/` for a test asserting the verifier's
verified/failed/unreadable triad found none — not because the outcomes were never
exercised (`tests/studio/test_dogfooding.py::test_step_8_the_verify_command_runs_on_a_
receipt_this_walkthrough_produced` and
`test_the_verify_commands_other_two_outcomes_are_what_the_document_says` between them
run all three exit codes through the real CLI), but because nothing named the triad
itself as the thing under test, in one place, by the words the product actually uses.
This file is that place: `verify.check`'s three outcomes, asserted by name, plus the two
download routes F-V1 adds (the reason a stranger can now get a known-good file to run
that check on at all, rather than hand-pasting out of a `<pre>` block).
"""

from __future__ import annotations

import pytest

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.studio import screens, server, shell, verify


@pytest.fixture
def state(tmp_path):
    st = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    policy_loader.upsert(
        st.enforcer,
        Policy(action_type="seed.action", tier=Tier.CONFIRM, bounds=Bounds(strict_params=False)),
    )
    policy_loader.record_snapshot(st.enforcer)
    return st


def _ratified_digest(state) -> str:
    draft = server.new_draft(state, title="the pass draft")
    server.save_draft(
        state,
        draft.draft_id,
        policies=[
            Policy(
                action_type="reports.read",
                tier=Tier.OBSERVE,
                bounds=Bounds(strict_params=False),
            )
        ],
    )
    outcome = server.ratify_draft(state, draft.draft_id, session="tester")
    assert outcome.ratified, outcome.message
    assert outcome.receipt is not None
    return str(outcome.receipt.sealed()["ratification_digest"])


# --- the triad, asserted by name, at the function the page and the CLI both share ------


def test_a_sound_receipt_verifies(state) -> None:
    digest = _ratified_digest(state)
    dep = verify.deposition(state.enforcer, digest)
    assert dep is not None
    assert dep.outcome == verify.VERIFIED
    outcome, _detail = verify.check(dep.receipt_json, dep.snapshot_text)
    assert outcome == verify.VERIFIED


def test_a_tampered_snapshot_fails_not_unreadable(state) -> None:
    """One changed byte in a well-formed file: the check RUNS and disagrees. That is
    `failed`, never `unreadable` — the file could be read; what it said was wrong."""
    digest = _ratified_digest(state)
    dep = verify.deposition(state.enforcer, digest)
    assert dep is not None
    tampered = dep.snapshot_text.replace('"policies"', '"policiesx"', 1)
    assert tampered != dep.snapshot_text  # precondition: the replace actually landed
    outcome, _detail = verify.check(dep.receipt_json, tampered)
    assert outcome == verify.FAILED


def test_the_snapshot_panel_cannot_blow_out_the_page_width(state) -> None:
    """`policy_loader._normalized_snapshot` writes the stored snapshot with
    `separators=(",", ":")` and no `indent` -- one unbroken line, by design (it
    must stay byte-for-byte what was hashed). A real deployment's policy set
    makes that line thousands of characters long. `<pre>` does not wrap it, and
    `pre{overflow-x:auto}` only has an effect once something has already
    shrunk the box down to its container -- a CSS grid item's own default
    min-width is auto, which for unwrapped content is the content's own width,
    so without an explicit override the grid track (and the page) is forced
    out to match the line instead of scrolling it.
    """
    draft = server.new_draft(state, title="many policies")
    policies = [
        Policy(
            action_type=f"demo.action_{i:03d}",
            tier=Tier.OBSERVE,
            bounds=Bounds(strict_params=False),
        )
        for i in range(80)
    ]
    server.save_draft(state, draft.draft_id, policies=policies)
    outcome = server.ratify_draft(state, draft.draft_id, session="tester")
    assert outcome.ratified, outcome.message
    digest = str(outcome.receipt.sealed()["ratification_digest"])  # type: ignore[union-attr]

    dep = verify.deposition(state.enforcer, digest)
    assert dep is not None
    assert "\n" not in dep.snapshot_text, "precondition: the snapshot really is one line"
    assert len(dep.snapshot_text) > 5000, (
        "precondition: the line is long enough to actually blow out a fixed-width page"
    )

    body = screens.deposition_body(dep)
    assert "<pre>" in body and 'class="cols"' in body, (
        "precondition: the snapshot pre really is inside the two-column grid"
    )
    css = shell.css()
    assert ".cols>*{min-width:0}" in css, (
        "the grid item must be allowed to shrink below its unwrapped <pre> content, "
        "or pre's own overflow-x:auto never gets a chance to scroll"
    )


def test_an_unparseable_file_is_unreadable_not_failed(state) -> None:
    """A file the JSON parser cannot even open: the check never ran. Telling a stranger
    their RECEIPT is bad when what is bad is their DOWNLOAD is the error this
    distinction exists to prevent (`verify.py`'s own module docstring)."""
    outcome, _detail = verify.check("not json at all {{{", "also not json {{{")
    assert outcome == verify.UNREADABLE


def test_the_exit_codes_are_distinct_for_all_three() -> None:
    assert (
        len(
            {
                verify.EXIT[verify.VERIFIED],
                verify.EXIT[verify.FAILED],
                verify.EXIT[verify.UNREADABLE],
            }
        )
        == 3
    )
    assert verify.EXIT[verify.VERIFIED] == 0
    assert verify.EXIT[verify.FAILED] == 1
    assert verify.EXIT[verify.UNREADABLE] == 2


# --- F-V1: the download routes ----------------------------------------------------------


def test_the_download_routes_serve_the_identical_bytes_the_page_renders(state) -> None:
    from fastapi.testclient import TestClient

    digest = _ratified_digest(state)
    dep = verify.deposition(state.enforcer, digest)
    assert dep is not None
    client = TestClient(server.create_app(state))

    receipt = client.get(f"/verify/{digest}/receipt.json")
    snapshot = client.get(f"/verify/{digest}/snapshot.json")
    assert receipt.status_code == 200 and snapshot.status_code == 200
    assert receipt.text == dep.receipt_json
    assert snapshot.text == dep.snapshot_text
    assert 'attachment; filename="receipt.json"' in receipt.headers["content-disposition"]
    assert 'attachment; filename="snapshot.json"' in snapshot.headers["content-disposition"]


def test_a_downloaded_pair_verifies_through_the_real_cli(state, tmp_path) -> None:
    """The requested reproduction: not the view model, the actual command a
    stranger runs, over files downloaded through the actual route -- the path that was
    unfollowable before this fix. G2's corruption sub-test needs exactly this: a
    known-good downloaded file to corrupt, which the page could not previously supply."""
    import subprocess
    import sys

    from fastapi.testclient import TestClient

    digest = _ratified_digest(state)
    client = TestClient(server.create_app(state))
    receipt = client.get(f"/verify/{digest}/receipt.json")
    snapshot = client.get(f"/verify/{digest}/snapshot.json")

    (tmp_path / "receipt.json").write_bytes(receipt.content)
    (tmp_path / "snapshot.json").write_bytes(snapshot.content)
    result = subprocess.run(
        [sys.executable, "-m", "onedoor.studio.verify", "receipt.json", "snapshot.json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert result.stdout.startswith("verified:")


def test_the_download_routes_are_absent_not_a_failed_check_for_an_unknown_digest(
    state,
) -> None:
    """Same three-outcome discipline the page itself follows: a receipt this store never
    held is an absence, never rendered or served as though a check had run and failed."""
    from fastapi.testclient import TestClient

    client = TestClient(server.create_app(state))
    assert client.get("/verify/0000000000000000/receipt.json").status_code == 404
    assert client.get("/verify/0000000000000000/snapshot.json").status_code == 404


def test_the_deposition_page_offers_both_download_links(state) -> None:
    from fastapi.testclient import TestClient

    digest = _ratified_digest(state)
    client = TestClient(server.create_app(state))
    body = client.get(f"/verify/{digest}").text
    assert f'href="/verify/{digest}/receipt.json"' in body
    assert f'href="/verify/{digest}/snapshot.json"' in body
