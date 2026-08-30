"""`ND-056` / T1 — upload, and the live-validation fragment.

Upload is the reason the staged validator has anything to stage: it is the only entry
point where bytes reach the loader's first stage. Everything else in the Studio hands
`validate` a `Policy` that has already survived the three stages before it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Caps, EffectPolicy, Policy, Tier
from onedoor.studio import descriptions, forecast, screens, server, shell, staging, store

GOOD_FILE = """
policies:
  - action_type: payments.transfer
    tier: 2
    compensating_command: payments.refund
    cost_param: amount_eur
    bounds:
      required: [amount_eur]
  - action_type: payments.refund
    tier: 2
    compensating_command: payments.transfer
effects:
  money.egress:
    min_tier: 2
"""

REFUSED_FILE = """
policies:
  - action_type: payments.transfer
    tier: 2
"""


@pytest.fixture
def state(tmp_path):
    st = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    policy_loader.upsert(
        st.enforcer,
        Policy(action_type="seed.action", tier=Tier.CONFIRM, bounds=Bounds(strict_params=False)),
    )
    return st


@pytest.fixture
def client(state):
    return TestClient(server.create_app(state))


def _upload(client, body: bytes, name: str = "policies.yaml"):
    return client.post(
        "/drafts/upload",
        files={"policy_file": (name, body, "application/x-yaml")},
        follow_redirects=False,
    )


# --- the happy path ------------------------------------------------------------------


def test_an_uploaded_file_becomes_a_draft(client, state) -> None:
    response = _upload(client, GOOD_FILE.encode("utf-8"))
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/drafts/")

    draft_id = location.split("/drafts/")[1].split("?")[0]
    draft = store.load(state.studio, draft_id)
    assert draft is not None
    assert {p.action_type for p in draft.policies} == {
        "payments.transfer",
        "payments.refund",
    }
    assert {e.effect for e in draft.effects} == {"money.egress"}


def test_the_uploaded_bytes_are_frozen_verbatim(client, state) -> None:
    """E10: received data, byte for byte, before anything parses it.

    A file with CRLF line endings and a BOM survives unmodified — the two things a text
    round trip silently rewrites, and this project has been bitten by both.
    """
    import hashlib

    hostile = ("﻿" + GOOD_FILE.replace("\n", "\r\n")).encode("utf-8")
    response = _upload(client, hostile)
    assert response.status_code == 303

    digest = hashlib.sha256(hostile).hexdigest()
    stored = descriptions.raw(state.studio, digest)
    assert stored == hostile, "the uploaded bytes were rewritten on the way to the store"
    assert b"\r\n" in stored and stored.startswith(b"\xef\xbb\xbf")


def test_uploading_does_not_touch_the_rules_in_force(client, state) -> None:
    """Fence post one. A draft is not a policy set."""
    before = policy_loader.current_version(state.enforcer)
    count = server.active_policy_count(state)
    _upload(client, GOOD_FILE.encode("utf-8"))
    assert policy_loader.current_version(state.enforcer) == before
    assert server.active_policy_count(state) == count


# --- a file the loader would refuse ---------------------------------------------------


def test_a_refused_file_still_becomes_a_draft_that_shows_the_refusals(client, state) -> None:
    """The on-save refusal is exactly what this ticket replaces.

    Handing the operator their file back with a message is the behaviour Forward 006
    called short of the bar. The draft is created, and the refusals are on its page.
    """
    response = _upload(client, REFUSED_FILE.encode("utf-8"))
    assert response.status_code == 303
    draft_id = response.headers["location"].split("/drafts/")[1].split("?")[0]
    assert store.load(state.studio, draft_id) is not None

    result = staging.staged(REFUSED_FILE)
    assert result.stopped_at == staging.STAGE_RULES
    assert "compensating_command" in result.refusals[0].message


def test_an_empty_upload_is_an_absence_and_says_so(client) -> None:
    response = client.post(
        "/drafts/upload", files={"policy_file": ("empty.yaml", b"", "application/x-yaml")}
    )
    assert response.status_code == 400
    assert "absence" in response.text
    assert "not a rejected file" in response.text


def test_a_file_that_is_not_utf8_is_unreadable_not_invalid(client) -> None:
    """Three outcomes at the door: unreadable is not a failed validation.

    Telling an operator their policy is invalid when what is wrong is the file's encoding
    is a verdict about content delivered about a file nothing could read — the deposition
    page's cardinal error, committed at the other end of the product.
    """
    response = _upload(client, b"policies:\n  - action_type: \xff\xfe\n", "latin.yaml")
    assert response.status_code == 400
    assert "could not be read" in response.text
    assert "not UTF-8" in response.text
    # The page must NOT claim the policy is invalid.
    assert "Nothing here says" in response.text


# --- the live-validation fragment -----------------------------------------------------


def test_the_fragment_is_the_same_function_the_page_calls(client, state) -> None:
    """A keystroke and a page load render the same bytes, because they call one function."""
    draft = server.new_draft(state, title="live")
    rule = '{"action_type": "a.b", "tier": 2}'
    response = client.post(f"/drafts/{draft.draft_id}/validate", data={"raw": rule})
    assert response.status_code == 200

    result, items = server.validation_for_rule(state, rule)
    assert response.text == screens.validation_fragment(result, items, inert_checked=True)


def test_the_fragment_reports_a_rule_the_loader_would_refuse(client, state) -> None:
    draft = server.new_draft(state, title="live")
    response = client.post(
        f"/drafts/{draft.draft_id}/validate", data={"raw": '{"action_type": "a.b", "tier": 2}'}
    )
    assert "compensating_command" in response.text
    assert "The loader would refuse this" in response.text


def test_the_fragment_separates_refusals_from_forecasts(client, state) -> None:
    """The C4 fence, at the surface a person actually reads."""
    draft = server.new_draft(state, title="live")
    rule = '{"action_type": "a.b", "tier": 3, "caps": {"eur_day": "100"}}'
    response = client.post(f"/drafts/{draft.draft_id}/validate", data={"raw": rule})
    body = response.text

    assert "The loader would refuse this" in body
    assert "Once in force, these rules will" in body
    assert body.index("The loader would refuse this") < body.index("Once in force")
    # The priced cap is a forecast and NOT a refusal: the loader accepts this rule.
    assert "cost_unknown" in body
    assert "Nothing here would be refused at boot" in body


def test_the_fragment_for_an_unknown_draft_is_an_absence_not_a_verdict(client) -> None:
    response = client.post("/drafts/nope/validate", data={"raw": "{}"})
    assert response.status_code == 404
    assert "nothing was validated" in response.text
    assert "Nothing here is a statement about the rule you are editing" in response.text


def test_validating_writes_nothing_anywhere(client, state) -> None:
    draft = server.new_draft(state, title="live")
    stored = store.load(state.studio, draft.draft_id)
    version = policy_loader.current_version(state.enforcer)

    for text in ('{"action_type": "a.b", "tier": 2}', "not yaml: [", ""):
        client.post(f"/drafts/{draft.draft_id}/validate", data={"raw": text})

    after = store.load(state.studio, draft.draft_id)
    assert after is not None and stored is not None
    assert after.policies == stored.policies
    assert policy_loader.current_version(state.enforcer) == version


# --- the inert forecast reaches the surface with the live effect set -------------------


def test_the_inert_forecast_uses_the_effect_policies_in_force(client, state) -> None:
    """`known_effects` comes from the enforcer, so the check runs rather than being absent."""
    assert server.known_effects(state) == set()
    draft = server.new_draft(state, title="live")
    rule = '{"action_type": "a.b", "tier": 3, "effects": ["money.egress"]}'
    response = client.post(f"/drafts/{draft.draft_id}/validate", data={"raw": rule})
    assert "effect_floor" in response.text
    assert "money.egress" in response.text

    policy_loader.upsert_effect(state.enforcer, EffectPolicy(effect="money.egress", caps=Caps()))
    assert server.known_effects(state) == {"money.egress"}
    again = client.post(f"/drafts/{draft.draft_id}/validate", data={"raw": rule})
    assert "effect_floor" not in again.text


# --- the upload affordance is reachable ------------------------------------------------


def test_the_drafts_page_offers_the_upload_form(client) -> None:
    from tests.viewer.assertions import assert_reader_sees

    body = client.get("/drafts").text
    assert 'action="/drafts/upload"' in body
    assert 'enctype="multipart/form-data"' in body
    # Verbatim in the form the reader receives -- the note contains an apostrophe, and
    # asserting the raw constant would make a correctly-escaped page look wrong (R061 §3).
    assert_reader_sees(body, screens.UPLOAD_NOTE)


def test_the_upload_note_says_nothing_uploaded_reaches_the_rules(client) -> None:
    assert "a draft is not a policy set" in screens.UPLOAD_NOTE
    assert "ratification ceremony" in screens.UPLOAD_NOTE


def test_the_editor_page_carries_the_live_validation_handle(client, state) -> None:
    """The script needs a target the SERVER wrote; without it, it returns early."""
    draft = server.new_draft(state, title="edit")
    server.save_draft(
        state,
        draft.draft_id,
        policies=[Policy(action_type="a.b", tier=Tier.CONFIRM, bounds=Bounds(strict_params=False))],
    )
    body = client.get(f"/drafts/{draft.draft_id}/edit/a.b").text
    assert 'id="raw-pane"' in body
    assert f'data-validate="/drafts/{draft.draft_id}/validate"' in body
    assert 'id="validation"' in body
    assert shell.LIVE_VALIDATE_SCRIPT in body


def test_the_editor_page_shows_both_lists(client, state) -> None:
    draft = server.new_draft(state, title="edit")
    server.save_draft(
        state,
        draft.draft_id,
        policies=[
            Policy(
                action_type="a.b",
                tier=Tier.CONFIRM,
                caps=Caps(eur_day="100"),
                bounds=Bounds(strict_params=False),
            )
        ],
    )
    body = client.get(f"/drafts/{draft.draft_id}/edit/a.b").text
    assert "The loader would refuse this" in body
    assert "Once in force, these rules will" in body
    assert forecast.FORECAST_NOTICE in body
