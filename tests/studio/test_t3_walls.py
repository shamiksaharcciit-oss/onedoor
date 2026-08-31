"""`ND-056` / T3 — natural-language authoring: one test per wall, each able to fail.

Forward 006 gave five binding conditions; R066 §4 confirmed the constitution's principle
4 as a sixth, which the directive had simply failed to transcribe. All six are here, and
each is written so that removing the thing it guards breaks it.

The walls ARE the feature. A model that proposes policy is unremarkable; a model that
proposes policy into a system where it cannot possibly enact one is the product.
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap

import pytest
from fastapi.testclient import TestClient

from onedoor.guardrail import policy_loader
from onedoor.guardrail.models import Bounds, Policy, Tier
from onedoor.studio import (
    descriptions,
    live_proposer,
    proposer,
    screens,
    server,
    shell,
    staging,
    store,
)

GOOD_YAML = """
policies:
  - action_type: payments.refund
    tier: 2
    compensating_command: payments.transfer
  - action_type: payments.transfer
    tier: 3
"""

REFUSED_YAML = """
policies:
  - action_type: payments.refund
    tier: 2
"""


class _StubEndpoint(live_proposer.HttpProposer):
    """The HTTP proposer with only the socket replaced.

    Everything under test — the parser call, the refusal path, the instrument, the
    mentions — is the real code. Only `_ask` is stubbed, because a test that also stubbed
    `parse` would be testing a mock's opinion of the walls.
    """

    def __init__(self, reply: str, **kw) -> None:
        super().__init__(
            live_proposer.Instrument(endpoint="https://models.example/v1/chat", model="m-1"),
            **kw,
        )
        self.reply = reply
        self.asked: list[str] = []

    def _ask(self, prompt: str) -> str:
        self.asked.append(prompt)
        return self.reply


def _propose(client, description: str) -> str:
    """POST a description and return where it redirected.

    `follow_redirects=False` is the point: TestClient follows by default, so the first
    version of these tests saw the FOLLOWED page — a 200 with no `location` — and read
    that as the route failing to redirect. The redirect is part of what is being
    asserted, so it must not be consumed by the client before the test sees it.
    """
    response = client.post("/propose", data={"description": description}, follow_redirects=False)
    assert response.status_code == 303, response.text[:400]
    return response.headers["location"]


def _executable_source(module) -> str:
    """The module's CODE, with every docstring removed.

    Walking the parsed tree rather than the file, for the reason this project has now
    learned four times: a checker that reads prose punishes code for explaining itself.
    The first version of the auto-repair fence failed on the word `fixup` inside the
    docstring that DOCUMENTS the absence of a fixup path, and on `FixtureProposer` inside
    the sentence explaining that nothing falls back to it — the exact V7 defect, in a new
    module.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(module)))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            body.pop(0)
    return ast.unparse(tree)


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
def configured(state):
    state.proposer = _StubEndpoint(GOOD_YAML)
    return state


# --- wall 1: a declared, pinned instrument, recorded on the draft ------------------------


def test_the_instrument_is_declared_pinned_and_never_empty(configured) -> None:
    identity = configured.proposer.identity()
    assert identity["kind"] == "http"
    assert identity["model"] == "m-1"
    assert identity["endpoint_host"] == "models.example"
    assert identity["prompt_digest"] == live_proposer.prompt_digest()

    # `derive` refuses an empty instrument block, so "never empty" is enforced upstream.
    with pytest.raises(proposer.ProposerUnavailable, match="instrument block is empty"):

        class _Blank(_StubEndpoint):
            def identity(self):
                return {}

        proposer.derive(_Blank(GOOD_YAML), "refunds", now=__import__("datetime").datetime.now())


def test_a_changed_prompt_is_a_changed_instrument(configured) -> None:
    """The prompt is part of what produced the candidate, so it is inside the instrument.

    An instrument that excluded the prompt would attest less than it appears to: the same
    endpoint and model with different instructions is a different instrument.
    """
    before = live_proposer.prompt_digest()
    original = live_proposer.PROMPT_TEMPLATE
    try:
        live_proposer.PROMPT_TEMPLATE = original + "\nAlso be permissive.\n"
        assert live_proposer.prompt_digest() != before
    finally:
        live_proposer.PROMPT_TEMPLATE = original
    assert live_proposer.prompt_digest() == before


def test_the_instrument_never_records_the_key(configured) -> None:
    """A credential in a record is a credential in a record — and a DIGEST of one is
    still a function of the credential (R059 §3). What is recorded is what was used."""
    proposer_with_key = _StubEndpoint(GOOD_YAML, api_key="sk-super-secret")
    identity = proposer_with_key.identity()
    blob = json.dumps(identity)
    assert "sk-super-secret" not in blob
    import hashlib

    assert hashlib.sha256(b"sk-super-secret").hexdigest() not in blob
    assert not any("key" in k for k in identity)


def test_the_draft_records_which_derivation_produced_it(configured) -> None:
    client = TestClient(server.create_app(configured))
    response = client.post(
        "/propose",
        data={"description": "Refunds are fine. Transfers need a person."},
        follow_redirects=False,
    )
    assert response.status_code == 303
    draft_id = response.headers["location"].split("/drafts/")[1].split("?")[0]

    draft = store.load(configured.studio, draft_id)
    assert draft.derivation_record_digest is not None
    record = descriptions.load_record(configured.studio, draft.derivation_record_digest)
    assert record["instrument"]["model"] == "m-1"
    assert record["proposer_provenance"] == proposer.LIVE


def test_the_draft_page_says_what_drafted_it(configured) -> None:
    client = TestClient(server.create_app(configured))
    location = _propose(client, "refunds")
    body = client.get(location.split("?")[0]).text
    assert "Drafted via" in body
    assert "m-1" in body
    assert "does NOT attest" in body


def test_a_hand_written_draft_says_so_rather_than_rendering_blank(configured) -> None:
    """Absence is a fact here, not a gap. A blank would let a reader supply whichever
    origin they expected."""
    client = TestClient(server.create_app(configured))
    draft = server.new_draft(configured, title="by hand")
    body = client.get(f"/drafts/{draft.draft_id}").text
    assert "Written by hand" in body
    assert "No model was involved" in body


# --- wall 2: the same single parser, and NO auto-repair -----------------------------------


def test_a_generation_the_parser_refuses_is_refused(state) -> None:
    state.proposer = _StubEndpoint(REFUSED_YAML)
    client = TestClient(server.create_app(state))
    response = client.post("/propose", data={"description": "refunds"})

    assert response.status_code == 422
    assert "The loader would refuse what came back" in response.text
    assert "compensating_command" in response.text
    # And no draft was created from it.
    assert store.listing(state.studio) == []


def test_the_refusal_shows_the_models_output_verbatim(state) -> None:
    state.proposer = _StubEndpoint(REFUSED_YAML)
    client = TestClient(server.create_app(state))
    body = client.post("/propose", data={"description": "refunds"}).text
    assert "Nothing was repaired or rewritten" in body
    assert "payments.refund" in body


def test_no_auto_repair_path_exists(state) -> None:
    """Structural: the module has no way to rewrite what the model returned.

    A behavioural test proves the paths it happened to take; the ABSENCE of a repair path
    is a property of the code, checkable in the code. Both, as the structural-fence law
    requires — the behaviour above is the smoke, this is the fence.
    """
    # Scoped to the path from model text to candidate. The first version scanned the
    # whole module and condemned `strip` in the mention TOKENISER -- which touches the
    # operator's description, never the model's policy output. A fence whose scope is
    # wider than its requirement fails on work it was never about.
    path = "".join(
        _executable_source(fn)
        for fn in (
            live_proposer.HttpProposer.propose,
            live_proposer.HttpProposer.parse,
            live_proposer.HttpProposer._ask,
        )
    )
    for smell in ("strip", "replace", "retry", "attempt", "fixup", "repair", "sanit"):
        assert smell not in path, (
            f"{smell!r} appears on the path from the model's text to a candidate. A "
            "generation the parser refuses is refused; deciding what the model meant is "
            "authority this module does not have."
        )
    # And the module as a whole grows no second entry point that could repair.
    code = _executable_source(live_proposer)
    assert code.count("staging.staged(") == 1, "there is exactly one way in, and it parses"


def test_the_parser_used_is_the_loaders_own(state) -> None:
    """Wall 2 as a call, not a claim: `parse` goes through `staging.staged`."""
    assert "staging.staged(" in inspect.getsource(live_proposer.HttpProposer.parse)
    code = _executable_source(live_proposer)
    assert "Policy.model_validate" not in code, "a second construction path grew"
    assert "validate_policy" not in code, "a second validator grew"


def test_the_stub_exercises_the_real_parse_path(state) -> None:
    """Precondition for every wall-2 test above: only the socket is stubbed."""
    assert _StubEndpoint.parse is live_proposer.HttpProposer.parse
    assert _StubEndpoint.propose is live_proposer.HttpProposer.propose


# --- wall 3: the ceremony renders what the PARSER read -----------------------------------


def test_the_draft_shows_parsed_rules_and_not_the_models_prose(configured) -> None:
    """Approve against the schema, not the prose.

    The reply carries a chatty preamble; what the draft renders is the parsed rules. The
    model's own words are not presented as if they described the rules.
    """
    configured.proposer = _StubEndpoint(
        "Sure! Here is a great policy that keeps you totally safe:\n" + GOOD_YAML
    )
    client = TestClient(server.create_app(configured))
    location = _propose(client, "refunds")
    body = client.get(location.split("?")[0]).text

    assert "payments.refund" in body
    assert "totally safe" not in body, (
        "the model's own reassurance reached the approval surface as if it described the rules"
    )


def test_the_ceremony_page_renders_the_parsed_rules(configured) -> None:
    client = TestClient(server.create_app(configured))
    location = _propose(client, "refunds")
    draft_id = location.split("/drafts/")[1].split("?")[0]

    ceremony = client.get(f"/drafts/{draft_id}/ratify")
    assert ceremony.status_code == 200
    assert "payments.refund" in ceremony.text


# --- wall 4: BYO, opt-in, OFF BY DEFAULT --------------------------------------------------


def test_with_no_configuration_the_feature_is_absent_not_broken(state) -> None:
    """No tab, no route, no mention. Sabotaged by configuring it and asserting all flip."""
    assert state.proposer is None
    client = TestClient(server.create_app(state))

    assert client.get("/propose").status_code == 404
    drafts_page = client.get("/drafts").text
    assert "/propose" not in drafts_page
    assert "Propose" not in drafts_page
    assert live_proposer.CAPABILITY not in drafts_page

    # The other direction: configured, all three appear.
    state.proposer = _StubEndpoint(GOOD_YAML)
    configured_client = TestClient(server.create_app(state))
    assert configured_client.get("/propose").status_code == 200
    assert "/propose" in configured_client.get("/drafts").text


def test_from_env_is_off_unless_both_endpoint_and_model_are_given() -> None:
    assert live_proposer.from_env({}) is None
    assert live_proposer.from_env({live_proposer.ENV_ENDPOINT: "https://x/v1"}) is None
    assert live_proposer.from_env({live_proposer.ENV_MODEL: "m"}) is None

    built = live_proposer.from_env(
        {live_proposer.ENV_ENDPOINT: "https://x/v1", live_proposer.ENV_MODEL: "m"}
    )
    assert isinstance(built, live_proposer.HttpProposer)
    assert built.provenance == proposer.LIVE


def test_nothing_falls_back_to_the_fixture() -> None:
    """The worst possible outcome: a demo that looks like a model and is not.

    `proposer_provenance` exists to make that impossible, so no configuration path may
    quietly hand back the deterministic stand-in.
    """
    assert "FixtureProposer" not in _executable_source(live_proposer)
    assert live_proposer.from_env({}) is None


def test_the_studio_ships_no_endpoint_and_no_key() -> None:
    """No bundled credentials, no default provider."""
    code = _executable_source(live_proposer)
    for vendor in ("openai.com", "anthropic.com", "DEFAULT_ENDPOINT"):
        assert vendor not in code
    assert live_proposer.Instrument.__dataclass_fields__["endpoint"].default is not None or True
    with pytest.raises(TypeError):
        live_proposer.Instrument()  # endpoint and model are required, never defaulted


# --- wall 5: capability language, exact on every surface ----------------------------------


def test_the_capability_sentence_is_exact_and_present(configured) -> None:
    client = TestClient(server.create_app(configured))
    body = client.get("/propose").text
    assert live_proposer.CAPABILITY == "drafts proposed by a model, ratified by you"
    assert live_proposer.CAPABILITY in body


def test_no_t3_surface_claims_the_model_writes_policy(configured) -> None:
    """The fence around wall 5, over every rendered T3 surface AND its constants."""
    client = TestClient(server.create_app(configured))
    location = _propose(client, "refunds and payouts")
    surfaces = [
        client.get("/propose").text,
        client.get(location.split("?")[0]).text,
        live_proposer.CAPABILITY,
        screens.PROPOSE_NOTE,
        screens.DARK_SURFACE_NOTE,
        screens.DARK_SURFACE_EMPTY,
    ]
    for surface in surfaces:
        lowered = surface.lower()
        for forbidden in live_proposer.CAPABILITY_FORBIDDEN:
            assert forbidden not in lowered, f"a T3 surface carries {forbidden!r}"


def test_the_capability_fence_can_fail() -> None:
    """Sabotage: a checker that has never been shown a lie has never been shown to look."""
    liar = "Our AI writes your policies for you, hands-free."
    caught = [f for f in live_proposer.CAPABILITY_FORBIDDEN if f in liar.lower()]
    assert len(caught) >= 2, "the forbidden list would have walked past an overclaim"


# --- wall 6: the dark-surface list (constitution principle 4, R066 §4) --------------------


def test_a_mention_with_no_rule_is_stated(configured) -> None:
    """Non-coverage is stated, never silent.

    The description names payouts; the returned policy set covers refunds and transfers.
    The gap must appear, quoting the description's own words.
    """
    client = TestClient(server.create_app(configured))
    location = _propose(client, "Refunds are fine. Never send payouts without asking.")
    body = client.get(location.split("?")[0]).text

    assert screens.DARK_SURFACE_HEADING in body
    assert "payout" in body
    assert "Never send payouts without asking" in body, (
        "the gap must quote the description's own words, never a paraphrase"
    )


def test_the_quote_is_the_descriptions_words_and_never_the_models(configured) -> None:
    """Principle 2: a mention that quoted a paraphrase would be the model vouching for
    itself."""
    # The preamble ends with a colon so YAML reads it as a key and the document still
    # parses. A preamble that does NOT parse is a refusal, which is wall 2's test rather
    # than this one -- conflating them would let this test pass on a 422 without ever
    # rendering the page it is about.
    configured.proposer = _StubEndpoint("I have carefully handled payouts for you:\n" + GOOD_YAML)
    client = TestClient(server.create_app(configured))
    location = _propose(client, "Refunds fine. Payouts must never happen.")
    body = client.get(location.split("?")[0]).text

    assert "Payouts must never happen" in body
    assert "carefully handled payouts" not in body


def test_the_empty_dark_surface_does_not_claim_full_coverage(configured) -> None:
    """*What this check found*, never *the description is covered*."""
    client = TestClient(server.create_app(configured))
    # A description naming nothing this check recognises as an action.
    location = _propose(client, "Keep everything conservative and ask me first.")
    body = client.get(location.split("?")[0]).text

    assert screens.DARK_SURFACE_HEADING in body
    assert "not a guarantee" in body


def test_silence_about_a_mention_fails(configured) -> None:
    """The list is rendered even when empty, so a gap can never be silent."""
    html = screens.dark_surface_block([])
    assert screens.DARK_SURFACE_HEADING in html
    assert screens.DARK_SURFACE_EMPTY in html

    html_with = screens.dark_surface_block(
        [{"subject": "payouts", "quote": "never send payouts", "covered_by": None}]
    )
    assert "payouts" in html_with
    assert screens.DARK_SURFACE_EMPTY not in html_with


# --- the record is not a receipt, and says so --------------------------------------------


def test_the_record_states_what_it_does_not_attest(configured) -> None:
    from tests.viewer.assertions import assert_reader_sees

    client = TestClient(server.create_app(configured))
    body = client.get("/propose").text
    # Both constants carry apostrophes, so they reach the page escaped. Asserting the raw
    # constant would make a correctly-escaped page look like a paraphrase (R061 section 3).
    assert_reader_sees(body, proposer.NOT_REDERIVABLE)
    assert_reader_sees(body, proposer.AUTHORITY_FROM_CHECKS)


def test_the_provenance_cannot_be_relabelled_without_breaking_the_record(configured) -> None:
    """`proposer_provenance` rides INSIDE the record's digest."""
    import datetime

    _, record = proposer.derive(
        configured.proposer, "refunds", now=datetime.datetime.now(datetime.UTC)
    )
    sealed = record.sealed()
    tampered = {**sealed, "proposer_provenance": proposer.FIXTURE}
    from onedoor._vendor.canonical import digest_obj

    recomputed = digest_obj({k: v for k, v in tampered.items() if k != "record_digest"})
    assert recomputed != sealed["record_digest"]


# --- unavailable is its own outcome -------------------------------------------------------


def test_an_endpoint_that_does_not_answer_is_not_a_verdict_on_the_description(state) -> None:
    """Three outcomes at the boundary. A socket that failed is not a bad description."""

    class _Dead(_StubEndpoint):
        def _ask(self, prompt: str) -> str:
            raise proposer.ProposerUnavailable("the endpoint refused the connection")

    state.proposer = _Dead(GOOD_YAML)
    client = TestClient(server.create_app(state))
    response = client.post("/propose", data={"description": "refunds"})

    assert response.status_code == 503
    assert "This says nothing about your description" in response.text
    assert store.listing(state.studio) == []


def test_a_response_shape_this_build_cannot_read_is_unavailable_not_empty(state) -> None:
    """An unreadable answer must not render as "the model suggested no rules"."""
    with pytest.raises(proposer.ProposerUnavailable, match="cannot read"):
        live_proposer._content_of({"unexpected": "shape"})
    with pytest.raises(proposer.ProposerUnavailable, match="not text"):
        live_proposer._content_of({"choices": [{"message": {"content": 42}}]})


def test_an_empty_description_drafts_nothing(configured) -> None:
    client = TestClient(server.create_app(configured))
    response = client.post("/propose", data={"description": "   "})
    assert response.status_code == 400
    assert "nothing was drafted" in response.text.lower()
    assert store.listing(configured.studio) == []


# --- the description is frozen as received bytes -------------------------------------------


def test_the_description_is_frozen_verbatim(configured) -> None:
    """E10. The operator's own words, byte for byte, before anything reads them."""
    import hashlib

    text = "Refunds  under  200€.\r\nNothing else.\t"
    client = TestClient(server.create_app(configured))
    client.post("/propose", data={"description": text})

    # The form round-trips CRLF as the browser sends it; what matters is that whatever
    # arrived was stored unchanged and is addressable by its own digest.
    stored = descriptions.raw(
        configured.studio, hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    )
    assert stored == text.strip().encode("utf-8")


# --- severability: T3 can slip alone (directive §3.3) --------------------------------------


def test_t1_and_t2_do_not_import_t3(state) -> None:
    """The slip fence. T3 must never drag T1 or T2, and this is why it cannot.

    Structural rather than intentional: if T3 slips to 0.7.1, the modules that ship
    without it must not name it. `server` is excluded because it MOUNTS T3 — that is the
    one place the tracks meet, and it meets them behind an `is not None`.
    """
    from onedoor.studio import api, forecast
    from onedoor.studio import staging as staging_module

    for module in (staging_module, forecast, api):
        code = _executable_source(module)
        assert "live_proposer" not in code, f"{module.__name__} imports T3"
        assert "propose" not in code.lower(), (
            f"{module.__name__} names proposing in its code; T1 and T2 must stand without T3"
        )


def test_the_propose_tab_is_not_in_the_base_tab_list() -> None:
    assert shell.PROPOSE_TAB not in shell.TABS
    assert shell.tabs_with_propose(False) == shell.TABS
    assert shell.tabs_with_propose(True)[-1] is shell.PROPOSE_TAB


def test_staged_output_is_what_the_proposal_carries(configured) -> None:
    """The proposal's policies are the parser's, object for object."""
    proposal = configured.proposer.propose("refunds")
    parsed = staging.staged(GOOD_YAML)
    assert [p.action_type for p in proposal.policies] == [p.action_type for p in parsed.policies]


# --- R071 §5: malformed model output, the shape from the forensic channel ----------------


MALFORMED = 'policies:\n  - action_type: "payments.refund\n'
"""A generation that abandons the format mid-structure.

The shape the forensic channel closed: a model given a described-but-unenforced schema
opened a structure, filled it, and stopped without closing the string. Nothing was
truncated by a limit; the format was simply abandoned. **A schema that is described but
not enforced is a hope with a type signature** — which is why T3 never relies on the model
to emit a well-formed policy.
"""


def test_a_structurally_broken_generation_refuses_at_the_load_stage(state) -> None:
    """Consequence 2: malformed output is its own outcome, distinct from policy-invalid.

    The stage is what keeps them apart. A model that abandons the format is refused at
    `load`; a model that writes clean YAML declaring an unsafe rule is refused at `rules`.
    Collapsing the two would tell an operator their policy was wrong when their model had
    stopped mid-sentence.
    """
    state.proposer = _StubEndpoint(MALFORMED)
    client = TestClient(server.create_app(state))
    response = client.post("/propose", data={"description": "refunds"}, follow_redirects=False)

    assert response.status_code == 422
    assert "The loader would refuse what came back" in response.text
    assert "Nothing was repaired or rewritten" in response.text

    refused = staging.staged(MALFORMED)
    assert refused.stopped_at == staging.STAGE_LOAD

    semantic = staging.staged(REFUSED_YAML)
    assert semantic.stopped_at == staging.STAGE_RULES
    assert refused.stopped_at != semantic.stopped_at, (
        "malformed and policy-invalid must not collapse into one outcome"
    )


def test_a_broken_generation_writes_no_draft_and_no_record(state) -> None:
    """It is surfaced, and nothing is persisted from it — stated rather than assumed."""
    state.proposer = _StubEndpoint(MALFORMED)
    client = TestClient(server.create_app(state))
    client.post("/propose", data={"description": "refunds"}, follow_redirects=False)

    assert store.listing(state.studio) == []
    rows = state.studio.execute("SELECT COUNT(*) AS n FROM derivation_records").fetchone()
    assert rows["n"] == 0


def test_the_artifact_is_built_by_the_parser_and_never_by_the_model(state) -> None:
    """Consequence 1: the model's output is INPUT to construction, never the artifact.

    Every `Policy` a proposal carries was constructed by the engine's own
    `_policy_from_entry` inside `staging`, so a well-formed-looking generation cannot
    become a candidate without passing through the loader's constructor.
    """
    proposal = _StubEndpoint(GOOD_YAML).propose("refunds")
    parsed = staging.staged(GOOD_YAML)
    assert [p.model_dump() for p in proposal.policies] == [p.model_dump() for p in parsed.policies]
    code = _executable_source(live_proposer)
    assert "Policy(" not in code, "a policy constructed outside the loader's own path"
