"""The proposer, its record, and the law it must not be able to dodge (S6, T1–T3, T7).

R053's expected standing lives here and next door in `tests/viewer/test_proposal.py`:
`proposer_provenance` hashed and rendering-surviving, the derivation record's face
statements in place, the E10 description discipline, and **T7's no-privileged-path law** —
a proposed candidate passes every check a hand-written one passes, and R027's rule about
the generator finally has a generator to bind.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from onedoor._vendor.canonical import digest_obj
from onedoor.guardrail import policy_loader
from onedoor.studio import backtest, coverage, descriptions, proposer, ratify, store
from onedoor.studio import validate as validate_module

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
DESCRIPTION = "We issue refunds to customers and post webhooks to our payment partner."


@pytest.fixture
def studio(tmp_path: Path) -> sqlite3.Connection:
    conn = store.open_store(tmp_path / "studio.db")
    yield conn
    conn.close()


def _derive(description: str = DESCRIPTION):
    return proposer.derive(proposer.FixtureProposer(), description, now=NOW)


# --- T1: the interface, and the stand-in that labels itself -----------------------


def test_the_fixture_proposer_satisfies_the_protocol() -> None:
    assert isinstance(proposer.FixtureProposer(), proposer.Proposer)


def test_the_same_description_gives_the_same_candidate() -> None:
    """Determinism is what makes the fixture path usable in CI at all."""
    first, first_record = _derive()
    second, second_record = _derive()
    assert first.policy_digest() == second.policy_digest()
    assert first_record.digest() == second_record.digest()


def test_the_instrument_block_is_never_empty(_unused: None = None) -> None:
    """R053 §2: a fixture records its identity as a model records its id."""
    identity = proposer.FixtureProposer().identity()
    assert identity
    for key in ("kind", "name", "version", "rules_digest", "pack_digest"):
        assert identity[key], f"the instrument block omits {key}"


def test_a_proposer_with_an_empty_instrument_is_refused() -> None:
    """An unrecorded instrument is an unrecorded derivation."""

    class Anonymous:
        provenance = proposer.FIXTURE

        def identity(self) -> dict:
            return {}

        def propose(self, description: str) -> proposer.Proposal:
            return proposer.Proposal(policies=[])

    with pytest.raises(proposer.ProposerUnavailable) as caught:
        proposer.derive(Anonymous(), DESCRIPTION, now=NOW)
    assert "instrument block is empty" in str(caught.value)


def test_an_unknown_provenance_is_refused() -> None:
    class Odd:
        provenance = "simulated"

        def identity(self) -> dict:
            return {"kind": "odd"}

        def propose(self, description: str) -> proposer.Proposal:
            return proposer.Proposal(policies=[])

    with pytest.raises(proposer.ProposerUnavailable):
        proposer.derive(Odd(), DESCRIPTION, now=NOW)


def test_there_is_no_silent_fallback_to_the_fixture() -> None:
    """A demo that looks like a model and is not is what the label exists to prevent."""
    with pytest.raises(proposer.ProposerUnavailable) as caught:
        proposer.live_proposer()
    assert "falls back to the fixture silently" in str(caught.value)


# --- T3: the record, and what it refuses to claim ---------------------------------


def test_the_record_says_it_is_not_re_derivable() -> None:
    _, record = _derive()
    sealed = record.sealed()
    assert sealed["not_rederivable"] == proposer.NOT_REDERIVABLE
    assert "does NOT" in sealed["not_rederivable"]
    assert sealed["authority"] == proposer.AUTHORITY_FROM_CHECKS
    assert "provenance, not trust" in sealed["authority"]


def test_the_record_is_not_called_a_receipt() -> None:
    """R053 §1: principle 5 was amended rather than stretched, and the noun changed."""
    assert proposer.SCHEMA == "onedoor/derivation-record/1"
    assert "receipt" not in proposer.SCHEMA


def test_proposer_provenance_is_inside_the_records_digest() -> None:
    """B5's sabotage shape: relabelling breaks the record's own address."""
    _, record = _derive()
    sealed = record.sealed()
    assert sealed["proposer_provenance"] == proposer.FIXTURE

    forged = {**sealed, "proposer_provenance": proposer.LIVE}
    body = {k: v for k, v in forged.items() if k != "record_digest"}
    assert digest_obj(body) != forged["record_digest"], (
        "a fixture-drafted candidate relabelled as a model's work kept its digest"
    )


def test_the_value_pair_is_the_same_one_the_ledger_label_uses() -> None:
    """R053 §2: a renderer must not learn a second dialect for one distinction."""
    assert (proposer.LIVE, proposer.FIXTURE) == (backtest.LIVE, backtest.FIXTURE)


def test_the_record_cites_the_candidate_by_the_existing_digest() -> None:
    proposal, record = _derive()
    assert record.policy_digest == backtest.policy_digest(proposal.policies)


# --- T2: the description is received data ------------------------------------------


def test_a_description_is_stored_byte_for_byte(studio: sqlite3.Connection) -> None:
    """E10. No stripping, no normalising, no line-ending translation."""
    awkward = "  Refunds.\r\n\tAnd webhooks.  \n\n"
    digest = descriptions.freeze(studio, awkward, now=NOW)
    assert descriptions.raw(studio, digest) == awkward.encode("utf-8")
    assert descriptions.load(studio, digest) == awkward


def test_the_stored_digest_is_over_the_stored_bytes(studio: sqlite3.Connection) -> None:
    """The tie between a record and its input is exactly this equality."""
    import hashlib

    awkward = "Refunds.\r\n  Webhooks. Trailing space. "
    digest = descriptions.freeze(studio, awkward, now=NOW)
    stored = descriptions.raw(studio, digest)
    assert stored is not None
    assert hashlib.sha256(stored).hexdigest() == digest


def test_two_descriptions_differing_only_in_whitespace_are_different(
    studio: sqlite3.Connection,
) -> None:
    """If they collided, a normalising step would be invisible instead of impossible."""
    a = descriptions.freeze(studio, "Refunds.\n", now=NOW)
    b = descriptions.freeze(studio, "Refunds.\r\n", now=NOW)
    assert a != b


def test_freezing_the_same_description_twice_stores_one_row(
    studio: sqlite3.Connection,
) -> None:
    descriptions.freeze(studio, DESCRIPTION, now=NOW)
    descriptions.freeze(studio, DESCRIPTION, now=NOW)
    assert studio.execute("SELECT COUNT(*) AS n FROM descriptions").fetchone()["n"] == 1


def test_derivation_records_are_append_only(studio: sqlite3.Connection) -> None:
    _, record = _derive()
    descriptions.store_record(studio, record, now=NOW)
    with pytest.raises(sqlite3.IntegrityError):
        studio.execute("UPDATE derivation_records SET proposer_provenance='live'")
    with pytest.raises(sqlite3.IntegrityError):
        studio.execute("DELETE FROM derivation_records")


def test_lineage_resolves_by_recomputation_not_by_a_pointer(
    studio: sqlite3.Connection, fresh: sqlite3.Connection
) -> None:
    """A ratification's `candidate_digest` IS the proposal's `policy_digest`.

    So *"where did the policy I ratified come from?"* is a query over the digest both
    sides already carry — no stored pointer between the two stores, and no schema change.
    """
    proposal, record = _derive()
    descriptions.freeze(studio, DESCRIPTION, now=NOW)
    descriptions.store_record(studio, record, now=NOW)

    receipt = ratify.ratify(
        fresh,
        proposal.policies,
        effects=proposal.effects,
        expected_version=policy_loader.current_version(fresh),
        ratified_by_session="operator-1",
        now=NOW,
    )
    found = descriptions.records_for_policy(studio, receipt.candidate_digest)
    assert len(found) == 1
    assert found[0]["record_digest"] == record.digest()


# --- T7: no privileged path -------------------------------------------------------


def test_a_proposed_candidate_passes_the_engines_own_validator() -> None:
    """R027's rule finally binds a generator: the generated set gets no exemption."""
    proposal, _ = _derive()
    assert proposal.policies, "the fixture proposed nothing; the test would be vacuous"
    assert validate_module.problems(proposal.policies, proposal.effects) == []


def test_a_proposed_candidate_names_no_effect_it_does_not_declare(
    fresh: sqlite3.Connection,
) -> None:
    """Q3's law, asserted against generated policy through `coverage.build`'s detector.

    This is the one that matters most: a generator that emits a bare effect label is
    emitting a silent permit at scale.
    """
    proposal, _ = _derive()
    ratify.ratify(
        fresh,
        proposal.policies,
        effects=proposal.effects,
        expected_version=policy_loader.current_version(fresh),
        ratified_by_session="tests",
        now=NOW,
    )
    inert = [r for r in coverage.build(fresh).effects if r.state == coverage.DECLARED_INERT]
    assert inert == [], f"the proposer emitted undeclared effect labels: {[r.name for r in inert]}"


def test_a_proposed_candidate_reaches_the_active_set_only_through_the_ceremony(
    fresh: sqlite3.Connection,
) -> None:
    """Principle 1: proposing changes nothing until a human ratifies.

    The candidate exists, it is complete, and the active set has not moved — because
    `derive` writes nowhere and the only door is `ratify`.
    """
    before = policy_loader.current_version(fresh)
    proposal, _ = _derive()
    assert proposal.policies
    assert policy_loader.current_version(fresh) == before, (
        "drafting a proposal moved the active policy set"
    )

    ratify.ratify(
        fresh,
        proposal.policies,
        effects=proposal.effects,
        expected_version=before,
        ratified_by_session="operator-1",
        now=NOW,
    )
    assert policy_loader.current_version(fresh) != before


def test_the_proposer_module_exposes_no_write_path_to_the_enforcer() -> None:
    """Structural: nothing in `proposer.py` imports the loader or the audit writer.

    `test_proposer_isolation.py` proves the engine cannot reach the proposer; this proves
    the reverse door too — the proposer holds no tool for enacting anything.
    """
    import ast

    source = Path(proposer.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    forbidden = {
        "onedoor.guardrail.policy_loader",
        "onedoor.guardrail.audit",
        "onedoor.guardrail.decision",
        "onedoor.studio.ratify",
    }
    assert not (imported & forbidden), (
        f"the proposer imports a write path: {sorted(imported & forbidden)}. It drafts; "
        "the ceremony enacts."
    )


def test_the_fixture_pulls_in_the_reversal_a_chosen_rule_names() -> None:
    """Fail-closed by construction: a candidate that cannot validate is not a candidate.

    A rule at an auto-executing tier needs its `compensating_command` present, so the
    proposer includes it rather than emitting a set that fails for a reason the
    description never mentioned.
    """
    proposal, _ = _derive("We issue refunds.")
    actions = {p.action_type for p in proposal.policies}
    assert "refunds.issue" in actions
    assert "payments.reverse" in actions, "the reversal the chosen rule names was omitted"
    assert validate_module.problems(proposal.policies, proposal.effects) == []


def test_mentions_quote_the_description_rather_than_paraphrasing_it() -> None:
    """Principle 2: the explanation derives from the artifact, not the model's memory."""
    proposal, _ = _derive()
    assert proposal.mentions
    for mention in proposal.mentions:
        assert mention.quote
        assert mention.quote in DESCRIPTION, (
            f"a mention quoted text that is not in the description: {mention.quote!r}"
        )
