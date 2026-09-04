"""`docs/DOGFOODING_SCRIPT.md` — the operator pass, held to the code it describes.

R070 §1 asks the script to quote the surfaces' own text where it matters. A quotation is a
claim about what a screen says, and **a claim about code is a test** — otherwise the
script drifts, the operator is told to expect a sentence that no longer exists, and the
pass produces a finding about the script rather than about the product.

Same law as the walkthrough (R065 §1): **test the document itself, or the test guards a
copy while the person follows the original.** So every quoted sentence below is read out of
the document and matched against the constant it came from, and every route the script
tells Shamik to call is checked against the app's own route table.

The one thing this file does NOT do is run the pass. It cannot: the pass is a person
looking at screens and saying what they see, and that is the whole reason it gates the tag.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from onedoor.studio import (
    api,
    drafts,
    forecast,
    library,
    live_proposer,
    screens,
    shell,
    staging,
    validate,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs" / "DOGFOODING_SCRIPT.md"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


#: Every constant the script quotes, by the name it is quoted from. The script must carry
#: each verbatim — these are the sentences an operator is told to look for, and a stale one
#: sends them hunting for words the screen no longer says.
QUOTED = {
    "shell.LOOPBACK_LINE": shell.LOOPBACK_LINE,
    "library.ABSENCE_IS_DENIAL": library.ABSENCE_IS_DENIAL,
    "validate.INCOMPLETE_NOTICE": validate.INCOMPLETE_NOTICE,
    "staging.STOPPED_NOTICE": staging.STOPPED_NOTICE,
    "forecast.FORECAST_NOTICE": forecast.FORECAST_NOTICE,
    "forecast.FORECASTS_ARE_NOT_COMPLETE": forecast.FORECASTS_ARE_NOT_COMPLETE,
    "drafts.IRREVERSIBLE": drafts.IRREVERSIBLE,
    "api.SUBMIT_MEANS": api.SUBMIT_MEANS,
    "api.NO_APPROVAL_NOTE": api.NO_APPROVAL_NOTE,
    "live_proposer.CAPABILITY": live_proposer.CAPABILITY,
    "screens.DARK_SURFACE_HEADING": screens.DARK_SURFACE_HEADING,
}


def _normalised(value: str) -> str:
    """Whitespace-folded, because the document wraps these sentences across lines.

    Line wrapping is not a change to what a sentence says, and a test that failed on it
    would force the document into unreadable long lines to satisfy a checker — the
    checker-reads-prose defect arriving from the other direction.
    """
    return " ".join(value.split())


def test_the_script_exists_and_is_sealed() -> None:
    assert SCRIPT.is_file(), "the operator script is gone; this test guards nothing"
    body = _text()
    assert body.rstrip().splitlines()[-1].startswith("Integrity: sha256(body) = "), (
        "the script must carry the protocol's integrity footer"
    )
    assert "\r" not in body, "CRLF in a sealed document breaks its own digest"


@pytest.mark.parametrize("name", sorted(QUOTED))
def test_every_quoted_sentence_is_the_constant_it_claims_to_be(name: str) -> None:
    """Parametrised per constant, so a failure names which sentence went stale."""
    assert _normalised(QUOTED[name]) in _normalised(_text()), (
        f"the script quotes {name} but the code's text has changed. An operator would be "
        "told to look for a sentence the screen no longer says, and would report a "
        "finding about this document instead of about the product."
    )


def test_the_script_names_the_stage_labels_the_loader_reports() -> None:
    """Two stages are named in the deliberate-failure stops; both must be real."""
    text = _normalised(_text())
    for stage in (staging.STAGE_RULES, staging.STAGE_LOAD):
        assert staging.STAGE_LABELS[stage] in text, f"the script names no label for stage {stage!r}"


def test_the_script_names_the_reason_code_the_forecast_stop_turns_on() -> None:
    from onedoor.guardrail.models import CheckId

    assert CheckId.COST_UNKNOWN.value in _text(), (
        "section D turns on the operator seeing `cost_unknown`; the code must be named"
    )


def test_the_script_names_every_built_tab() -> None:
    """A script naming a screen that is not there sends a person looking for it."""
    text = _text()
    for tab in shell.TABS:
        assert f"**{tab.label}**" in text, f"the script never mentions {tab.label}"
    assert f"**{shell.PROPOSE_TAB.label}**" in text


# --- the routes and commands the script tells an operator to use ------------------------


def _app_paths(method: str) -> set[str]:
    """Route templates the app actually serves. Read off the running app (R064 §2)."""
    import tempfile

    from onedoor.studio import server

    with tempfile.TemporaryDirectory() as tmp:
        state = server.open_state(f"{tmp}/onedoor.db", f"{tmp}/studio.db")
        try:
            app = server.create_app(state)
            return {
                route.path
                for route in app.routes
                if method in set(getattr(route, "methods", set()))
            }
        finally:
            state.close()


def test_every_api_path_the_script_names_is_served() -> None:
    """Sends an operator nowhere that does not exist."""
    named = set(re.findall(r"localhost:8787(/api/v1[^\s'\"`]*)", _text()))
    assert named, "precondition: the script does tell the operator to call the API"

    served = _app_paths("GET") | _app_paths("POST")
    for path in named:
        template = re.sub(r"/<id>", "/{draft_id}", path)
        assert template in served, (
            f"the script tells an operator to call {path}, which the app does not serve"
        )


def test_the_shell_commands_the_script_gives_are_the_real_ones() -> None:
    """Each is already run or checked by the walkthrough's own suite; here they are only
    matched, so the two documents cannot drift into naming different commands."""
    commands = [
        line.strip()
        for block in re.findall(r"```\n(.*?)```", _text(), re.S)
        for line in block.splitlines()
        if line.strip()
    ]
    assert "python -m onedoor.studio --db pass.db --studio-db pass-studio.db" in commands
    assert "python -m onedoor.studio.walkthrough --db pass.db" in commands
    assert "python -m onedoor.studio.verify receipt.json snapshot.json" in commands


def test_the_script_uses_a_purpose_made_store_not_ambient_state() -> None:
    """R086 §4.1: a re-walk is deterministic only if it never touches what a previous
    pass, or the README quickstart, already left in `onedoor.db` / `studio.db`."""
    text = _text()
    assert "--db onedoor.db" not in text, "the script must not point at the ambient store"
    assert "--db pass.db" in text
    assert "--studio-db pass-studio.db" in text


def test_the_seed_step_loads_the_shipped_payments_pack_and_records_a_version(
    tmp_path,
) -> None:
    """R086 §4.2: the seed commands actually work, against the real pack and the real
    loader — not just described in prose. `record_snapshot` has to run too, or
    `current_version` stays `None` and A2's banner would show `no version in force`."""
    from onedoor.guardrail import policy_loader
    from onedoor.store.db import Database

    pack = ROOT / "onedoor" / "templates" / "payments" / "policies.yaml"
    assert pack.is_file(), "the script tells the operator to copy a pack that must exist"

    database = Database(str(tmp_path / "pass.db"))
    database.init()
    conn = database.connect()
    n = policy_loader.load_file(conn, pack)
    version = policy_loader.record_snapshot(conn)
    assert n == 6, "A0's Expect says '6 policies loaded'; the pack must match"
    assert len(version) == 64 and all(c in "0123456789abcdef" for c in version)

    text = _text()
    assert "6 policies loaded" in text
    assert "version digest:" in text
    assert "6 policies · 2 effects" in text, "A2's Expect must name the resulting banner"


def test_the_bad_yaml_the_script_supplies_really_is_refused_at_the_stage_it_says() -> None:
    """**The deliberate-failure stops must actually fail, and at the named stage.**

    A script that told an operator to expect a refusal, over a file the loader happily
    accepts, would manufacture a finding out of nothing and burn minutes the pass has
    budgeted. So the fixture is run through the real staged validator here.
    """
    bad = "policies:\n  - action_type: payments.transfer\n    tier: 2\n"
    result = staging.staged(bad)
    assert result.stopped_at == staging.STAGE_RULES
    assert any("compensating_command" in r.message for r in result.refusals)

    unparseable = "policies:\n  - [unclosed\n"
    broken = staging.staged(unparseable)
    assert broken.stopped_at == staging.STAGE_LOAD
    assert broken.stages_not_run, "the stopped-notice stop needs stages that did not run"


def test_the_euro_cap_stop_lands_in_the_forecast_list_and_not_the_refusal_list() -> None:
    """Section D's whole point, verified rather than asserted in prose.

    The script tells Shamik that finding this in the refusal list is a serious finding. If
    the product ever put it there, this test fails first and the script is not the thing
    that discovers it.
    """
    from onedoor.guardrail.models import CheckId

    rule = '{"action_type": "payments.transfer", "tier": 3, "caps": {"eur_day": "100"}}'
    result = staging.staged_rule(rule)
    assert result.loads is True
    assert result.refusals == ()

    codes = {f.reason_code for f in forecast.build(result.policies, result.effects)}
    assert CheckId.COST_UNKNOWN.value in codes


# --- the budget, and the claims the script makes about itself ---------------------------


def test_the_time_budget_adds_up_to_the_fifty_minutes_it_claims() -> None:
    """A budget that does not sum is a promise about someone's afternoon, broken quietly.

    R086 §4: the budget is RE-DERIVED, not retyped, because section A grew a seeding
    stop and section C grew a second beat in C1c and a rule switch in C1d. This test
    holds the arithmetic, not the number — it would catch a section growing in prose
    without the total following.
    """
    text = _text()
    rows = re.findall(r"^\| [A-H] · [^|]+\|\s*(\d+)\s*\|", text, re.M)
    assert len(rows) == 8, f"expected eight budgeted sections, found {len(rows)}"
    total = sum(int(r) for r in rows)
    assert total == 50, (
        f"the per-section budgets sum to {total}, not the 50 minutes the pass is allotted"
    )
    assert f"| **Total** | **{total}** |" in text


def test_the_script_marks_every_stop_as_gate_or_see() -> None:
    """R070 §1.4: the stops that gate the tag are distinguished from the nice-to-see."""
    stops = re.findall(r"^\*\*([A-I]\d[a-z]?) \[(GATE|SEE)[^\]]*\]", _text(), re.M)
    assert stops, "no marked stops found"
    unmarked = re.findall(r"^\*\*([A-I]\d[a-z]?) —", _text(), re.M)
    assert not unmarked, f"stops with no GATE/SEE marking: {unmarked}"


def test_the_cut_list_names_only_stops_that_exist_and_none_that_gate() -> None:
    """The order-to-cut-in must not quietly drop a stop that gates the tag."""
    text = _text()
    cut = re.search(r"the order to cut in:\*\* ([A-I0-9a-z, ]+?) —", text)
    assert cut, "the script promises an order to cut in and does not give one"

    marked = dict(re.findall(r"^\*\*([A-I]\d[a-z]?) \[(GATE|SEE)", text, re.M))
    for stop in [s.strip() for s in cut.group(1).split(",")]:
        assert stop in marked, f"the cut list names {stop}, which is not a stop"
        assert marked[stop] == "SEE", (
            f"the cut list would drop {stop}, which is marked GATE. A pass that gates the "
            "tag may not shed a gating stop to save minutes."
        )


def test_the_script_says_propose_is_outside_the_budget() -> None:
    """T3's gate is unresolved, so its screens may not ship; the budget must not assume."""
    text = _text()
    assert "not in the 50" in text
    assert "| I · Propose | +6 |" in text


def test_the_script_states_where_its_estimate_is_a_guess() -> None:
    """An estimate presented as a measurement is the overclaim, one artifact over."""
    folded = _normalised(_text())
    assert "Every finding costs time the walking number does not contain" in folded
    assert "walking" in folded


def test_the_script_budgets_an_envelope_and_not_a_number() -> None:
    """R071 §1.1: **a time budget that excludes the cost of what the activity produces is
    not a budget.**

    The pass exists to produce findings, so the time to record them is budgeted rather
    than hoped away. Checked in the FIRST screenful, where an operator decides whether to
    start — a correct envelope buried below the fold is a number nobody read.
    """
    text = _text()
    head = _normalised(text[: text.index("## A · Arrival")]).replace("–", "-")

    assert "Block 65-80 minutes." in head
    assert "50 minutes of walking" in head
    assert "15-30 minutes of findings" in head
    assert "expected, not feared" in head
    assert "two or three findings is what success looks like" in head.lower()


def test_the_script_tells_the_operator_which_variant_to_run_before_they_start() -> None:
    """R071 §1.1: the T3 world is known at the top, not discovered at section I.

    The question is now **answered** rather than asked (R079 §6): T3 measured 0/11 and
    does not ship on that result, so the current script is the no-Propose one and the
    operator is told so. The answer can flip once if three gates are met; the front
    matter says which world is current and what a flip would look like.
    """
    text = _text()
    head = text[: text.index("## A · Arrival")]
    assert "Which world you are in" in head
    assert "section I is NOT part of this pass" in head
    assert "71-86" in head.replace("–", "-"), "the alternate envelope must still be named"
    assert head.index("Which world you are in") < head.index("Block 65"), (
        "the variant answer comes before the envelope it changes"
    )


def test_the_script_defaults_to_the_shipping_world_rather_than_a_pending_question() -> None:
    """**The fallback is the current state, not a decision the operator must chase.**

    An operator who is handed nothing must still know what to walk. A front matter that
    said "ask someone" would leave the pass blocked at the door on a question its reader
    cannot answer — and the whole point of stating it at the top (R072 §1) is that the
    reader is standing there.
    """
    head = _normalised(_text()[: _text().index("## A · Arrival")])
    assert "If nobody hands you a different script, this one is the one to walk" in head
    assert "0 of 11" in head, "the reason the section is absent is stated, not merely the fact"


def test_the_cut_rule_is_in_the_prose_and_not_only_in_a_test() -> None:
    """An operator must know the rule before they need it."""
    head = _normalised(_text()[: _text().index("## A · Arrival")])
    assert "cut [SEE] stops, never [GATE] stops" in head


# --- R088 §3/§5.3: F-S1 -- A0 refuses/removes a leftover store, never reuses one -------


def test_a0_removes_leftover_pass_files_before_it_seeds_them() -> None:
    """The re-walk's own finding: a `pass.db` the agent's dry-run had already left on
    disk sixteen hours earlier was silently reused — "purpose-made store" failed
    without a word, and operator suspicion was the only detector. Both shells now
    remove every file this pass owns as A0's first act, printed either way, before
    anything is written."""
    text = _text()
    a0 = text[text.index("**A0 [") : text.index("**A1 [")]
    for target in ("pass.db", "pass-studio.db", "pass-policies.yaml"):
        assert target in a0.split("Windows (PowerShell):")[0], (
            f"{target} must be named in A0's own doctrine, not only in the commands"
        )
    assert "Remove-Item" in a0 and "-Force" in a0, "no PowerShell removal command"
    assert "rm -f" in a0, "no POSIX removal command"
    assert 'Write-Host "removed' in a0
    assert 'echo "removed' in a0
    # Removed BEFORE the seed, never after -- ordering is the whole fix.
    assert a0.index("Remove-Item") < a0.index("Copy-Item")
    assert a0.index("rm -f") < a0.index("cp ")


def test_a0s_windows_removal_announces_and_stops_on_a_locked_file() -> None:
    """R090 §5: on Windows, a file a running Studio server still has open cannot be
    removed. A0 used to swallow that with `-ErrorAction SilentlyContinue` and seed on
    top of whatever it failed to clear -- silent contamination, the exact defect F-S1
    exists to kill, one layer down. The PowerShell block must detect a removal failure
    and stop on its own, never fall through to the seed."""
    text = _text()
    a0 = text[text.index("**A0 [") : text.index("**A1 [")]
    ps_block = a0.split("Windows (PowerShell):")[1].split("macOS/Linux")[0]
    assert "-ErrorAction Stop" in ps_block, "removal must be able to fail loudly, not silently"
    assert "catch" in ps_block and "$locked" in ps_block
    assert "locked by a running process" in ps_block
    assert "stop the Studio and re-run" in ps_block
    # The seed commands must be gated behind the lock check -- not merely present
    # somewhere after it, but structurally unreachable when the removal failed.
    assert re.search(r"\}\s*else\s*\{", ps_block), (
        "the seed commands are not gated behind the lock check"
    )
    assert ps_block.index("if ($locked)") < ps_block.index("Copy-Item")


def test_the_lock_stop_is_explained_as_windows_only() -> None:
    """POSIX `rm` can unlink an open file (the inode outlives the last close), so the
    same failure mode does not exist there -- the script must say so rather than leave
    an operator wondering why one shell gates and the other does not."""
    text = _text()
    a0 = text[text.index("**A0 [") : text.index("**A1 [")]
    assert "this stop does not apply" in a0
    assert "unlink" in a0


# --- R089/R090 §3/§4: F-S2 (chain-number-or-unchained), F-S3 (C saves a real change) -----


def test_f2_expects_a_chain_number_or_unchained() -> None:
    """Core's own error, corrected: the newest row is legitimately `unchained` --
    chaining is opt-in/periodic -- and F2 previously overstated a guaranteed number."""
    text = _text()
    f2 = text[text.index("**F2 [") : text.index("**F3 [")]
    assert "chain number" in f2 and "`unchained`" in f2
    assert "or" in _normalised(f2).lower().split("chain number")[1].split("unchained")[0]


def test_g_points_at_the_download_links_not_hand_copying() -> None:
    """R089 F-V1: the page used to make its own instruction unfollowable -- the only
    path to the bytes was select-and-paste, which risks a byte and a false `failed`.
    G2 now names the Download links and runs the corruption sub-test on the file that
    came from clicking one, never on hand-typed or pasted content."""
    text = _text()
    g = text[text.index("## G ·") : text.index("## H ·")]
    assert "Download" in g
    assert "downloaded" in g
    assert "select-and-paste" in g or "hand-typed or pasted" in g


def test_c1c_saves_the_one_real_change_e_ratifies_and_f3_replays() -> None:
    """R089/R090 F-S3: C1's edits were unsaved by design, so E3-as-scripted ratified a
    no-op and F3 had nothing to replay against -- reachable only because an earlier
    operator deviated from the script. C1c now saves one real, valid change, and says
    why: without it, E is a no-op and F3 is unreachable on a faithful walk."""
    text = _text()
    c1c = text[text.index("**C1c [") : text.index("**C1d [")]
    assert "save from the raw pane" in c1c
    assert "F-S3" in c1c
    assert "no-op" in c1c
    assert "ratifies" in c1c.lower() or "replays" in c1c.lower()


# --- R086 §4.10: every [GATE] stop states what to do when it is blocked -----------------


def test_every_gate_stop_states_what_to_do_when_blocked() -> None:
    """ "Today that question came upward three times" (R086 §0). Every [GATE] marker in
    the 50-minute walking budget (sections A-H) now carries its own answer, so the
    question does not have to travel to whoever is running the pass — it is answered at
    the point it would be asked. Section I is out of the walking budget entirely (its own
    gate, T3's benchmark, is unresolved) and keeps its pre-existing `[GATE, if T3 ships]`
    marker, which is a different question — whether the stop exists at all this release.
    """
    text = _text()
    walking = text[: text.index("## I · Propose")]
    stops = re.findall(r"^\*\*([A-I]\d[a-z]?) \[GATE([^\]]*)\]", walking, re.M)
    assert stops, "no GATE stops found"
    ACTIONABLE = ("note the finding and continue", "skip", "stop the pass")
    for stop_id, clause in stops:
        assert any(word in clause for word in ACTIONABLE), (
            f"{stop_id}'s [GATE] marker does not say what to do when it is blocked: {clause!r}"
        )


def test_the_state_building_gates_are_the_ones_marked_to_skip_ahead() -> None:
    """A0 seeds the store everything else reads; C1a makes the draft C1b-E use; E3
    produces the receipt G verifies. Losing any of the three makes something later
    unreachable, which is a different situation from a stop that merely reads wrong —
    and the marker on each says so, by name, rather than leaving it to be inferred."""
    text = _text()
    assert re.search(r"\*\*A0 \[GATE — if blocked, stop the pass", text)
    assert re.search(r"\*\*C1a \[GATE — if blocked, skip C1b", text)
    assert re.search(r"\*\*E3 \[GATE — if blocked, skip G", text)


# --- R086 §4.4-4.7: the authoring stops name a specific rule, not "a rule" --------------


def test_the_authoring_stops_name_the_specific_rule_each_one_needs() -> None:
    text = _text()
    assert "**Do:** click **`payments.transfer`**." in text, "B2 must name its rule"
    assert "**Do:** open **`payouts.schedule`**" in text, "C1b must name its rule"
    assert "the pack's only tier-3 rule" in text, "C1b must say why that rule"
    assert "**Do:** open **`payments.transfer`** — the pack's only rule with decimal" in text, (
        "C1d must switch to the rule that actually has decimals to check"
    )


def test_c1c_demonstrates_the_referent_is_never_checked_and_cites_nd057() -> None:
    """R086 §4.6: type a nonexistent action, watch the refusal clear; then type a real
    one, watch it clear identically; then say why, citing the ND item filed for it."""
    text = _text()
    assert '"payments.refund"' in text and "names no action type in this pack" in text
    assert '"payments.reverse"' in text and "a real action type in this pack" in text
    assert "ND-057" in text


# --- R086 §4.8: files the operator creates are written by exact command, never copied ---


def test_files_the_operator_must_create_are_written_by_exact_command() -> None:
    """Finding 1's actual cause: 'save this as bad.yaml' over a fenced block let a fence
    tag become the file's first line. Both files this script asks for are now written by
    a command that produces the exact bytes, for both shells named in R086 §4.2."""
    text = _text()
    assert "save this as" not in text, "the old copy-this-block phrasing must be gone"
    for filename in ("bad.yaml", "broken.yaml"):
        assert f"Set-Content -NoNewline {filename}" in text, f"no PowerShell writer for {filename}"
        assert f"cat > {filename} <<'EOF'" in text, f"no POSIX writer for {filename}"


# --- R086 §4.9: curl.exe on Windows ------------------------------------------------------


def test_the_api_stops_offer_a_windows_curl_exe_variant() -> None:
    """`curl` is aliased to `Invoke-WebRequest` in PowerShell 5.1 and `-s` throws there."""
    text = _text()
    assert text.count("curl.exe -s") >= 4, "every C3 stop needs a curl.exe variant"
    assert "alias for" in text and "Invoke-WebRequest" in text
