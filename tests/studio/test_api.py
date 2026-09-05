"""`ND-056` / T2 — the policy REST API, and the wall it must not cross.

The load-bearing test is `test_submit_is_not_approval`. Everything else here is CRUD
worth having; that one is the reason the API is allowed to exist at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, CheckId, Policy, Tier
from onedoor.studio import api, server, store

RULE = {
    "action_type": "payments.transfer",
    "tier": 2,
    "compensating_command": "payments.refund",
    "bounds": {"strict_params": False},
}


@pytest.fixture
def state(tmp_path):
    st = server.open_state(str(tmp_path / "onedoor.db"), str(tmp_path / "studio.db"))
    policy_loader.upsert(
        st.enforcer,
        Policy(action_type="seed.action", tier=Tier.CONFIRM, bounds=Bounds(strict_params=False)),
    )
    policy_loader.record_snapshot(st.enforcer)
    return st


@pytest.fixture
def client(state):
    return TestClient(server.create_app(state))


# --- the wall ---------------------------------------------------------------------------


def test_submit_is_not_approval(client, state) -> None:
    """Submitting asks a human. It approves nothing, and this proves all three halves.

    Sabotaged on its own premise: the ceremony is shown to be ABLE to move the version
    pointer, so "nothing moved" is a fact about `submit` rather than a fact about a
    fixture that could never have moved anything.
    """
    created = client.post(api.API_ROOT + "/drafts", json={"title": "t", "rules": [RULE]})
    draft_id = created.json()["draft_id"]

    before_version = policy_loader.current_version(state.enforcer)
    before_ratifications = state.enforcer.execute(
        "SELECT COUNT(*) AS n FROM ratifications"
    ).fetchone()["n"]

    response = client.post(f"{api.API_ROOT}/drafts/{draft_id}/submit")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == store.SUBMITTED
    assert body["means"] == api.SUBMIT_MEANS
    assert body["ceremony_url"] == f"/drafts/{draft_id}/ratify"

    # 1. The version pointer did not move.
    assert policy_loader.current_version(state.enforcer) == before_version
    # 2. No receipt was written.
    after = state.enforcer.execute("SELECT COUNT(*) AS n FROM ratifications").fetchone()["n"]
    assert after == before_ratifications
    # 3. The rules in force are untouched.
    assert {
        str(r["action_type"]) for r in state.enforcer.execute("SELECT action_type FROM policies")
    } == {"seed.action"}

    # The premise: the ceremony CAN move all of that, so the assertions above mean
    # something. Without this, a fixture that could never ratify would pass them all.
    outcome = server.ratify_draft(state, draft_id, session="a person at the keyboard")
    assert outcome.ratified is True
    assert policy_loader.current_version(state.enforcer) != before_version


def test_the_api_offers_no_route_that_ratifies(client) -> None:
    """Structural: no path under /api/v1 mentions ratifying.

    Read off the app's own route table, not off a list this test remembers — R064 §2:
    *an app's surface is what the server serves, not what the project remembers writing.*
    """
    app = client.app
    api_paths = [r.path for r in app.routes if str(getattr(r, "path", "")).startswith(api.API_ROOT)]
    assert api_paths, "precondition: the API is mounted"
    for path in api_paths:
        assert "ratify" not in path, f"{path} is an approval route under the v1 API"


def test_the_documented_sentence_is_the_ruled_one_and_is_true(client) -> None:
    """R066 §1's wording, and the fact that makes it shippable.

    The sentence says the v1 API adds no approval route AND that one legacy route still
    serves. Both halves are checked here, because a sentence that was true about only
    one half would be the false-sentence-about-approval delivery refused to ship.
    """
    schema = client.get(api.OPENAPI_PATH).json()
    assert schema["info"]["description"] == api.NO_APPROVAL_NOTE
    assert "adds no approval route" in api.NO_APPROVAL_NOTE
    assert "POST /draft/{id}/ratify" in api.NO_APPROVAL_NOTE
    assert "declared, never authenticated" in api.NO_APPROVAL_NOTE

    served = [str(getattr(r, "path", "")) for r in client.app.routes]
    assert "/draft/{draft_id}/ratify" in served, (
        "the sentence says a legacy route still serves; if it does not, the sentence is "
        "no longer true and must change before this ships"
    )


# --- C1's two teeth: the witness test and the deprecation field --------------------------


def test_the_legacy_ratify_route_behaves_exactly_as_it_does_today(client, state) -> None:
    """The WITNESS (R066 §1). Its retirement must be deliberate, never silent.

    This pins the shape a caller depends on: the path, the query parameter, the sealed
    receipt's keys, and the recorded approver. When the actor-identity work retires this
    route, this test fails and someone has to decide — which is the whole point.
    """
    created = client.post(api.API_ROOT + "/drafts", json={"title": "t", "rules": [RULE]})
    draft_id = created.json()["draft_id"]

    response = client.post(f"/draft/{draft_id}/ratify", params={"session": "desk-1"})
    assert response.status_code == 200
    body = response.json()

    # The receipt is unchanged: the digest covers exactly what it always covered.
    assert "ratification_digest" in body
    assert body["ratified_by_session"] == "desk-1"
    assert body["to_version"] == policy_loader.current_version(state.enforcer)


def test_the_legacy_route_declares_its_own_deprecation(client) -> None:
    """A caller is told what this is BY THE THING ITSELF, not by docs they never read."""
    created = client.post(api.API_ROOT + "/drafts", json={"title": "t", "rules": [RULE]})
    draft_id = created.json()["draft_id"]

    body = client.post(f"/draft/{draft_id}/ratify", params={"session": "desk-1"}).json()
    assert body["deprecation"] == api.LEGACY_DEPRECATION
    assert body["deprecation"]["status"] == "deprecated"
    assert "declared" in body["deprecation"]["why"]
    assert "ceremony" in body["deprecation"]["instead"]


def test_the_deprecation_notice_sits_beside_the_receipt_and_not_inside_it(client, state) -> None:
    """Beside, never merged: the sealed receipt's digest covers exactly its own fields.

    Folding a notice into the receipt would change what the digest is over. Corrections
    annotate evidence; they do not rewrite it — the beside-not-into doctrine, applied to
    a JSON body instead of a palette.
    """
    created = client.post(api.API_ROOT + "/drafts", json={"title": "t", "rules": [RULE]})
    draft_id = created.json()["draft_id"]
    body = client.post(f"/draft/{draft_id}/ratify", params={"session": "d"}).json()

    receipt = {k: v for k, v in body.items() if k != "deprecation"}
    assert "deprecation" not in receipt

    # The row the enforcer actually sealed, addressed by the digest the response gave.
    # Selecting the named columns rather than the whole record, per the standing rule.
    stored = state.enforcer.execute(
        "SELECT ratification_digest, body_json FROM ratifications WHERE ratification_digest=?",
        (receipt["ratification_digest"],),
    ).fetchone()
    assert stored is not None, "the response's digest must address a row that exists"

    # The sealed body carries no trace of the annotation. If `deprecation` had been
    # folded in, it would be inside what the digest is over.
    import json

    assert "deprecation" not in json.loads(stored["body_json"])
    assert "deprecation" not in stored["body_json"]


# --- CRUD ---------------------------------------------------------------------------------


def test_create_read_list_and_delete(client) -> None:
    created = client.post(api.API_ROOT + "/drafts", json={"title": "mine", "rules": [RULE]})
    assert created.status_code == 201
    draft_id = created.json()["draft_id"]
    assert created.json()["title"] == "mine"
    assert created.json()["state"] == store.DRAFT
    assert [r["action_type"] for r in created.json()["rules"]] == ["payments.transfer"]

    got = client.get(f"{api.API_ROOT}/drafts/{draft_id}")
    assert got.status_code == 200
    assert got.json()["draft_id"] == draft_id

    listed = client.get(api.API_ROOT + "/drafts").json()
    assert draft_id in [d["draft_id"] for d in listed["drafts"]]

    gone = client.delete(f"{api.API_ROOT}/drafts/{draft_id}")
    assert gone.status_code == 200
    assert client.get(f"{api.API_ROOT}/drafts/{draft_id}").status_code == 404


def test_put_a_rule_keeps_every_other_rule(client) -> None:
    """R063 §4 at the API: a partial write must not delete what it never named."""
    other = {**RULE, "action_type": "payments.refund", "compensating_command": "payments.transfer"}
    created = client.post(api.API_ROOT + "/drafts", json={"rules": [RULE, other]})
    draft_id = created.json()["draft_id"]

    updated = client.put(
        f"{api.API_ROOT}/drafts/{draft_id}/rules/payments.transfer",
        json={**RULE, "tier": 3},
    )
    assert updated.status_code == 200
    by_action = {r["action_type"]: r for r in updated.json()["rules"]}
    assert set(by_action) == {"payments.transfer", "payments.refund"}
    assert by_action["payments.transfer"]["tier"] == 3
    assert by_action["payments.refund"]["compensating_command"] == "payments.transfer"


def test_put_a_rule_adds_it_when_the_draft_does_not_have_it(client) -> None:
    # A new draft opens from the ACTIVE set, so it already carries `seed.action`. Adding
    # a rule must leave that one alone -- which is the same law as the test above, met
    # from the adding side rather than the updating side.
    created = client.post(api.API_ROOT + "/drafts", json={})
    draft_id = created.json()["draft_id"]
    assert [r["action_type"] for r in created.json()["rules"]] == ["seed.action"]

    added = client.put(f"{api.API_ROOT}/drafts/{draft_id}/rules/payments.transfer", json=RULE)
    assert added.status_code == 200
    assert sorted(r["action_type"] for r in added.json()["rules"]) == [
        "payments.transfer",
        "seed.action",
    ]


def test_delete_a_rule_that_is_not_there_is_an_absence(client) -> None:
    created = client.post(api.API_ROOT + "/drafts", json={})
    draft_id = created.json()["draft_id"]
    response = client.delete(f"{api.API_ROOT}/drafts/{draft_id}/rules/nope")
    assert response.status_code == 404
    assert response.json()["reason"] == api.NO_SUCH_RULE


def test_editing_a_submitted_draft_returns_it_to_draft(client) -> None:
    """A submission is about a specific candidate; changing it un-asks the question."""
    created = client.post(api.API_ROOT + "/drafts", json={"rules": [RULE]})
    draft_id = created.json()["draft_id"]
    assert client.post(f"{api.API_ROOT}/drafts/{draft_id}/submit").json()["state"] == "submitted"

    edited = client.put(f"{api.API_ROOT}/drafts/{draft_id}/rules/payments.transfer", json=RULE)
    assert edited.json()["state"] == store.DRAFT


# --- typed refusals -----------------------------------------------------------------------


def test_every_refusal_reason_maps_to_a_status(client) -> None:
    assert set(api.STATUS_FOR) == set(api.REASONS), "a reason with no status is unrenderable"


def test_an_unknown_draft_is_404_with_a_typed_reason(client) -> None:
    response = client.get(f"{api.API_ROOT}/drafts/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["reason"] == api.NO_SUCH_DRAFT


def test_a_candidate_the_loader_refuses_is_422_carrying_the_staged_reasons(client) -> None:
    """422, not 409: the rules are wrong, which is a different fact from the world moving."""
    created = client.post(api.API_ROOT + "/drafts", json={})
    draft_id = created.json()["draft_id"]
    # Tier 2 with no compensating_command -- validate_policy's own refusal.
    response = client.put(
        f"{api.API_ROOT}/drafts/{draft_id}/rules/a.b",
        json={"action_type": "a.b", "tier": 2},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["reason"] == api.CANDIDATE_REFUSED
    assert any("compensating_command" in r["message"] for r in body["refusals"])
    assert body["incomplete_notice"]


def test_a_body_that_is_not_json_is_400(client) -> None:
    created = client.post(api.API_ROOT + "/drafts", json={})
    draft_id = created.json()["draft_id"]
    response = client.put(
        f"{api.API_ROOT}/drafts/{draft_id}/rules/a.b",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["reason"] == api.MALFORMED_REQUEST


def test_a_renaming_body_is_refused_rather_than_guessed(client) -> None:
    created = client.post(api.API_ROOT + "/drafts", json={})
    draft_id = created.json()["draft_id"]
    response = client.put(
        f"{api.API_ROOT}/drafts/{draft_id}/rules/a.b",
        json={**RULE, "action_type": "something.else"},
    )
    assert response.status_code == 400
    assert "rename is a different act" in response.json()["message"]


def test_submitting_twice_is_409(client) -> None:
    created = client.post(api.API_ROOT + "/drafts", json={"rules": [RULE]})
    draft_id = created.json()["draft_id"]
    assert client.post(f"{api.API_ROOT}/drafts/{draft_id}/submit").status_code == 200
    again = client.post(f"{api.API_ROOT}/drafts/{draft_id}/submit")
    assert again.status_code == 409
    assert again.json()["reason"] == api.ALREADY_SUBMITTED


def test_submitting_a_stale_draft_is_409_and_says_which_versions(client, state) -> None:
    created = client.post(api.API_ROOT + "/drafts", json={"rules": [RULE]})
    draft_id = created.json()["draft_id"]

    # Move the world underneath the draft.
    policy_loader.upsert(
        state.enforcer,
        Policy(action_type="new.action", tier=Tier.CONFIRM, bounds=Bounds(strict_params=False)),
    )

    response = client.post(f"{api.API_ROOT}/drafts/{draft_id}/submit")
    assert response.status_code == 409
    body = response.json()
    assert body["reason"] == api.BASE_MOVED
    assert body["base_version"] != body["active_version"]


# --- the validation route -----------------------------------------------------------------


def test_the_validation_route_returns_both_lists_separately(client) -> None:
    """Two keys, for the same reason there are two panels."""
    created = client.post(
        api.API_ROOT + "/drafts",
        json={"rules": [{"action_type": "a.b", "tier": 3, "caps": {"eur_day": "100"}}]},
    )
    draft_id = created.json()["draft_id"]
    body = client.get(f"{api.API_ROOT}/drafts/{draft_id}/validation").json()

    assert body["loads"] is True
    assert body["refusals"] == []
    codes = {f["reason_code"] for f in body["forecasts"]}
    assert CheckId.COST_UNKNOWN.value in codes
    assert body["forecast_notice"]


def test_the_validation_route_notice_is_true_beside_a_refusal(client, state) -> None:
    """R092 F-D1, witnessed exactly where core witnessed it: a refused rule still
    forecast, and the notice must stop claiming universal acceptance the moment the
    refusals list is not empty.

    `POST /drafts` refuses an invalid candidate outright (422, no draft made) — the
    guard T2's own test above already covers — so a draft that HOLDS a refused rule is
    built directly, the shape fix B's upload path produces, and the shape core actually
    witnessed this on."""
    draft = server.new_draft(state, title="refused")
    server.save_draft(
        state,
        draft.draft_id,
        policies=[Policy(action_type="payments.transfer", tier=Tier(2), dry_run=False)],
    )
    body = client.get(f"{api.API_ROOT}/drafts/{draft.draft_id}/validation").json()

    assert body["loads"] is False
    assert body["refusals"], "precondition: this candidate is refused"
    assert body["forecasts"], "precondition: the refused rule is still forecast"
    assert "accepts every rule below" not in body["forecast_notice"]
    assert "refused above" in body["forecast_notice"]


def test_the_validation_route_names_the_reason_codes(client) -> None:
    created = client.post(
        api.API_ROOT + "/drafts",
        json={"rules": [{"action_type": "a.b", "tier": 3}]},
    )
    draft_id = created.json()["draft_id"]
    body = client.get(f"{api.API_ROOT}/drafts/{draft_id}/validation").json()
    known = {c.value for c in CheckId}
    for item in body["forecasts"]:
        assert item["reason_code"] in known


# --- queries -------------------------------------------------------------------------------


def test_policies_are_read_from_the_snapshot_the_version_names(client, state) -> None:
    """R058 §1, sabotaged: a divergent live row must not move the answer."""
    before = client.get(api.API_ROOT + "/policies").json()
    assert [p["action_type"] for p in before["policies"]] == ["seed.action"]
    assert before["retrievable"] is True

    # Write straight into the live table without recording a snapshot.
    state.enforcer.execute("UPDATE policies SET tier=? WHERE action_type=?", (1, "seed.action"))
    after = client.get(api.API_ROOT + "/policies").json()
    assert after["version"] == before["version"]
    assert after["policies"] == before["policies"], (
        "the API answered from live tables; the digest in its own answer names a "
        "snapshot, so the snapshot is the only honest source"
    )


def test_a_policy_that_is_not_declared_is_a_named_absence(client) -> None:
    response = client.get(f"{api.API_ROOT}/policies/nope")
    assert response.status_code == 404
    assert response.json()["reason"] == api.NO_SUCH_RULE
    assert "default-deny" in response.json()["message"]


def test_versions_lists_what_the_store_holds(client) -> None:
    body = client.get(api.API_ROOT + "/versions").json()
    assert body["active_version"]
    assert body["active_version"] in [v["version_hash"] for v in body["versions"]]
    assert all(v["created_at"] for v in body["versions"])


# --- the schema is published, the HTML doc pages are not -----------------------------------


def test_the_openapi_schema_is_served_and_the_doc_pages_are_not(client) -> None:
    assert client.get(api.OPENAPI_PATH).status_code == 200
    for cdn_page in ("/docs", "/redoc"):
        assert client.get(cdn_page).status_code == 404, (
            f"{cdn_page} is back; it is what pulled Swagger, ReDoc, fonts and a favicon "
            "from CDNs and made the header's promise false"
        )


def test_the_published_schema_names_no_host_but_this_machine(client) -> None:
    """The header's promise, applied to the schema — as the requirement, not a proxy.

    The blunt version of this check (`"//" not in text`) failed, and it was RIGHT to
    fail and WRONG about why: the schema embeds route docstrings, and one of them tells
    an operator to open `http://127.0.0.1:8787`. That is this machine, in prose, in a
    description — not an origin anything fetches.

    So the requirement is stated instead of approximated: every host named anywhere in
    the published schema is loopback. A URL that would take a reader off this box is the
    thing that matters, and a substring of a sentence is not.
    """
    import ipaddress
    import re

    text = client.get(api.OPENAPI_PATH).text
    hosts = re.findall(r"https?://([^/\s\"'`)]+)", text)
    assert hosts, "precondition: the schema does mention at least one URL"
    for host in hosts:
        name = host.split(":")[0]
        if name == "localhost":
            continue
        assert ipaddress.ip_address(name).is_loopback, (
            f"the published schema names {host!r}, which is not this machine"
        )


def test_the_published_schema_pulls_in_no_assets(client) -> None:
    """Whatever it names in prose, the schema must not carry a fetchable reference."""
    text = client.get(api.OPENAPI_PATH).text
    for marker in ('"src"', "<script", "<link", "cdn.jsdelivr.net", "fonts.googleapis.com"):
        assert marker not in text, f"the published schema carries {marker}"


def test_the_schema_marks_the_legacy_route_deprecated(client) -> None:
    schema = client.get(api.OPENAPI_PATH).json()
    legacy = schema["paths"]["/draft/{draft_id}/ratify"]["post"]
    assert legacy.get("deprecated") is True
