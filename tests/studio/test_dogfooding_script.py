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
    assert "python -m onedoor.studio --db onedoor.db --studio-db studio.db" in commands
    assert "python -m onedoor.studio.walkthrough --db onedoor.db" in commands
    assert "python -m onedoor.studio.verify receipt.json snapshot.json" in commands


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


def test_the_time_budget_adds_up_to_the_forty_five_minutes_it_claims() -> None:
    """A budget that does not sum is a promise about someone's afternoon, broken quietly."""
    text = _text()
    rows = re.findall(r"^\| [A-H] · [^|]+\|\s*(\d+)\s*\|", text, re.M)
    assert len(rows) == 8, f"expected eight budgeted sections, found {len(rows)}"
    assert sum(int(r) for r in rows) == 45, (
        f"the per-section budgets sum to {sum(int(r) for r in rows)}, not the 45 minutes "
        "the pass is allotted"
    )
    assert "| **Total** | **45** |" in text


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
    assert "not in the 45" in text
    assert "| I · Propose | +6 |" in text


def test_the_script_states_where_its_estimate_is_a_guess() -> None:
    """An estimate presented as a measurement is the overclaim, one artifact over."""
    text = _text()
    folded = _normalised(text)
    assert "Every finding costs time this budget does not contain" in folded
    assert "walking" in folded and "estimate" in folded
